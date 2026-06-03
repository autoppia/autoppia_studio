import os
import re
import uuid
import json
import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    companies_collection,
    connectors_collection,
    evals_collection,
    onboarding_sessions_collection,
    agent_webs_collection,
    agents_collection,
    trajectories_collection,
)
from app.routes.agent_creation import ensure_agent_creation_job

router = APIRouter()


KNOWN_CONNECTORS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail",
        "type": "gmail",
        "category": "email",
        "description": "Gmail connector for reading, searching and drafting email responses.",
    },
    "smtp": {
        "name": "SMTP",
        "type": "smtp",
        "category": "email",
        "description": "SMTP connector for sending approved emails.",
    },
    "email": {
        "name": "SMTP",
        "type": "smtp",
        "category": "email",
        "description": "Email connector for sending approved emails.",
    },
    "telegram": {
        "name": "Telegram",
        "type": "telegram",
        "category": "communication",
        "description": "Telegram connector for sending approved messages.",
    },
    "holded": {
        "name": "Holded",
        "type": "holded",
        "category": "software",
        "description": "Holded connector for clients, contacts and invoices.",
    },
    "bopa": {
        "name": "BOPA",
        "type": "web",
        "category": "web",
        "description": "BOPA public website connector.",
        "config": {"baseUrl": "https://www.bopa.ad/"},
    },
    "documents": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded documents and internal sources.",
    },
    "documentos": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded documents and internal sources.",
    },
    "docs": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded documents and internal sources.",
    },
    "pdf": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded PDFs and internal sources.",
    },
    "slack": {"name": "Slack", "type": "slack", "category": "communication", "description": "Slack connector for channels, messages and team workflows."},
    "discord": {"name": "Discord", "type": "discord", "category": "communication", "description": "Discord connector for channels and messages."},
    "matrix": {"name": "Matrix", "type": "matrix", "category": "communication", "description": "Matrix connector for rooms and messages."},
    "signal": {"name": "Signal", "type": "signal", "category": "communication", "description": "Signal connector via signal-cli REST bridge."},
    "teams": {"name": "Microsoft Teams", "type": "teams", "category": "communication", "description": "Microsoft Teams connector for channels and messages."},
    "whatsapp": {"name": "WhatsApp Cloud", "type": "whatsapp", "category": "communication", "description": "WhatsApp Cloud connector for approved customer messages."},
    "github": {"name": "GitHub", "type": "github", "category": "development", "description": "GitHub connector for repositories, issues and pull requests."},
    "gitlab": {"name": "GitLab", "type": "gitlab", "category": "development", "description": "GitLab connector for projects, issues and merge requests."},
    "jira": {"name": "Jira", "type": "jira", "category": "development", "description": "Jira connector for projects, issues and workflows."},
    "linear": {"name": "Linear", "type": "linear", "category": "software", "description": "Linear connector for teams, issues and product workflows."},
    "notion": {"name": "Notion", "type": "notion", "category": "software", "description": "Notion connector for pages, databases and knowledge workflows."},
    "trello": {"name": "Trello", "type": "trello", "category": "software", "description": "Trello connector for boards, lists and cards."},
    "asana": {"name": "Asana", "type": "asana", "category": "software", "description": "Asana connector for projects, tasks and workspaces."},
    "confluence": {"name": "Confluence", "type": "confluence", "category": "software", "description": "Confluence connector for spaces, pages and documentation."},
    "google calendar": {"name": "Google Calendar", "type": "google_calendar", "category": "software", "description": "Google Calendar connector for events and scheduling."},
    "google_calendar": {"name": "Google Calendar", "type": "google_calendar", "category": "software", "description": "Google Calendar connector for events and scheduling."},
    "calendar": {"name": "Google Calendar", "type": "google_calendar", "category": "software", "description": "Google Calendar connector for events and scheduling."},
    "google drive": {"name": "Google Drive", "type": "google_drive", "category": "software", "description": "Google Drive connector for files and folders."},
    "google_drive": {"name": "Google Drive", "type": "google_drive", "category": "software", "description": "Google Drive connector for files and folders."},
    "drive": {"name": "Google Drive", "type": "google_drive", "category": "software", "description": "Google Drive connector for files and folders."},
    "aws": {"name": "AWS", "type": "aws", "category": "cloud", "description": "AWS connector for cloud resources and operations."},
    "runpod": {"name": "RunPod", "type": "runpod", "category": "cloud", "description": "RunPod connector for GPU pods and templates."},
    "contabo": {"name": "Contabo", "type": "contabo", "category": "cloud", "description": "Contabo connector for cloud instances."},
    "cloudflare": {"name": "Cloudflare", "type": "cloudflare", "category": "cloud", "description": "Cloudflare connector for zones, DNS and edge configuration."},
    "kubernetes": {"name": "Kubernetes", "type": "kubernetes", "category": "cloud", "description": "Kubernetes connector for cluster resources."},
    "k8s": {"name": "Kubernetes", "type": "kubernetes", "category": "cloud", "description": "Kubernetes connector for cluster resources."},
    "postgres": {"name": "Postgres", "type": "postgres", "category": "data", "description": "Postgres connector for SQL queries and database workflows."},
    "postgresql": {"name": "Postgres", "type": "postgres", "category": "data", "description": "Postgres connector for SQL queries and database workflows."},
    "mongodb": {"name": "MongoDB", "type": "mongodb", "category": "data", "description": "MongoDB connector for collections and documents."},
    "mongo": {"name": "MongoDB", "type": "mongodb", "category": "data", "description": "MongoDB connector for collections and documents."},
    "openai": {"name": "OpenAI", "type": "openai", "category": "api", "description": "OpenAI connector for model and API workflows."},
    "weather": {"name": "Weather", "type": "weather", "category": "api", "description": "Weather connector for current conditions and forecasts."},
    "google search": {"name": "Google Custom Search", "type": "google", "category": "api", "description": "Google Custom Search connector for web search."},
    "taostats": {"name": "TaoStats", "type": "taostats", "category": "bittensor", "description": "TaoStats connector for Bittensor metrics."},
    "twitter": {"name": "Twitter/X", "type": "twitter", "category": "social", "description": "Twitter/X connector for social monitoring and posting workflows."},
    "x": {"name": "Twitter/X", "type": "twitter", "category": "social", "description": "Twitter/X connector for social monitoring and posting workflows."},
    "twitterapi": {"name": "twitterapi.io", "type": "twitterapi", "category": "social", "description": "twitterapi.io connector for Twitter/X API workflows."},
    "bittensor": {"name": "Bittensor Directory", "type": "bittensor_directory", "category": "bittensor", "description": "Bittensor Directory connector for subnet metadata."},
    "bittensor directory": {"name": "Bittensor Directory", "type": "bittensor_directory", "category": "bittensor", "description": "Bittensor Directory connector for subnet metadata."},
    "chutes": {"name": "Bittensor Chutes", "type": "bittensor_chutes", "category": "bittensor", "description": "Bittensor Chutes connector."},
    "computehorde": {"name": "Bittensor ComputeHorde", "type": "bittensor_computehorde", "category": "bittensor", "description": "Bittensor ComputeHorde connector."},
    "desearch": {"name": "Bittensor Desearch", "type": "bittensor_desearch", "category": "bittensor", "description": "Bittensor Desearch connector."},
    "datauniverse": {"name": "Bittensor DataUniverse", "type": "bittensor_datauniverse", "category": "bittensor", "description": "Bittensor DataUniverse connector."},
}

