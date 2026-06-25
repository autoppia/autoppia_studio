import uuid
import os
from datetime import datetime, timezone
import smtplib
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import companies_collection, connectors_collection
from app.repositories import ConnectorRepository
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.routes.credentials import create_credential_record, resolve_secret_refs

router = APIRouter()
SECRET_PLACEHOLDER = "__configured__"


def _tool(name: str, description: str, side_effects: str = "reads") -> dict[str, Any]:
    return {"name": name, "description": description, "sideEffects": side_effects, "inputSchema": {"type": "object", "properties": {}}}


def _safe_tool_segment(value: str) -> str:
    segment = "".join(char.lower() if char.isalnum() else "_" for char in str(value or "knowledge"))
    segment = "_".join(part for part in segment.split("_") if part)
    return segment[:48] or "knowledge"


def _api_toolkit(name: str, prefix: str, auth_fields: list[str], config_fields: list[str] | None = None, requirements: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": f"{name} Toolkit",
        "authFields": auth_fields,
        "configFields": config_fields or ["baseUrl"],
        "runtimeRequirements": requirements or ["api_credentials", "network"],
        "tools": [
            _tool(f"{prefix}.search", f"Search or list {name} resources."),
            _tool(f"{prefix}.get", f"Fetch one {name} resource."),
            _tool(f"{prefix}.create", f"Create a {name} resource after approval.", "writes"),
            _tool(f"{prefix}.update", f"Update a {name} resource after approval.", "writes"),
        ],
    }