GENERIC_SOFTWARE_HINTS = ("crm", "erp", "saas", "dashboard", "stripe", "salesforce", "hubspot", "notion")
GENERIC_BROWSER_HINTS = ("website", "web", "portal", "government", "gobierno", "bopa.ad", "url")
SYSTEM_STOPWORDS = {
    "API",
    "CRM",
    "ERP",
    "SaaS",
    "Agent",
    "Automata",
    "Company",
    "Empresa",
    "Tareas",
    "Tasks",
}
ONBOARDING_MODEL = os.getenv("OPENAI_ONBOARDING_MODEL", "gpt-5-mini")
DEFAULT_OPERATOR_RUNTIME_ENDPOINT = os.getenv("AUTOMATA_DEFAULT_RUNTIME_ENDPOINT", "http://127.0.0.1:5060/step").strip()
DEFAULT_OPERATOR_RUNTIME_TYPE = os.getenv("AUTOMATA_DEFAULT_RUNTIME_TYPE", "generalist_with_company_capabilities").strip()
DEFAULT_RUNTIME_PROXY_BASE = os.getenv("AUTOMATA_RUNTIME_PROXY_BASE", "http://127.0.0.1:8080").rstrip("/")
KNOWLEDGE_SYSTEM_TERMS = {
    "doc",
    "docs",
    "document",
    "documents",
    "documento",
    "documentos",
    "knowledge",
    "conocimiento",
    "vectorstore",
    "pdf",
    "pdfs",
}
AUTH_REQUIREMENTS: dict[str, list[str]] = {
    "gmail": ["OAuth client ID", "OAuth client secret", "refresh token", "Gmail user email"],
    "smtp": ["SMTP server", "SMTP port", "email", "password"],
    "holded": ["Holded API key"],
    "telegram": ["Telegram bot token", "target chat ID"],
    "slack": ["Slack bot token", "default channel ID"],
    "discord": ["Discord bot token", "default channel ID"],
    "matrix": ["Matrix homeserver URL", "access token", "room ID"],
    "signal": ["Signal bridge URL", "API token", "account"],
    "teams": ["Microsoft Graph access token", "team ID", "channel ID"],
    "whatsapp": ["WhatsApp Cloud access token", "phone number ID"],
    "github": ["GitHub personal access token", "owner/repository if scoped"],
    "gitlab": ["GitLab private token", "base URL", "project ID"],
    "jira": ["Jira server URL", "email", "API token", "project key"],
    "linear": ["Linear API key", "team ID"],
    "notion": ["Notion API key", "database ID if scoped"],
    "trello": ["Trello API key", "Trello token"],
    "asana": ["Asana access token", "workspace/project ID if scoped"],
    "confluence": ["Confluence base URL", "API token", "space ID if scoped"],
    "google_calendar": ["Google OAuth access token", "calendar ID"],
    "google_drive": ["Google OAuth access token", "folder ID if scoped"],
    "aws": ["AWS access key ID", "AWS secret access key", "region"],
    "runpod": ["RunPod API key"],
    "contabo": ["Contabo client ID", "client secret", "API user", "API password"],
    "cloudflare": ["Cloudflare API token", "zone ID if scoped"],
    "kubernetes": ["Kubernetes API URL", "bearer token", "namespace"],
    "postgres": ["host", "port", "database name", "user", "password"],
    "mongodb": ["MongoDB URI or host", "user/password if required"],
    "openai": ["OpenAI API key", "project/organization if scoped"],
    "google": ["Google API key", "Custom Search engine ID"],
    "taostats": ["TaoStats API key"],
    "twitter": ["Twitter/X bearer token"],
    "twitterapi": ["twitterapi.io API key"],
    "bittensor_subnet_vendor": ["vendor API key", "base URL"],
    "bittensor_desearch": ["Desearch API key"],
    "bittensor_datauniverse": ["DataUniverse API key"],
    "bittensor_chutes": ["Chutes API key"],
    "bittensor_computehorde": ["ComputeHorde API key"],
    "api": ["base URL or OpenAPI URL", "API key/token if required"],
}

ONBOARDING_CONNECTOR_TYPES = [
    "gmail",
    "smtp",
    "holded",
    "telegram",
    "web",
    "knowledge",
    "api",
    "openai",
    "weather",
    "google",
    "taostats",
    "aws",
    "runpod",
    "contabo",
    "cloudflare",
    "kubernetes",
    "slack",
    "discord",
    "matrix",
    "signal",
    "teams",
    "whatsapp",
    "github",
    "gitlab",
    "jira",
    "google_calendar",
    "google_drive",
    "confluence",
    "asana",
    "notion",
    "trello",
    "linear",
    "postgres",
    "mongodb",
    "twitter",
    "twitterapi",
    "bittensor_directory",
    "bittensor_subnet_vendor",
    "bittensor_desearch",
    "bittensor_datauniverse",
    "bittensor_chutes",
    "bittensor_computehorde",
]


class OnboardingStartRequest(BaseModel):
    email: str
    companyId: str = ""
    seedPrompt: str = ""


class OnboardingMessageRequest(BaseModel):
    email: str
    message: str


class OnboardingFinalizeRequest(BaseModel):
    email: str
    draft: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom"


def _env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _known_connector(keyword: str) -> dict[str, Any]:
    connector = dict(KNOWN_CONNECTORS[keyword])
    connector["config"] = dict(connector.get("config") or {})
    connector["provider"] = "official"
    connector["generationStatus"] = "autoppia_supported"
    if connector["type"] == "smtp":
        connector["config"].update(
            {
                key: value
                for key, value in {
                    "email": _env("SMTP_EMAIL", "EMAIL_HOST_USERNAME", "EMAIL_USER", "EMAIL_HOST_USER"),
                    "password": _env("SMTP_PASSWORD", "SMTP_PASS", "EMAIL_HOST_PASSWORD"),
                    "smtpServer": _env("SMTP_SERVER", "EMAIL_HOST"),
                    "smtpPort": _env("SMTP_PORT", "EMAIL_PORT"),
                    "imapServer": _env("IMAP_SERVER"),
                    "imapPort": _env("IMAP_PORT"),
                }.items()
                if value
            }
        )
        connector["status"] = "connected" if connector["config"].get("email") and connector["config"].get("password") and connector["config"].get("smtpServer") else "needs_auth"
    elif connector["type"] == "gmail":
        connector["config"].update(
            {
                key: value
                for key, value in {
                    "clientId": _env("GMAIL_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
                    "clientSecret": _env("GMAIL_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
                    "refreshToken": _env("GMAIL_REFRESH_TOKEN", "GOOGLE_OAUTH_REFRESH_TOKEN"),
                    "userEmail": _env("GMAIL_USER_EMAIL", "EMAIL_HOST_USERNAME", "SMTP_EMAIL"),
                    "scopes": _env("GMAIL_SCOPES") or "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send",
                }.items()
                if value
            }
        )
        connector["status"] = "connected" if connector["config"].get("refreshToken") else "needs_auth"
    elif connector["type"] in {"web", "knowledge"}:
        connector["status"] = "connected"
    else:
        connector["status"] = "needs_auth"
    return connector


def _default_draft() -> dict[str, Any]:
    return {
        "company": {
            "name": "",
            "industry": "",
            "description": "",
        },
        "agent": {
            "name": "",
            "websiteUrl": "",
            "successCriteria": "The user confirms the result, cited sources are correct, and sensitive write actions require approval.",
            "customInstructions": "",
        },
        "connectors": [],
        "tasks": [],
        "questions": [
            "What company or workflow are we automating?",
            "Which systems do you use? For example Gmail, SMTP, Holded, Telegram, BOPA, CRM, ERP, dashboards or APIs.",
            "List 3-10 tasks you want the agent to handle.",
        ],
    }


def _connector_key(connector: dict[str, Any]) -> str:
    return f"{connector.get('type')}:{str(connector.get('name') or '').lower()}"


def _normalized_connector_name(value: str) -> str:
    return re.sub(r"\b(api|connector|integration|toolkit)\b", "", value.lower()).strip(" -_:")


def _merge_connector(draft: dict[str, Any], connector: dict[str, Any]) -> None:
    if connector.get("type") == "knowledge":
        for existing in draft["connectors"]:
            if existing.get("type") == "knowledge":
                existing.update({k: v for k, v in connector.items() if v not in ("", None, {})})
                existing["name"] = existing.get("name") or connector.get("name", "Documents")
                return
    existing = {_connector_key(item): item for item in draft["connectors"]}
    key = _connector_key(connector)
    if key in existing:
        existing[key].update({k: v for k, v in connector.items() if v not in ("", None, {})})
        return
    if connector.get("type") == "api":
        normalized = _normalized_connector_name(str(connector.get("name") or ""))
        for item in draft["connectors"]:
            if item.get("type") == "api" and normalized and normalized == _normalized_connector_name(str(item.get("name") or "")):
                item.update({k: v for k, v in connector.items() if v not in ("", None, {})})
                return
    draft["connectors"].append(
        {
            "name": connector.get("name", "Custom Connector"),
            "type": connector.get("type", "api"),
            "category": connector.get("category", "software"),
            "description": connector.get("description", ""),
            "config": connector.get("config", {}),
            "status": connector.get("status", "not_connected"),
            "provider": connector.get("provider", "custom" if connector.get("type") == "api" else "official"),
            "generationStatus": connector.get("generationStatus", "needs_docs" if connector.get("type") == "api" else "autoppia_supported"),
        }
    )


def _extract_urls(text: str) -> list[str]:
    return [url.rstrip(".,;)") for url in re.findall(r"https?://[^\s,)]+", text)]


def _looks_like_api_docs(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in ("api docs", "docs de la api", "documentacion de la api", "documentación de la api", "swagger", "openapi"))


def _extract_docs_url(text: str, system_name: str = "") -> str:
    urls = _extract_urls(text)
    if not urls:
        return ""
    if system_name:
        lowered = system_name.lower()
        for url in urls:
            if lowered in url.lower():
                return url
    for url in urls:
        if any(token in url.lower() for token in ("docs", "api", "openapi", "swagger", "developer")):
            return url
    return urls[0]


def _extract_custom_systems(text: str) -> list[str]:
    systems: list[str] = []
    patterns = [
        r"(?:use|uses|using|usa|usar|usamos|utiliza|utilizamos|conectar(?:me)?(?: a)?|integrar(?: con)?)\s+([A-Z][A-Za-z0-9][A-Za-z0-9 ._-]{1,40})",
        r"(?:connector|conector|integration|integraci[oó]n)\s+(?:for|de|con|para)?\s*([A-Z][A-Za-z0-9][A-Za-z0-9 ._-]{1,40})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(1).strip(" .,:;")
            raw = re.split(r"[.,;:\n]|\s+(?:para|to|for|que|and|y|with|con)\b", raw, maxsplit=1)[0].strip(" .,:;")
            if not raw or raw in SYSTEM_STOPWORDS:
                continue
            raw_lower = raw.lower()
            if any(term in raw_lower for term in KNOWLEDGE_SYSTEM_TERMS):
                continue
            if raw.lower() in KNOWN_CONNECTORS:
                continue
            if raw.lower() in {item.lower() for item in GENERIC_SOFTWARE_HINTS}:
                continue
            if len(raw) < 3 or len(raw.split()) > 4:
                continue
            systems.append(raw)
    deduped: list[str] = []
    for system in systems:
        if not any(existing.lower() == system.lower() for existing in deduped):
            deduped.append(system)
    return deduped[:5]


def _has_auth_hint(text: str) -> bool:
    return any(term in text.lower() for term in ("api token", "token", "api key", "auth", "oauth", "credential", "credencial", "bot token"))


def _normalize_custom_connectors(draft: dict[str, Any], user_message: str) -> None:
    custom_systems = _extract_custom_systems(user_message)
    lower = user_message.lower()
    normalized_systems = {_normalized_connector_name(system): system for system in custom_systems}
    normalized_connectors: list[dict[str, Any]] = []

    for connector in draft.get("connectors", []):
        connector_type = str(connector.get("type") or "").lower()
        name = str(connector.get("name") or "")
        normalized_name = _normalized_connector_name(name)
        config = connector.get("config") or {}

        if connector_type == "knowledge" and custom_systems and ("docs" in lower or _looks_like_api_docs(user_message)):
            continue
        if connector_type == "web" and custom_systems:
            base_url = str(config.get("baseUrl") or "")
            if any(token in base_url.lower() for token in ("docs", "api", "developer")) or ("openapi url" in lower and name.lower() == "browser"):
                continue

        if connector_type == "api":
            if normalized_name == "openapi" and custom_systems:
                name = custom_systems[0]
                connector["name"] = name
                normalized_name = _normalized_connector_name(name)
            connector["provider"] = "custom"
            config = dict(config)
            docs_url = config.get("docsUrl") or config.get("openApiUrl") or _extract_docs_url(user_message, name)
            if docs_url:
                config.setdefault("docsUrl", docs_url)
                if any(token in str(docs_url).lower() for token in ("openapi", "swagger")):
                    config.setdefault("openApiUrl", docs_url)
            elif _looks_like_api_docs(user_message):
                config.setdefault("docsMentioned", True)
            connector["config"] = config
            connector["generationStatus"] = "docs_provided" if (config.get("docsUrl") or config.get("openApiUrl")) else "needs_docs"
            if _has_auth_hint(user_message) or connector["generationStatus"] == "needs_docs":
                connector["status"] = "needs_auth"

        if normalized_name in normalized_systems and connector_type != "api" and connector_type not in {"web", "knowledge"}:
            connector["provider"] = "custom"

        duplicate = False
        for existing in normalized_connectors:
            if connector_type == "api" and existing.get("type") == "api" and normalized_name == _normalized_connector_name(str(existing.get("name") or "")):
                existing.update({k: v for k, v in connector.items() if v not in ("", None, {})})
                duplicate = True
                break
        if not duplicate:
            normalized_connectors.append(connector)

    draft["connectors"] = normalized_connectors


def _extract_tasks(text: str) -> list[str]:
    normalized = re.sub(r"\s+(\d+[\).:-]\s*)", r"\n\1", text)
    lines = [line.strip(" -\t") for line in normalized.splitlines()]
    numbered_lines = [line for line in lines if re.match(r"^\d+[\).:-]\s*", line)]
    if numbered_lines:
        lines = numbered_lines
    tasks: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\).:-]\s*", "", line).strip()
        if len(cleaned) < 18:
            continue
        if any(word in cleaned.lower() for word in ("task", "tarea", "necesito", "quiero", "recibo", "buscar", "encontrar", "consultar", "leer", "resumir", "preparar", "enviar", "responder", "download", "summar", "find", "prepare", "send", "notify", "read")):
            tasks.append(cleaned)
    if not tasks and any(word in text.lower() for word in ("tasks", "tareas", "automate", "automatizar")):
        chunks = re.split(r"[.;]\s+", text)
        tasks = [chunk.strip() for chunk in chunks if len(chunk.strip()) > 28][:10]
    deduped: list[str] = []
    for task in tasks:
        if task and not any(existing.lower() == task.lower() for existing in deduped):
            deduped.append(task)
    return deduped[:10]


def task_name_from_prompt(prompt: str, fallback_index: int = 1) -> str:
    text = re.sub(r"^\s*\d+[\).:-]\s*", "", str(prompt or "")).strip()
    lower = text.lower()
    if not text:
        return f"Workflow {fallback_index}"
    if "bopa" in lower:
        if any(term in lower for term in ("email", "cliente", "client")):
            return "Summarize BOPA update for client email"
        return "Summarize latest BOPA labor update"
    if any(term in lower for term in ("factura", "invoice")):
        if "holded" in lower and any(term in lower for term in ("email", "respuesta", "response")):
            return "Find Holded invoice and draft reply"
        if "holded" in lower:
            return "Retrieve latest Holded invoice"
        return "Handle client invoice request"
    if any(term in lower for term in ("telegram", "slack", "discord", "teams")):
        if any(term in lower for term in ("urgente", "urgent")):
            return "Send urgent team notification"
        return "Send team notification"
    if any(term in lower for term in ("clasificar", "classify", "nomina", "contrato", "consulta")):
        return "Classify client request"
    if any(term in lower for term in ("document", "documento", "fuente", "source", "knowledge", "conocimiento")):
        return "Answer from internal documents"
    if any(term in lower for term in ("email", "correo")):
        return "Process client email"

    words = re.findall(r"[A-Za-z0-9]+", text)
    title = " ".join(words[:7]).strip()
    if not title:
        return f"Workflow {fallback_index}"
    return title[:1].upper() + title[1:60]


def _ensure_extracted_setup(draft: dict[str, Any], user_message: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    before_company = dict(draft["company"])
    before_agent = dict(draft["agent"])
    before_connectors = {_connector_key(item) for item in draft["connectors"]}
    _apply_message(draft, user_message)

    if draft["company"] != before_company:
        events.extend(
            [
                _event("tool_call", f"Updating company profile: {draft['company'].get('name') or 'Untitled'}", tool_name="set_company"),
                _event("tool_result", f"Updated company: {draft['company'].get('name') or 'Untitled'}", tool_name="set_company"),
            ]
        )
    if draft["agent"] != before_agent:
        events.extend(
            [
                _event("tool_call", f"Preparing agent: {draft['agent'].get('name') or 'Company Agent'}", tool_name="set_agent"),
                _event("tool_result", f"Prepared agent: {draft['agent'].get('name') or 'Company Agent'}", tool_name="set_agent"),
            ]
        )
    for connector in draft["connectors"]:
        if _connector_key(connector) not in before_connectors:
            events.extend(
                [
                    _event("tool_call", f"Creating connector: {connector.get('name')}", tool_name="add_connector"),
                    _event("tool_result", f"Created connector/toolkit: {connector.get('name')}", tool_name="add_connector"),
                ]
            )
    return events


def _ensure_extracted_tasks(draft: dict[str, Any], user_message: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    extracted = _extract_tasks(user_message)
    if len(extracted) > 1:
        draft["tasks"] = [
            existing for existing in draft["tasks"]
            if sum(1 for task in extracted if task.lower() in existing["prompt"].lower()) < 2
            and not re.search(r"\b2[\).:-]\s+", existing["prompt"])
        ]
    for task in extracted:
        if any(existing["prompt"].strip().lower() == task.lower() for existing in draft["tasks"]):
            continue
        name = task_name_from_prompt(task, len(draft["tasks"]) + 1)
        draft["tasks"].append(
            {
                "name": name,
                "prompt": task,
                "successCriteria": "The user approves the result and all sensitive writes are confirmed before execution.",
                "status": "draft",
            }
        )
        events.extend(
            [
                _event("tool_call", f"Creating benchmark task: {task[:80]}", tool_name="add_task"),
                _event("tool_result", f"Created benchmark task: {task[:80]}", tool_name="add_task"),
            ]
        )
    return events


def _prune_stale_task_events(events: list[dict[str, Any]], draft: dict[str, Any]) -> list[dict[str, Any]]:
    task_prompts = [str(task.get("prompt") or "").strip().lower() for task in draft.get("tasks", [])]
    if not task_prompts:
        return events
    pruned: list[dict[str, Any]] = []
    for event in events:
        if event.get("toolName") != "add_task":
            pruned.append(event)
            continue
        content = str(event.get("content") or "").lower()
        if any(prompt[:60] and prompt[:60] in content for prompt in task_prompts):
            pruned.append(event)
    return pruned


def _apply_message(draft: dict[str, Any], message: str) -> dict[str, Any]:
    text = message.strip()
    lower = text.lower()
    custom_systems = _extract_custom_systems(text)

    if not draft["company"]["name"]:
        name_match = re.search(r"(?:company|empresa|compañ[ií]a|asesor[ií]a)\s+(?:is|es|called|llamada?)?\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ -]{2,40})", text)
        if name_match:
            draft["company"]["name"] = name_match.group(1).strip(" .")
    if "celeris" in lower and not draft["company"].get("name"):
        draft["company"]["name"] = "Celeris"
        draft["company"]["industry"] = "Labor advisory, Andorra"
        draft["company"]["description"] = "Asesoría laboral en Andorra que automatiza emails, facturas, comunicaciones y seguimiento del BOPA."

    if not draft["company"]["description"] and len(text) > 40:
        draft["company"]["description"] = text[:500]

    if any(term in lower for term in ("andorra", "laboral", "asesoria", "asesoría")) and not draft["company"]["industry"]:
        draft["company"]["industry"] = "Labor advisory, Andorra"

    for url in _extract_urls(text):
        if custom_systems and any(token in url.lower() for token in ("docs", "api", "developer", "openapi", "swagger")):
            continue
        if "bopa.ad" in url:
            _merge_connector(draft, _known_connector("bopa"))
        elif not draft["agent"]["websiteUrl"]:
            draft["agent"]["websiteUrl"] = url
            _merge_connector(
                draft,
                {
                    "name": re.sub(r"^https?://", "", url).split("/")[0],
                    "type": "web",
                    "category": "web",
                    "description": f"Browser/web connector for {url}",
                    "config": {"baseUrl": url},
                    "status": "connected",
                },
            )

    for keyword in KNOWN_CONNECTORS:
        if keyword in {"docs", "documents"} and _looks_like_api_docs(text):
            continue
        if keyword in lower:
            _merge_connector(draft, _known_connector(keyword))

    has_known_connector = any(keyword in lower for keyword in KNOWN_CONNECTORS)
    if _looks_like_api_docs(text) and not has_known_connector and (_extract_urls(text) or not custom_systems):
        url = next(iter(_extract_urls(text)), "")
        _merge_connector(
            draft,
            {
                "name": "OpenAPI",
                "type": "api",
                "category": "api",
                "description": "Custom API connector generated from OpenAPI or Swagger documentation.",
                "config": {"openApiUrl": url} if url else {},
                "status": "not_connected",
                "provider": "custom",
                "generationStatus": "docs_provided" if url else "needs_docs",
            },
        )

    for system_name in custom_systems:
        if any(system_name.lower() == str(item.get("name", "")).lower() for item in draft["connectors"]):
            continue
        has_auth_hint = _has_auth_hint(text)
        docs_url = _extract_docs_url(text, system_name)
        config = {
            key: value
            for key, value in {
                "docsMentioned": _looks_like_api_docs(text),
                "docsUrl": docs_url,
                "openApiUrl": docs_url if any(token in docs_url.lower() for token in ("openapi", "swagger")) else "",
            }.items()
            if value
        }
        _merge_connector(
            draft,
            {
                "name": system_name,
                "type": "api",
                "category": "software",
                "description": f"Custom API connector for {system_name}. Add API docs/OpenAPI URL and auth so Automata can generate and test its toolkit.",
                "config": config,
                "status": "needs_auth" if has_auth_hint else "not_connected",
                "provider": "custom",
                "generationStatus": "docs_provided" if docs_url else "needs_docs",
            },
        )

    for hint in GENERIC_SOFTWARE_HINTS:
        if hint in lower and not any(hint in str(item.get("name", "")).lower() for item in draft["connectors"]):
            _merge_connector(
                draft,
                {
                    "name": hint.upper() if len(hint) <= 4 else hint.title(),
                    "type": "api",
                    "category": "software",
                    "description": f"Custom software connector for {hint}. Add API docs or auth to generate a richer toolkit.",
                    "status": "not_connected",
                    "provider": "custom",
                "generationStatus": "needs_docs",
                },
            )

    if any(hint in lower for hint in GENERIC_BROWSER_HINTS) and "bopa" not in lower and not draft["agent"]["websiteUrl"]:
        _merge_connector(
            draft,
            {
                "name": "Browser",
                "type": "web",
                "category": "web",
                "description": "Browser runtime connector for web tasks without a structured API.",
                "status": "connected",
            },
        )

    if draft["company"]["name"] and not draft["agent"]["name"]:
        draft["agent"]["name"] = f"{draft['company']['name']} Agent"
    if any(item.get("name") == "BOPA" for item in draft["connectors"]) and not draft["agent"]["websiteUrl"]:
        draft["agent"]["websiteUrl"] = "https://www.bopa.ad/"

    _normalize_custom_connectors(draft, text)
    _refresh_onboarding_questions(draft)
    return draft


def _missing_setup_items(draft: dict[str, Any]) -> list[str]:
    return [
        missing for missing, ok in (
            ("company name", bool(draft["company"].get("name"))),
            ("connectors or systems", bool(draft["connectors"])),
            ("tasks", bool(draft["tasks"])),
        ) if not ok
    ]


def _questions_for_missing(missing: list[str]) -> list[str]:
    if not missing:
        return [
            "Review the draft. If it looks right, create the agent. Otherwise tell me what to change.",
        ]
    questions = []
    if "company name" in missing:
        questions.append("What is the company or project name?")
    if "connectors or systems" in missing:
        questions.append("Which systems should this agent use? Examples: Gmail, SMTP, Holded, Telegram, BOPA, CRM, ERP, dashboard, API docs.")
    if "tasks" in missing:
        questions.append("List the tasks you want this agent to solve, one per line if possible.")
    return questions


def _auth_fields_for_connector(connector: dict[str, Any]) -> list[str]:
    if connector.get("provider") == "custom":
        config = connector.get("config") or {}
        fields = []
        if not config.get("openApiUrl") and not config.get("docsUrl"):
            fields.append("API docs URL or OpenAPI URL")
        fields.append("base URL")
        fields.append("API key/token if required")
        return fields
    return AUTH_REQUIREMENTS.get(str(connector.get("type") or "").lower(), ["credentials or API token"])


def _connectors_by_status(draft: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    connected: list[str] = []
    needs_auth: list[str] = []
    not_connected: list[str] = []
    for connector in draft.get("connectors", []):
        name = str(connector.get("name") or connector.get("type") or "Connector")
        status = str(connector.get("status") or "not_connected")
        if status == "connected":
            connected.append(name)
        elif status == "needs_auth":
            fields = ", ".join(_auth_fields_for_connector(connector))
            needs_auth.append(f"{name} ({fields})")
        else:
            not_connected.append(name)
    return connected, needs_auth, not_connected


def _status_summary(draft: dict[str, Any]) -> str:
    connected, needs_auth, not_connected = _connectors_by_status(draft)
    task_count = len(draft.get("tasks", []))
    lines = [
        f"Working: {', '.join(connected) if connected else 'no connected connectors yet'}.",
        f"Needs auth: {', '.join(needs_auth) if needs_auth else 'none'}.",
        f"Not connected: {', '.join(not_connected) if not_connected else 'none'}.",
        f"Benchmark tasks: {task_count}.",
    ]
    if needs_auth:
        lines.append("Left: add missing auth/docs in connector settings. For custom connectors, provide API docs/OpenAPI URL, or ask Automata to search public docs and generate a toolkit draft.")
    elif draft.get("questions") and "Review the draft" not in draft["questions"][0]:
        lines.append(f"Left: {draft['questions'][0]}")
    else:
        lines.append("Left: review the draft and create the company agent when it looks right.")
    return "\n".join(lines)


def _auth_question(draft: dict[str, Any]) -> str:
    _, needs_auth, _ = _connectors_by_status(draft)
    if not needs_auth:
        return ""
    names = ", ".join(item.split(" (", 1)[0] for item in needs_auth)
    return f"These connectors still need auth or API docs before they can run: {names}. Open Connectors to add credentials/docs, or ask Automata to search public docs and generate a toolkit draft."


def _refresh_onboarding_questions(draft: dict[str, Any]) -> str:
    draft["questions"] = _questions_for_missing(_missing_setup_items(draft))
    auth_question = _auth_question(draft)
    if auth_question and auth_question not in draft["questions"]:
        draft["questions"] = [auth_question, *draft["questions"]]
    return auth_question


def _assistant_message(draft: dict[str, Any]) -> str:
    if draft["questions"] and "Review the draft" not in draft["questions"][0]:
        return f"I updated the onboarding draft.\n{_status_summary(draft)}"
    return f"Draft is ready for {draft['company']['name']}.\n{_status_summary(draft)}"


ONBOARDING_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Emit a short visible status note about what the onboarding agent is deciding. Do not reveal hidden chain-of-thought.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string"}},
                "required": ["note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_company",
            "description": "Set or update the company profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "industry": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_connector",
            "description": "Create or update a connector/toolkit the agent should use.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ONBOARDING_CONNECTOR_TYPES},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "baseUrl": {"type": "string"},
                    "openApiUrl": {"type": "string"},
                    "docsUrl": {"type": "string"},
                },
                "required": ["name", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_agent",
            "description": "Set the specialized company agent metadata and runtime defaults.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "websiteUrl": {"type": "string"},
                    "successCriteria": {"type": "string"},
                    "customInstructions": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a benchmark task the agent should learn/evaluate. Use a short descriptive name, not Task 1 or Task 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {"type": "string"},
                    "successCriteria": {"type": "string"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish this onboarding turn with a concise user-facing summary.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


def _event(kind: str, content: str, *, tool_name: str = "", status: str = "completed") -> dict[str, Any]:
    return {
        "role": "event",
        "kind": kind,
        "content": content,
        "toolName": tool_name,
        "status": status,
        "createdAt": _now(),
    }


def _apply_tool_call(draft: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "think":
        return str(args.get("note") or "Thinking through the setup.")

    if name == "set_company":
        if args.get("name"):
            draft["company"]["name"] = str(args["name"]).strip()
        if args.get("industry"):
            draft["company"]["industry"] = str(args["industry"]).strip()
        if args.get("description"):
            draft["company"]["description"] = str(args["description"]).strip()
        if draft["company"].get("name") and not draft["agent"].get("name"):
            draft["agent"]["name"] = f"{draft['company']['name']} Agent"
        return f"Updated company: {draft['company'].get('name') or 'Untitled Company'}"

    if name == "add_connector":
        connector_type = str(args.get("type") or "api").lower()
        connector_name = str(args.get("name") or connector_type.title()).strip()
        base_url = str(args.get("baseUrl") or "").strip()
        openapi_url = str(args.get("openApiUrl") or "").strip()
        docs_url = str(args.get("docsUrl") or "").strip()
        known_key = connector_type if connector_type in KNOWN_CONNECTORS else connector_name.lower()
        connector = _known_connector(known_key) if known_key in KNOWN_CONNECTORS else {
            "name": connector_name,
            "type": connector_type,
            "category": args.get("category") or ("api" if connector_type == "api" else "software"),
            "description": args.get("description") or f"Custom {connector_type} connector for {connector_name}. Add docs/auth so Automata can generate and test its toolkit.",
            "status": "connected" if connector_type in {"web", "knowledge"} else "not_connected",
            "provider": "custom" if connector_type == "api" else "official",
            "generationStatus": "needs_docs" if connector_type == "api" else "autoppia_supported",
            "config": {},
        }
        connector["name"] = connector_name
        connector["category"] = args.get("category") or connector.get("category", "software")
        connector["description"] = args.get("description") or connector.get("description", "")
        if base_url:
            connector.setdefault("config", {})["baseUrl"] = base_url
        if openapi_url:
            connector.setdefault("config", {})["openApiUrl"] = openapi_url
            connector["generationStatus"] = "docs_provided"
        if docs_url:
            connector.setdefault("config", {})["docsUrl"] = docs_url
            connector["generationStatus"] = "docs_provided"
        _merge_connector(draft, connector)
        if base_url and not draft["agent"].get("websiteUrl"):
            draft["agent"]["websiteUrl"] = base_url
        return f"Created connector/toolkit: {connector_name}"

    if name == "set_agent":
        if args.get("name"):
            draft["agent"]["name"] = str(args["name"]).strip()
        elif draft["company"].get("name") and not draft["agent"].get("name"):
            draft["agent"]["name"] = f"{draft['company']['name']} Agent"
        if args.get("websiteUrl"):
            draft["agent"]["websiteUrl"] = str(args["websiteUrl"]).strip()
        if args.get("successCriteria"):
            draft["agent"]["successCriteria"] = str(args["successCriteria"]).strip()
        if args.get("customInstructions"):
            draft["agent"]["customInstructions"] = str(args["customInstructions"]).strip()
        return f"Prepared agent: {draft['agent'].get('name') or 'Company Agent'}"

    if name == "add_task":
        prompt = str(args.get("prompt") or "").strip()
        if prompt and not any(existing["prompt"].lower() == prompt.lower() for existing in draft["tasks"]):
            task_name = str(args.get("name") or "").strip()
            draft["tasks"].append(
                {
                    "name": task_name if task_name and not re.fullmatch(r"Task\s+\d+", task_name, flags=re.IGNORECASE) else task_name_from_prompt(prompt, len(draft["tasks"]) + 1),
                    "prompt": prompt,
                    "successCriteria": str(args.get("successCriteria") or "The user approves the result and all sensitive writes are confirmed before execution.").strip(),
                    "status": "draft",
                }
            )
        return f"Created benchmark task: {prompt[:80]}"

    if name == "finish":
        return str(args.get("summary") or _assistant_message(draft))

    return f"Unknown tool ignored: {name}"


async def _run_llm_onboarding_agent(draft: dict[str, Any], user_message: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from openai import OpenAI

    visible_events: list[dict[str, Any]] = [_event("thinking", "Reading your company description and planning the setup.")]
    system = (
        "You are Automata's onboarding agent. Convert the user's natural language into a structured company agent setup. "
        "You must use tools to update the draft: set_company, add_connector, set_agent, add_task, then finish. "
        "Create connectors for every system mentioned. Known connector types are gmail, smtp, holded, telegram, web, knowledge, api. "
        "Use api for unknown SaaS/API systems and web for browser-only websites. Use knowledge for documents or files. "
        "Create one add_task tool call for each distinct workflow or requested task. Do not merge multiple workflows into one task. "
        "Give every task a concrete 3-7 word name based on the workflow, never generic names like Task 1 or Task 2. "
        "If the system is not an official known connector, still create it as a custom api connector. Ask for API docs/OpenAPI URL and auth, or say Automata can search public docs to draft the toolkit. "
        "In the final summary, explain what is working, what is not connected, what needs auth, and what is left. "
        "Connectors that need auth are not working yet; ask the user to configure their credentials in connector settings instead of pretending they are connected. "
        "Keep visible thinking short and operational; do not reveal hidden chain-of-thought."
    )
    client = OpenAI(api_key=api_key)
    response_tools = [
        {
            "type": "function",
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "parameters": {
                **tool["function"]["parameters"],
                "additionalProperties": False,
            },
        }
        for tool in ONBOARDING_TOOLS
    ]

    final_summary = ""
    previous_response_id = ""
    next_input: Any = f"Current draft JSON:\n{json.dumps(draft, ensure_ascii=False)}\n\nUser onboarding message:\n{user_message}"
    for _ in range(10):
        require_tool = not (draft["company"].get("name") and draft["connectors"] and draft["tasks"])
        def _create_response():
            kwargs: dict[str, Any] = {
                "model": ONBOARDING_MODEL,
                "instructions": system,
                "input": next_input,
                "tools": response_tools,
                "tool_choice": "required" if require_tool else "auto",
                "parallel_tool_calls": False,
                "max_output_tokens": 1400,
            }
            if previous_response_id:
                kwargs["previous_response_id"] = previous_response_id
            return client.responses.create(**kwargs)

        response = await asyncio.to_thread(_create_response)
        previous_response_id = response.id
        function_calls = [item for item in response.output if getattr(item, "type", "") == "function_call"]
        if not function_calls:
            final_summary = getattr(response, "output_text", "") or final_summary
            break

        function_outputs: list[dict[str, str]] = []
        for call in function_calls:
            name = call.name
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            status_text = {
                "think": args.get("note") or "Thinking through the setup.",
                "set_company": f"Updating company profile: {args.get('name') or draft['company'].get('name') or 'Untitled'}",
                "add_connector": f"Creating connector: {args.get('name') or args.get('type') or 'Connector'}",
                "set_agent": f"Preparing agent: {args.get('name') or draft['agent'].get('name') or 'Company Agent'}",
                "add_task": f"Creating benchmark task: {str(args.get('prompt') or '')[:80]}",
                "finish": "Reviewing the draft and preparing the summary.",
            }.get(name, f"Calling tool: {name}")
            visible_events.append(_event("thinking" if name == "think" else "tool_call", status_text, tool_name=name))
            result = _apply_tool_call(draft, name, args)
            visible_events.append(_event("tool_result", result, tool_name=name))
            if name == "finish":
                final_summary = result
            function_outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": result})
        next_input = function_outputs
        if final_summary:
            break

    visible_events.extend(_ensure_extracted_setup(draft, user_message))
    visible_events.extend(_ensure_extracted_tasks(draft, user_message))
    _normalize_custom_connectors(draft, user_message)
    visible_events = _prune_stale_task_events(visible_events, draft)
    auth_question = _refresh_onboarding_questions(draft)
    if auth_question:
        visible_events.extend(
            [
                _event("tool_call", "Checking connector auth status.", tool_name="check_connector_auth"),
                _event("tool_result", auth_question, tool_name="check_connector_auth"),
            ]
        )
    summary = final_summary or _assistant_message(draft)
    status_summary = _status_summary(draft)
    if "Needs auth:" not in summary and "Working:" not in summary:
        summary = f"{summary}\n\n{status_summary}"
    visible_events.append(_event("assistant_summary", summary))
    return draft, visible_events


async def _run_onboarding_agent(draft: dict[str, Any], user_message: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        return await _run_llm_onboarding_agent(draft, user_message)
    except Exception as exc:
        fallback_draft = draft
        setup_events = _ensure_extracted_setup(fallback_draft, user_message)
        task_events = _ensure_extracted_tasks(fallback_draft, user_message)
        _normalize_custom_connectors(fallback_draft, user_message)
        auth_question = _refresh_onboarding_questions(fallback_draft)
        auth_events = [
            _event("tool_call", "Checking connector auth status.", tool_name="check_connector_auth"),
            _event("tool_result", auth_question, tool_name="check_connector_auth"),
        ] if auth_question else []
        return fallback_draft, [
            _event("thinking", "I could not reach the model, so I used the local onboarding parser.", status="completed"),
            _event("tool_result", f"Fallback parser updated the draft: {exc.__class__.__name__}", tool_name="local_parser"),
            *setup_events,
            *task_events,
            *auth_events,
            _event("assistant_summary", _assistant_message(fallback_draft)),
        ]


def _session_payload(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": doc.get("sessionId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "messages": doc.get("messages", []),
        "draft": doc.get("draft", _default_draft()),
        "status": doc.get("status", "collecting"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _create_eval(
    *,
    email: str,
    agent_id: str,
    agent_name: str,
    website_url: str,
    task: dict[str, Any],
) -> str:
    now = _now()
    eval_id = str(uuid.uuid4())
    await evals_collection.insert_one(
        {
            "evalId": eval_id,
            "email": email,
            "prompt": task["prompt"],
            "initialUrl": website_url,
            "benchmarkId": f"agent-{agent_id}",
            "benchmarkName": f"{agent_name} Benchmark",
            "agentId": agent_id,
            "agentName": agent_name,
            "agentTaskName": task["name"],
            "successCriteria": task.get("successCriteria", ""),
            "createdAt": now,
        }
    )
    return eval_id


@router.post("/onboarding/sessions")
async def start_onboarding(body: OnboardingStartRequest):
    draft = _default_draft()
    if body.companyId:
        company = await companies_collection.find_one({"companyId": body.companyId, "email": body.email}, {"_id": 0})
        if company:
            draft["company"] = {
                "name": company.get("name", ""),
                "industry": company.get("industry", ""),
                "description": company.get("description", ""),
            }
            if company.get("name"):
                draft["agent"]["name"] = f"{company['name']} Agent"
    messages = [
        {
            "role": "assistant",
            "content": "Please explain what this company do for me to create the whole setup.",
            "createdAt": _now(),
        }
    ]
    if body.seedPrompt.strip():
        draft = _apply_message(draft, body.seedPrompt)
    now = _now()
    status = "ready" if draft["company"]["name"] and draft["connectors"] and draft["tasks"] else "collecting"
    doc = {
        "sessionId": str(uuid.uuid4()),
        "email": body.email,
        "companyId": body.companyId,
        "messages": messages,
        "draft": draft,
        "status": status,
        "createdAt": now,
        "updatedAt": now,
    }
    await onboarding_sessions_collection.insert_one(doc)
    return {"session": _session_payload(doc)}


@router.post("/onboarding/sessions/{session_id}/messages")
async def send_onboarding_message(session_id: str, body: OnboardingMessageRequest):
    doc = await onboarding_sessions_collection.find_one({"sessionId": session_id, "email": body.email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    draft = doc.get("draft") or _default_draft()
    messages = doc.get("messages", [])
    messages.append({"role": "user", "content": body.message.strip(), "createdAt": _now()})
    draft, agent_events = await _run_onboarding_agent(draft, body.message)
    messages.extend(agent_events)
    status = "ready" if draft["company"]["name"] and draft["connectors"] and draft["tasks"] else "collecting"
    await onboarding_sessions_collection.update_one(
        {"sessionId": session_id},
        {"$set": {"draft": draft, "messages": messages, "status": status, "updatedAt": _now()}},
    )
    return {"session": {**_session_payload(doc), "messages": messages, "draft": draft, "status": status, "updatedAt": _now()}}


@router.post("/onboarding/sessions/{session_id}/finalize")
async def finalize_onboarding(session_id: str, body: OnboardingFinalizeRequest):
    doc = await onboarding_sessions_collection.find_one({"sessionId": session_id, "email": body.email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    draft = body.draft or doc.get("draft") or _default_draft()
    if not draft.get("company", {}).get("name"):
        raise HTTPException(status_code=400, detail="Company name is required")
    if not draft.get("tasks"):
        raise HTTPException(status_code=400, detail="At least one task is required")
    if not draft.get("connectors"):
        raise HTTPException(status_code=400, detail="At least one connector is required")

    now = _now()
    existing_company_id = str(doc.get("companyId") or "").strip()
    if existing_company_id:
        company_id = existing_company_id
        update = {
            "name": draft["company"].get("name", "Untitled Company").strip(),
            "description": draft["company"].get("description", "").strip(),
            "industry": draft["company"].get("industry", "").strip(),
            "updatedAt": now,
        }
        await companies_collection.update_one(
            {"companyId": company_id, "email": body.email},
            {"$set": update},
        )
        company = await companies_collection.find_one({"companyId": company_id}, {"_id": 0}) or {
            "companyId": company_id,
            "email": body.email,
            "status": "active",
            "createdAt": now,
            **update,
        }
    else:
        company_id = str(uuid.uuid4())
        company = {
            "companyId": company_id,
            "email": body.email,
            "name": draft["company"].get("name", "Untitled Company").strip(),
            "description": draft["company"].get("description", "").strip(),
            "industry": draft["company"].get("industry", "").strip(),
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        await companies_collection.insert_one(dict(company))

    connectors = []
    for item in draft.get("connectors", []):
        connector_id = str(uuid.uuid4())
        status = item.get("status") or ("connected" if item.get("type") in ("web", "knowledge") else "not_connected")
        connector = {
            "connectorId": connector_id,
            "email": body.email,
            "companyId": company_id,
            "name": item.get("name", "Connector"),
            "type": item.get("type", "api"),
            "category": item.get("category", "software"),
            "description": item.get("description", ""),
            "status": status,
            "config": item.get("config", {}),
            "provider": item.get("provider", "custom" if item.get("type") == "api" else "official"),
            "generationStatus": item.get("generationStatus", "needs_docs" if item.get("type") == "api" and item.get("provider") == "custom" else "autoppia_supported"),
            "createdAt": now,
            "updatedAt": now,
        }
        await connectors_collection.insert_one(dict(connector))
        connectors.append(connector)

    agent_id = str(uuid.uuid4())
    runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else ""
    agent = draft.get("agent", {})
    agent_name = agent.get("name") or f"{company['name']} Agent"
    website_url = agent.get("websiteUrl") or next(
        (str(connector.get("config", {}).get("baseUrl")) for connector in connectors if connector.get("config", {}).get("baseUrl")),
        "",
    )
    tasks = []
    for index, task in enumerate(draft.get("tasks", []), start=1):
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        tasks.append(
            {
                "name": task_name_from_prompt(prompt, index) if not task.get("name") or re.fullmatch(r"Task\s+\d+", str(task.get("name") or ""), flags=re.IGNORECASE) else task.get("name"),
                "prompt": prompt,
                "successCriteria": task.get("successCriteria", "The user confirms the result."),
                "status": "draft",
                "trajectoryId": "",
            }
        )

    agent_config = {
        "agentId": agent_id,
        "email": body.email,
        "companyId": company_id,
        "name": agent_name,
        "websiteUrl": website_url,
        "runtimeEndpoint": runtime_endpoint,
        "baseRuntimeEndpoint": DEFAULT_OPERATOR_RUNTIME_ENDPOINT,
        "runtimeType": DEFAULT_OPERATOR_RUNTIME_TYPE if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "pending",
        "status": "ready" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "draft",
        "trainingStatus": "needs_trajectories",
        "harvester": "Automata Onboarding Agent",
        "runtimeCapabilities": {
            "browser": any(connector.get("type") == "web" for connector in connectors),
            "apiCalls": any(connector.get("type") in ("api", "holded", "gmail", "smtp", "telegram") for connector in connectors),
            "knowledge": any(connector.get("type") == "knowledge" for connector in connectors),
            "python": False,
            "humanApprovalForWrites": True,
        },
        "tasks": tasks,
        "trajectories": [],
        "successCriteria": agent.get("successCriteria", ""),
        "customInstructions": agent.get("customInstructions", ""),
        "createdAt": now,
        "updatedAt": now,
    }
    await agents_collection.insert_one(dict(agent_config))
    await ensure_agent_creation_job(agent_config)

    web_id = f"default-{agent_id}"
    await agent_webs_collection.insert_one(
        {
            "webId": web_id,
            "agentId": agent_id,
            "email": body.email,
            "name": company["name"],
            "baseUrl": website_url,
            "authRequired": False,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    eval_ids = []
    trajectory_ids = []
    for task in tasks:
        trajectory_id = str(uuid.uuid4())
        trajectory_ids.append(trajectory_id)
        await trajectories_collection.insert_one(
            {
                "trajectoryId": trajectory_id,
                "agentId": agent_id,
                "email": body.email,
                "webId": web_id,
                "taskName": task["name"],
                "prompt": task["prompt"],
                "successCriteria": task.get("successCriteria", ""),
                "source": "onboarding_agent",
                "status": "needs_harvest",
                "actions": [],
                "screenshots": [],
                "createdAt": now,
                "updatedAt": now,
            }
        )
        eval_ids.append(
            await _create_eval(
                email=body.email,
                agent_id=agent_id,
                agent_name=agent_name,
                website_url=website_url,
                task=task,
            )
        )

    await onboarding_sessions_collection.update_one(
        {"sessionId": session_id},
        {
            "$set": {
                "status": "finalized",
                "companyId": company_id,
                "agentId": agent_id,
                "updatedAt": _now(),
            }
        },
    )
    return {
        "success": True,
        "company": company,
        "agentId": agent_id,
        "connectorIds": [connector["connectorId"] for connector in connectors],
        "trajectoryIds": trajectory_ids,
        "evalIds": eval_ids,
    }