CONNECTOR_TOOLKIT_DEFAULTS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail Toolkit",
        "authFields": ["clientId", "clientSecret", "refreshToken", "userEmail"],
        "configFields": ["accessToken", "scopes", "apiVersion", "defaultFrom", "signature"],
        "runtimeRequirements": ["oauth:gmail", "network"],
        "tools": [
            {"name": "gmail.search_emails", "description": "Search client emails.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "gmail.read_email", "description": "Read an email thread.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"threadId": {"type": "string"}}}},
            {"name": "gmail.send_email", "description": "Send an email after approval.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
        ],
    },
    "smtp": {
        "name": "SMTP Toolkit",
        "authFields": ["email", "password"],
        "configFields": ["smtpServer", "smtpPort", "imapServer", "imapPort"],
        "runtimeRequirements": ["smtp_credentials", "network"],
        "tools": [
            {"name": "imap.search_emails", "description": "Search mailbox messages through IMAP by text query.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "folder": {"type": "string", "default": "INBOX"}, "limit": {"type": "integer", "default": 10}}}},
            {"name": "imap.read_email", "description": "Read one email message body through IMAP by messageId/UID.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"messageId": {"type": "string"}, "uid": {"type": "string"}, "folder": {"type": "string", "default": "INBOX"}}}},
            {"name": "smtp.draft_email", "description": "Prepare an email draft without sending it.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
            {"name": "smtp.send_email", "description": "Send an email through SMTP after approval.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
        ],
    },
    "holded": {
        "name": "Holded Toolkit",
        "authFields": ["apiKey"],
        "configFields": ["workspaceId"],
        "runtimeRequirements": ["api_credentials", "network"],
        "tools": [
            {"name": "holded.list_clients", "description": "List Holded contacts/clients.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
            {"name": "holded.search_clients", "description": "Search clients in Holded.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "holded.list_invoices", "description": "List recent Holded invoices.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}, "status": {"type": "string"}}}},
            {"name": "holded.search_invoices", "description": "Search Holded invoices by customer, number, notes or raw invoice fields.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
            {"name": "holded.get_invoice", "description": "Fetch an invoice.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"invoiceId": {"type": "string"}}}},
        ],
    },
    "telegram": {
        "name": "Telegram Toolkit",
        "authFields": ["botToken", "chatId"],
        "configFields": ["defaultChatId"],
        "runtimeRequirements": ["bot_token", "network"],
        "tools": [
            {"name": "telegram.get_chat", "description": "Fetch Telegram chat metadata for the configured or provided chat.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"chatId": {"type": "string"}}}},
            {"name": "telegram.send_message", "description": "Send a Telegram message after approval.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"chatId": {"type": "string"}, "message": {"type": "string"}}}},
        ],
    },
    "web": {
        "name": "Web Toolkit",
        "authFields": ["authUsername", "authPassword"],
        "configFields": ["startUrl", "loginUrl"],
        "runtimeRequirements": ["browser_or_http", "network"],
        "tools": [
            {"name": "web.fetch", "description": "Fetch a public page.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
            {"name": "web.fetch_text", "description": "Fetch a public page and return cleaned visible text.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "maxChars": {"type": "integer"}}}},
            {"name": "web.extract_links", "description": "Fetch a public page and extract links with labels.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "limit": {"type": "integer"}}}},
            {"name": "browser.navigate", "description": "Open a website in browser runtime.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
        ],
    },
    "bopa": {
        "name": "BOPA Toolkit",
        "authFields": [],
        "configFields": ["baseUrl"],
        "runtimeRequirements": ["network"],
        "tools": [
            _tool("bopa.latest_bulletin_pdf", "Resolve the latest official BOPA bulletin PDF using the public BOPA API."),
            _tool("bopa.latest_bulletin", "Fetch metadata for the latest official BOPA bulletin."),
            _tool("bopa.list_bulletins", "List BOPA bulletins for the current publication month."),
        ],
    },
    "knowledge": {
        "name": "Knowledge Toolkit",
        "authFields": [],
        "configFields": ["collectionName", "sourceUrl"],
        "runtimeRequirements": ["vectorstore", "embedding_model"],
        "tools": [
            {"name": "knowledge.search", "description": "Search company documents with configurable topK and optional filters.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "topK": {"type": "integer"}, "k": {"type": "integer"}, "minScore": {"type": "number"}, "documentId": {"type": "string"}, "source": {"type": "string"}}}},
            {"name": "knowledge.list_documents", "description": "List indexed/stored documents available in this vector database.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}}},
            {"name": "knowledge.stats", "description": "Return document and indexing stats for this vector database.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "knowledge.read_document", "description": "Read a document chunk.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {"documentId": {"type": "string"}}}},
        ],
    },
    "api": {
        "name": "API Toolkit",
        "authFields": ["apiKey"],
        "configFields": ["baseUrl", "openApiUrl", "docsUrl"],
        "runtimeRequirements": ["openapi_optional", "network"],
        "tools": [
            {"name": "api.call", "description": "Call an approved API endpoint.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"method": {"type": "string"}, "path": {"type": "string"}, "body": {"type": "object"}}}},
        ],
    },
    "openai": _api_toolkit("OpenAI", "openai", ["apiKey"], ["organizationId", "projectId"]),
    "weather": {
        "name": "Weather Toolkit",
        "authFields": [],
        "configFields": ["countryCode"],
        "runtimeRequirements": ["network"],
        "tools": [
            _tool("weather.forecast", "Fetch weather forecast for a location."),
            _tool("weather.current", "Fetch current weather for a location."),
        ],
    },
    "google": _api_toolkit("Google Custom Search", "google", ["googleApiKey", "googleSearchEngineId"], []),
    "taostats": _api_toolkit("TaoStats", "taostats", ["apiKey"], []),
    "aws": _api_toolkit("AWS", "aws", ["accessKeyId", "secretAccessKey"], ["region"], ["cloud_credentials", "network"]),
    "runpod": _api_toolkit("RunPod", "runpod", ["apiKey"], [], ["cloud_credentials", "network"]),
    "contabo": _api_toolkit("Contabo", "contabo", ["clientId", "clientSecret", "apiUser", "apiPassword"], [], ["cloud_credentials", "network"]),
    "cloudflare": _api_toolkit("Cloudflare", "cloudflare", ["apiToken"], ["zoneId"], ["cloud_credentials", "network"]),
    "kubernetes": _api_toolkit("Kubernetes", "kubernetes", ["token"], ["baseUrl", "namespace", "verifyTls"], ["cluster_credentials", "network"]),
    "slack": {
        "name": "Slack Toolkit",
        "authFields": ["botToken"],
        "configFields": ["defaultChannelId"],
        "runtimeRequirements": ["bot_token", "network"],
        "tools": [
            _tool("slack.search_messages", "Search Slack messages."),
            _tool("slack.read_channel", "Read messages from a Slack channel."),
            _tool("slack.send_message", "Send a Slack message after approval.", "writes"),
        ],
    },
    "discord": {
        "name": "Discord Toolkit",
        "authFields": ["botToken"],
        "configFields": ["defaultChannelId"],
        "runtimeRequirements": ["bot_token", "network"],
        "tools": [_tool("discord.read_channel", "Read Discord messages."), _tool("discord.send_message", "Send a Discord message after approval.", "writes")],
    },
    "matrix": _api_toolkit("Matrix", "matrix", ["accessToken"], ["homeserverUrl", "defaultRoomId"], ["messaging_credentials", "network"]),
    "signal": _api_toolkit("Signal", "signal", ["apiToken"], ["baseUrl", "account"], ["messaging_bridge", "network"]),
    "teams": _api_toolkit("Microsoft Teams", "teams", ["accessToken"], ["teamId", "channelId"], ["microsoft_graph", "network"]),
    "whatsapp": _api_toolkit("WhatsApp Cloud", "whatsapp", ["accessToken"], ["phoneNumberId", "apiVersion"], ["meta_graph", "network"]),
    "github": {
        "name": "GitHub Toolkit",
        "authFields": ["personalAccessToken"],
        "configFields": ["owner", "repo", "baseUrl"],
        "runtimeRequirements": ["repo_credentials", "network"],
        "tools": [
            _tool("github.search_repositories", "Search GitHub repositories."),
            _tool("github.get_issue", "Fetch a GitHub issue or PR."),
            _tool("github.create_issue", "Create a GitHub issue after approval.", "writes"),
            _tool("github.comment", "Comment on a GitHub issue or PR after approval.", "writes"),
        ],
    },
    "gitlab": _api_toolkit("GitLab", "gitlab", ["privateToken"], ["baseUrl", "projectId"], ["repo_credentials", "network"]),
    "jira": _api_toolkit("Jira", "jira", ["apiToken"], ["serverUrl", "email", "projectKey"], ["ticketing_credentials", "network"]),
    "google_calendar": _api_toolkit("Google Calendar", "google_calendar", ["accessToken"], ["calendarId"], ["oauth:google", "network"]),
    "google_drive": _api_toolkit("Google Drive", "google_drive", ["accessToken"], ["folderId"], ["oauth:google", "network"]),
    "confluence": _api_toolkit("Confluence", "confluence", ["apiToken"], ["baseUrl", "spaceId"], ["knowledge_source", "network"]),
    "asana": _api_toolkit("Asana", "asana", ["accessToken"], ["workspaceGid", "projectGid"], ["task_tool_credentials", "network"]),
    "notion": _api_toolkit("Notion", "notion", ["apiKey"], ["databaseId"], ["workspace_credentials", "network"]),
    "trello": _api_toolkit("Trello", "trello", ["apiKey", "token"], ["boardId", "listId"], ["task_tool_credentials", "network"]),
    "linear": _api_toolkit("Linear", "linear", ["apiKey"], ["teamId"], ["ticketing_credentials", "network"]),
    "postgres": _api_toolkit("Postgres", "postgres", ["user", "password"], ["host", "port", "dbname"], ["database_credentials", "network"]),
    "mongodb": _api_toolkit("MongoDB", "mongodb", ["uri", "user", "password"], ["host", "port", "dbname", "authSource"], ["database_credentials", "network"]),
    "twitter": _api_toolkit("Twitter/X", "twitter", ["bearerToken"], [], ["social_api_credentials", "network"]),
    "twitterapi": _api_toolkit("twitterapi.io", "twitterapi", ["apiKey"], [], ["social_api_credentials", "network"]),
    "bittensor_directory": {
        "name": "Bittensor Directory Toolkit",
        "authFields": [],
        "configFields": [],
        "runtimeRequirements": ["network"],
        "tools": [_tool("bittensor_directory.list_subnets", "List known Bittensor subnets."), _tool("bittensor_directory.get_subnet", "Fetch Bittensor subnet metadata.")],
    },
    "bittensor_subnet_vendor": _api_toolkit("Bittensor Vendor API", "bittensor_vendor", ["apiKey"], ["baseUrl", "authHeader", "authScheme"], ["bittensor_api", "network"]),
    "bittensor_desearch": _api_toolkit("Bittensor Desearch", "bittensor_desearch", ["apiKey"], ["baseUrl", "authHeader", "authScheme"], ["bittensor_api", "network"]),
    "bittensor_datauniverse": _api_toolkit("Bittensor DataUniverse", "bittensor_datauniverse", ["apiKey"], ["baseUrl", "authHeader", "authScheme"], ["bittensor_api", "network"]),
    "bittensor_chutes": _api_toolkit("Bittensor Chutes", "bittensor_chutes", ["apiKey"], ["baseUrl", "authHeader", "authScheme"], ["bittensor_api", "network"]),
    "bittensor_computehorde": _api_toolkit("Bittensor ComputeHorde", "bittensor_computehorde", ["apiKey"], ["baseUrl", "authHeader", "authScheme"], ["bittensor_api", "network"]),
}


class ConnectorCreateRequest(BaseModel):
    email: str
    companyId: str
    name: str
    type: str = "api"
    category: str = "software"
    description: str = ""
    status: str = "not_connected"
    config: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    generationStatus: str = ""
    surface: str = ""
    authRequired: bool | None = None
    discoveryStatus: str = ""
    discoveryMode: str = ""
    runtimeRequirements: list[str] = Field(default_factory=list)


class ConnectorUpdateRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    category: str | None = None
    description: str | None = None
    status: str | None = None
    config: dict[str, Any] | None = None
    provider: str | None = None
    generationStatus: str | None = None
    surface: str | None = None
    authRequired: bool | None = None
    discoveryStatus: str | None = None
    discoveryMode: str | None = None
    runtimeRequirements: list[str] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connector_toolkit(connector: dict[str, Any]) -> dict[str, Any]:
    connector_type = str(connector.get("type") or "api").lower()
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    toolkit_id = f"{connector.get('connectorId')}:toolkit"
    provider = connector.get("provider", "official")
    config = connector.get("config", {}) or {}
    custom_api = connector_type == "api" and provider == "custom"
    toolkit_name = f"{connector.get('name', 'Custom')} Generated API Toolkit" if custom_api else defaults["name"]
    tools = defaults["tools"]
    runtime_requirements = list(defaults["runtimeRequirements"])
    auth_fields = list(defaults["authFields"])
    config_fields = list(defaults["configFields"])
    if connector_type == "web" and provider == "custom":
        toolkit_name = f"{connector.get('name', 'Custom Web')} Web Toolkit"
        runtime_requirements = list(connector.get("runtimeRequirements") or ["browser", "network"])
        auth_fields = list(defaults["authFields"]) if connector.get("authRequired") else []
        config_fields = ["baseUrl", "startUrl", "loginUrl"] if connector.get("authRequired") else ["baseUrl", "startUrl"]
    if connector_type == "knowledge":
        db_name = str(config.get("vectorDatabaseName") or connector.get("name") or "Knowledge")
        db_segment = _safe_tool_segment(db_name)
        toolkit_name = f"{db_name} Toolkit"
        config_fields = ["vectorDatabaseId", "collectionName", "vectorStoreProvider"]
        tools = [
            {
                "name": f"knowledge.{db_segment}.search",
                "description": f"Search documents indexed in {db_name} with configurable topK and optional filters.",
                "sideEffects": "none",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "topK": {"type": "integer"}, "k": {"type": "integer"}, "minScore": {"type": "number"}, "documentId": {"type": "string"}, "source": {"type": "string"}}},
            },
            {
                "name": f"knowledge.{db_segment}.list_documents",
                "description": f"List documents stored in {db_name}.",
                "sideEffects": "none",
                "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}},
            },
            {
                "name": f"knowledge.{db_segment}.stats",
                "description": f"Return document and indexing stats for {db_name}.",
                "sideEffects": "none",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": f"knowledge.{db_segment}.read_document",
                "description": f"Read a document from {db_name}.",
                "sideEffects": "none",
                "inputSchema": {"type": "object", "properties": {"documentId": {"type": "string"}}},
            },
        ]
    if custom_api:
        runtime_requirements = ["api_docs_or_openapi", "api_credentials_optional", "network"]
        tools = [
            {"name": "api.discover_schema", "description": "Load public API docs or an OpenAPI spec to draft available endpoints.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"docsUrl": {"type": "string"}, "openApiUrl": {"type": "string"}}}},
            {"name": "api.call", "description": f"Call an approved {connector.get('name', 'custom')} API endpoint.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"method": {"type": "string"}, "path": {"type": "string"}, "body": {"type": "object"}}}},
        ]
        if config.get("openApiUrl") or config.get("docsUrl"):
            tools.insert(1, {"name": "api.generate_toolkit", "description": "Generate typed tools from the provided API documentation.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {"connectorId": {"type": "string"}}}})
    return {
        "toolkitId": toolkit_id,
        "connectorId": connector.get("connectorId", ""),
        "name": toolkit_name,
        "connectorName": connector.get("name", ""),
        "category": connector.get("category", "software"),
        "status": connector.get("status", "not_connected"),
        "runtimeRequirements": runtime_requirements,
        "authFields": auth_fields,
        "configFields": config_fields,
        "tools": tools,
    }


def _is_secret_field(field: str) -> bool:
    value = field.lower()
    return any(token in value for token in ("password", "secret", "token", "apikey", "api_key", "key"))


def _credential_type_for(field: str) -> str:
    value = field.lower()
    if "password" in value:
        return "password"
    if "apikey" in value or "api_key" in value or value.endswith("key"):
        return "apikey"
    if "oauth" in value or "refresh" in value:
        return "oauth"
    return "token"


def _credential_fields_for(connector_type: str) -> set[str]:
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    fields = set(defaults.get("authFields") or [])
    fields.update(field for field in defaults.get("configFields") or [] if _is_secret_field(field))
    return fields


def _public_config(config: dict[str, Any], credential_refs: dict[str, str] | None = None) -> dict[str, Any]:
    public: dict[str, Any] = {}
    refs = credential_refs or {}
    for key, value in (config or {}).items():
        public[key] = SECRET_PLACEHOLDER if value and _is_secret_field(key) else value
    for key, ref in refs.items():
        if ref:
            public[key] = SECRET_PLACEHOLDER
    return public


def _connector_capability_discovery(connector: dict[str, Any], toolkit: dict[str, Any]) -> dict[str, Any]:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    connector_type = str(connector.get("type") or "api").lower()
    provider = str(connector.get("provider") or "official").lower()
    docs_urls = [
        str(config.get(key) or "").strip()
        for key in ("openApiUrl", "docsUrl", "sourceUrl")
        if str(config.get(key) or "").strip()
    ]
    surface_urls = [
        str(config.get(key) or "").strip()
        for key in ("startUrl", "baseUrl", "loginUrl")
        if str(config.get(key) or "").strip()
    ]
    auth_fields = list(toolkit.get("authFields") or [])
    credential_fields = connector.get("credentialFields") if isinstance(connector.get("credentialFields"), dict) else {}
    configured_auth = sum(1 for field in auth_fields if credential_fields.get(field, {}).get("configured") or config.get(field) == SECRET_PLACEHOLDER or bool(config.get(field)))
    tool_specs = list(toolkit.get("tools") or [])
    generic_discovery_tools = {"api.discover_schema", "api.generate_toolkit", "api.call", "browser.open", "browser.click", "browser.type"}
    typed_tools = [
        str(tool.get("name") or "")
        for tool in tool_specs
        if str(tool.get("name") or "") and str(tool.get("name") or "") not in generic_discovery_tools
    ]
    write_tools = [
        tool.get("name", "")
        for tool in tool_specs
        if str(tool.get("sideEffects") or "").lower() in {"write", "writes", "send", "mutates"}
    ]
    discovery_gaps = []
    if provider == "custom" and connector_type == "api" and not docs_urls:
        discovery_gaps.append({"key": "docs", "label": "Add OpenAPI or documentation URL.", "target": "config.openApiUrl"})
    if provider == "custom" and connector_type == "web" and not (config.get("startUrl") or config.get("baseUrl")):
        discovery_gaps.append({"key": "startUrl", "label": "Add the web app start URL.", "target": "config.startUrl"})
    if auth_fields and configured_auth < len(auth_fields):
        discovery_gaps.append({"key": "auth", "label": "Configure required auth fields.", "target": "credentials"})
    if not tool_specs:
        discovery_gaps.append({"key": "tools", "label": "Publish or synthesize callable tools.", "target": "capabilities"})
    requires_docs = provider == "custom" and connector_type == "api"
    requires_surface = provider == "custom" and connector_type == "web"
    docs_ready = bool(docs_urls) or not requires_docs
    surface_ready = bool(surface_urls) or not requires_surface
    auth_ready = not auth_fields or configured_auth >= len(auth_fields)
    typed_tools_ready = provider != "custom" or bool(typed_tools)
    entity_ready = docs_ready or provider != "custom"
    pipeline_stages = [
        {
            "key": "connector_docs",
            "label": "Connector docs/OpenAPI",
            "status": "ready" if docs_ready and surface_ready else "pending",
            "target": "config.openApiUrl" if requires_docs else "config.startUrl" if requires_surface else "config",
            "summary": "Docs or start surface are available." if docs_ready and surface_ready else "Add API docs/OpenAPI or a web start URL.",
        },
        {
            "key": "auth_state",
            "label": "Auth state",
            "status": "ready" if auth_ready else "pending",
            "target": "credentials",
            "summary": f"{configured_auth}/{len(auth_fields)} required auth fields configured.",
        },
        {
            "key": "entity_mapping",
            "label": "Entity mapping",
            "status": "ready" if entity_ready else "pending",
            "target": "entities",
            "summary": "Entity discovery source is available." if entity_ready else "Provide docs or observations before entity mapping.",
        },
        {
            "key": "tool_synthesis",
            "label": "Typed tool synthesis",
            "status": "ready" if typed_tools_ready else "pending",
            "target": "capabilities",
            "summary": f"{len(typed_tools)} typed tools available." if typed_tools_ready else "Generate typed tools from docs, UI observations, or benchmarks.",
        },
        {
            "key": "candidate_tasks",
            "label": "Candidate tasks",
            "status": "recommended" if provider == "custom" else "ready",
            "target": "evals",
            "summary": "Seed benchmark tasks to harvest trajectories." if provider == "custom" else "Connector benchmark seeding is available.",
        },
    ]
    blocking_stages = [stage for stage in pipeline_stages if stage["status"] == "pending"]
    pipeline_state = "blocked" if blocking_stages else "needs_benchmark" if provider == "custom" else "ready"
    return {
        "mode": connector.get("discoveryMode") or ("task_scoped" if provider == "custom" else "official_toolkit"),
        "status": connector.get("discoveryStatus") or ("pending" if discovery_gaps or blocking_stages else "ready"),
        "surface": connector.get("surface") or ("browser" if connector_type == "web" else "api" if connector_type == "api" else connector_type),
        "docs": {
            "available": bool(docs_urls),
            "urls": docs_urls,
            "surfaceUrls": surface_urls,
            "generationStatus": connector.get("generationStatus", ""),
        },
        "auth": {
            "required": bool(auth_fields) or bool(connector.get("authRequired")),
            "requiredFields": auth_fields,
            "configuredFields": configured_auth,
            "totalFields": len(auth_fields),
        },
        "entityDiscovery": {
            "source": "openapi" if connector_type == "api" and docs_urls else "runtime_observation" if connector_type == "web" else "toolkit",
            "status": "available" if docs_urls or provider != "custom" else "pending",
        },
        "toolSynthesis": {
            "toolCount": len(tool_specs),
            "typedToolCount": len(typed_tools),
            "typedTools": typed_tools,
            "writeToolCount": len(write_tools),
            "writeTools": write_tools,
            "runtimeRequirements": toolkit.get("runtimeRequirements", []),
        },
        "candidateTasks": {
            "recommended": provider == "custom",
            "source": "benchmarks",
            "reason": "Custom connectors should generate capabilities from benchmark tasks." if provider == "custom" else "Official toolkit is ready for connector benchmark seeding.",
        },
        "ingestionPipeline": {
            "state": pipeline_state,
            "readyStages": sum(1 for stage in pipeline_stages if stage["status"] == "ready"),
            "totalStages": len(pipeline_stages),
            "nextStage": blocking_stages[0] if blocking_stages else next((stage for stage in pipeline_stages if stage["status"] == "recommended"), None),
            "stages": pipeline_stages,
        },
        "gaps": discovery_gaps,
    }


async def _extract_connector_credentials(
    *,
    existing: dict[str, Any] | None,
    email: str,
    company_id: str,
    connector_id: str,
    connector_name: str,
    connector_type: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    credential_fields = _credential_fields_for(connector_type)
    existing_refs = dict((existing or {}).get("credentialRefs") or {})
    next_config: dict[str, Any] = {}
    next_refs: dict[str, str] = dict(existing_refs)

    for key, value in (config or {}).items():
        if key not in credential_fields:
            next_config[key] = value
            continue
        if value == SECRET_PLACEHOLDER:
            if key in existing_refs:
                next_refs[key] = existing_refs[key]
            elif key in (existing or {}).get("config", {}):
                next_config[key] = (existing or {}).get("config", {}).get(key, "")
            continue
        if value is None or str(value) == "":
            next_refs.pop(key, None)
            continue
        credential = await create_credential_record(
            email=email,
            company_id=company_id,
            name=f"{connector_name} {key}",
            value=str(value),
            credential_type=_credential_type_for(key),
            created_for="connector",
            metadata={"connectorId": connector_id, "connectorName": connector_name, "field": key},
        )
        next_refs[key] = credential["secretRef"]

    return next_config, next_refs


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    connector = {
        "connectorId": doc.get("connectorId", ""),
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "type": doc.get("type", "api"),
        "category": doc.get("category", "software"),
        "description": doc.get("description", ""),
        "status": doc.get("status", "not_connected"),
        "provider": doc.get("provider", "custom" if doc.get("type") == "api" else "official"),
        "generationStatus": doc.get("generationStatus", "needs_docs" if doc.get("type") == "api" and doc.get("provider") == "custom" else "autoppia_supported"),
        "surface": doc.get("surface", ""),
        "authRequired": bool(doc.get("authRequired", False)),
        "discoveryStatus": doc.get("discoveryStatus", ""),
        "discoveryMode": doc.get("discoveryMode", ""),
        "runtimeRequirements": doc.get("runtimeRequirements", []),
        "config": _public_config(doc.get("config", {}), doc.get("credentialRefs", {})),
        "credentialFields": {key: {"configured": bool(value)} for key, value in (doc.get("credentialRefs", {}) or {}).items()},
        "lastTestAt": doc.get("lastTestAt"),
        "lastTestStatus": doc.get("lastTestStatus"),
        "lastTestMessage": doc.get("lastTestMessage"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }
    if str(connector["type"]).lower() == "knowledge":
        config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
        provider = str(config.get("vectorStoreProvider") or os.getenv("AUTOMATA_VECTORSTORE", "local")).strip().lower() or "local"
        collection = str(config.get("collectionName") or f"company-{connector['companyId']}")
        embedding_provider = os.getenv("AUTOMATA_EMBEDDINGS", "hash").strip().lower() or "hash"
        connector["vectorIndex"] = {
            "vectorDatabaseId": str(config.get("vectorDatabaseId") or ""),
            "name": str(config.get("vectorDatabaseName") or connector.get("name") or "Knowledge"),
            "provider": provider,
            "collectionName": collection,
            "embeddingProvider": embedding_provider,
            "embeddingModel": (
                os.getenv("AUTOMATA_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
                if embedding_provider == "openai"
                else f"hash-{os.getenv('AUTOMATA_HASH_EMBEDDING_DIMENSIONS', '256')}"
            ),
        }
    connector["toolkit"] = connector_toolkit(connector)
    connector["capabilityDiscovery"] = _connector_capability_discovery(connector, connector["toolkit"])
    return connector


async def _ensure_company(company_id: str, scope: RequestScope | None = None) -> None:
    scope = coerce_request_scope(scope)
    query: dict[str, Any] = {"companyId": company_id}
    if scope and scope.email:
        query["email"] = scope.email
    if not company_id or not await companies_collection.find_one(query, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Company not found")


def _repo(scope: RequestScope) -> ConnectorRepository:
    scope = coerce_request_scope(scope)
    return ConnectorRepository(connectors_collection, scope)


@router.get("/connectors")
async def list_connectors(email: str, companyId: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(email)
    if not companyId:
        company = await companies_collection.find_one({"email": email}, {"_id": 0, "companyId": 1}, sort=[("createdAt", 1)])
        companyId = str((company or {}).get("companyId") or "")
    await _ensure_company(companyId, scope)
    cursor = connectors_collection.find({"email": email, "companyId": companyId}, {"_id": 0}).sort("createdAt", 1)
    return {"connectors": [_serialize(doc) async for doc in cursor]}


@router.post("/connectors")
async def create_connector(body: ConnectorCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    await _ensure_company(body.companyId, scope)
    now = _now()
    connector_id = str(uuid.uuid4())
    connector_type = body.type.strip().lower() or "api"
    provider = body.provider or ("custom" if connector_type == "api" else "official")
    if provider == "custom" and connector_type not in {"api", "web"}:
        raise HTTPException(status_code=400, detail="Custom connectors are currently supported only for APIs and Web apps.")
    connector_name = body.name.strip() or "Untitled Connector"
    config, credential_refs = await _extract_connector_credentials(
        existing=None,
        email=email,
        company_id=body.companyId,
        connector_id=connector_id,
        connector_name=connector_name,
        connector_type=connector_type,
        config=body.config,
    )
    doc = {
        "connectorId": connector_id,
        "email": email,
        "companyId": body.companyId,
        "name": connector_name,
        "type": connector_type,
        "category": body.category.strip() or "software",
        "description": body.description.strip(),
        "status": body.status,
        "config": config,
        "credentialRefs": credential_refs,
        "provider": provider,
        "generationStatus": body.generationStatus or ("needs_docs" if provider == "custom" and connector_type == "api" else "needs_start_url" if provider == "custom" and connector_type == "web" else "autoppia_supported"),
        "surface": body.surface or ("webapp" if connector_type == "web" else "api" if connector_type == "api" else ""),
        "authRequired": bool(body.authRequired) if body.authRequired is not None else False,
        "discoveryStatus": body.discoveryStatus or ("pending" if provider == "custom" else "ready"),
        "discoveryMode": body.discoveryMode or "task_scoped",
        "runtimeRequirements": body.runtimeRequirements or (["browser", "network"] if connector_type == "web" else ["network"] if connector_type == "api" else []),
        "createdAt": now,
        "updatedAt": now,
    }
    await connectors_collection.insert_one(doc)
    return {"success": True, "connector": _serialize(doc)}


@router.put("/connectors/{connector_id}")
async def update_connector(connector_id: str, body: ConnectorUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    now = _now()
    repo = _repo(scope)
    existing = await repo.by_id(connector_id)

    update: dict[str, Any] = {"updatedAt": now}
    if body.name is not None:
        update["name"] = body.name.strip() or "Untitled Connector"
    if body.type is not None:
        update["type"] = body.type.strip().lower() or "api"
    if body.category is not None:
        update["category"] = body.category.strip() or "software"
    if body.description is not None:
        update["description"] = body.description.strip()
    if body.status is not None:
        update["status"] = body.status
    if body.provider is not None:
        update["provider"] = body.provider
    if body.generationStatus is not None:
        update["generationStatus"] = body.generationStatus
    if body.surface is not None:
        update["surface"] = body.surface
    if body.authRequired is not None:
        update["authRequired"] = body.authRequired
    if body.discoveryStatus is not None:
        update["discoveryStatus"] = body.discoveryStatus
    if body.discoveryMode is not None:
        update["discoveryMode"] = body.discoveryMode
    if body.runtimeRequirements is not None:
        update["runtimeRequirements"] = body.runtimeRequirements
    if body.config is not None:
        connector_name = update.get("name", existing.get("name", "Connector"))
        connector_type = str(update.get("type", existing.get("type", "api")) or "api").lower()
        next_config, credential_refs = await _extract_connector_credentials(
            existing=existing,
            email=str(existing.get("email") or ""),
            company_id=str(existing.get("companyId") or ""),
            connector_id=connector_id,
            connector_name=connector_name,
            connector_type=connector_type,
            config=body.config,
        )
        update["config"] = next_config
        update["credentialRefs"] = credential_refs
        provider = body.provider or existing.get("provider", "custom" if existing.get("type") == "api" else "official")
        if connector_type == "api" and provider == "custom" and (next_config.get("openApiUrl") or next_config.get("docsUrl")) and body.generationStatus is None:
            update["generationStatus"] = "docs_provided"
        if connector_type == "web" and provider == "custom" and next_config.get("startUrl") and body.generationStatus is None:
            update["generationStatus"] = "start_url_provided"
    next_type = str(update.get("type", existing.get("type", "api")) or "api").lower()
    next_provider = str(update.get("provider", existing.get("provider", "custom" if next_type == "api" else "official")) or "").lower()
    if next_provider == "custom" and next_type not in {"api", "web"}:
        raise HTTPException(status_code=400, detail="Custom connectors are currently supported only for APIs and Web apps.")
    doc = await repo.update_owned_one({"connectorId": connector_id}, {"$set": update}, not_found="Connector not found")
    return {"success": True, "connector": _serialize(doc or {"connectorId": connector_id, **update})}


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str, scope: RequestScope = Depends(get_request_scope)):
    deleted = await _repo(scope).delete_owned_one({"connectorId": connector_id}, not_found="Connector not found")
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"success": True}


@router.post("/connectors/{connector_id}/test")
async def test_connector(connector_id: str, scope: RequestScope = Depends(get_request_scope)):
    doc = await _repo(scope).by_id(connector_id)

    connector_type = str(doc.get("type") or "api").lower()
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    config = {**(doc.get("config") or {})}
    config.update(await resolve_secret_refs(doc.get("credentialRefs") or {}))
    required_auth = defaults.get("authFields") or []
    if connector_type == "web" and not doc.get("authRequired"):
        required_auth = []
    missing = [field for field in required_auth if not str(config.get(field) or "").strip()]
    provider = doc.get("provider", "custom" if connector_type == "api" else "official")
    docs_configured = bool(str(config.get("openApiUrl") or config.get("docsUrl") or "").strip())

    now = _now()
    if connector_type == "api" and provider == "custom" and not docs_configured:
        status = "needs_auth"
        message = "Missing API docs: add docsUrl or openApiUrl, or ask Automata to search public docs and generate a toolkit draft."
        success = False
    elif missing:
        status = "needs_auth"
        message = f"Missing auth fields: {', '.join(missing)}"
        success = False
    elif connector_type == "smtp":
        smtp_server = str(config.get("smtpServer") or config.get("baseUrl") or "").strip()
        smtp_port = int(str(config.get("smtpPort") or config.get("port") or "465").strip())
        email = str(config.get("email") or "").strip()
        password = str(config.get("password") or config.get("apiKey") or "").strip()
        if not smtp_server:
            status = "needs_auth"
            message = "Missing config fields: smtpServer"
            success = False
        else:
            try:
                with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
                    server.login(email, password)
                status = "connected"
                message = "SMTP login passed. Toolkit is ready for agents."
                success = True
            except Exception as exc:
                status = "needs_auth"
                message = f"SMTP login failed: {exc.__class__.__name__}"
                success = False
    elif connector_type == "telegram":
        bot_token = str(config.get("botToken") or "").strip()
        chat_id = str(config.get("chatId") or config.get("defaultChatId") or "").strip()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                me_res = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
                me_data = me_res.json()
                if me_res.status_code >= 400 or not me_data.get("ok"):
                    raise RuntimeError("getMe failed")
                chat_res = await client.get(f"https://api.telegram.org/bot{bot_token}/getChat", params={"chat_id": chat_id})
                chat_data = chat_res.json()
                if chat_res.status_code >= 400 or not chat_data.get("ok"):
                    raise RuntimeError("getChat failed")
            status = "connected"
            message = "Telegram bot and chat are reachable. Toolkit is ready for agents."
            success = True
        except Exception as exc:
            status = "needs_auth"
            message = f"Telegram test failed: {exc.__class__.__name__}"
            success = False
    else:
        status = "connected"
        message = "Connector test passed. Toolkit is ready for agents."
        success = True

    await connectors_collection.update_one(
        {"connectorId": connector_id},
        {"$set": {"status": status, "lastTestAt": now, "lastTestStatus": "pass" if success else "fail", "lastTestMessage": message, "updatedAt": now}},
    )
    updated = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    return {"success": success, "message": message, "connector": _serialize(updated or doc)}
