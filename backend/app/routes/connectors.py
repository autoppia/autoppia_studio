import uuid
from datetime import datetime, timezone
import smtplib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import companies_collection, connectors_collection

router = APIRouter()
SECRET_PLACEHOLDER = "__configured__"


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
            {"name": "smtp.send_email", "description": "Send an email through SMTP after approval.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
            {"name": "imap.read_email", "description": "Read email through IMAP when configured.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"folder": {"type": "string"}, "limit": {"type": "integer"}}}},
        ],
    },
    "holded": {
        "name": "Holded Toolkit",
        "authFields": ["apiKey"],
        "configFields": ["workspaceId"],
        "runtimeRequirements": ["api_credentials", "network"],
        "tools": [
            {"name": "holded.search_clients", "description": "Search clients in Holded.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "holded.get_invoice", "description": "Fetch an invoice.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"invoiceId": {"type": "string"}}}},
        ],
    },
    "telegram": {
        "name": "Telegram Toolkit",
        "authFields": ["botToken", "chatId"],
        "configFields": ["defaultChatId"],
        "runtimeRequirements": ["bot_token", "network"],
        "tools": [
            {"name": "telegram.send_message", "description": "Send a Telegram message after approval.", "sideEffects": "writes", "inputSchema": {"type": "object", "properties": {"chatId": {"type": "string"}, "message": {"type": "string"}}}},
        ],
    },
    "web": {
        "name": "Web Toolkit",
        "authFields": [],
        "configFields": ["baseUrl", "authUsername", "authPassword"],
        "runtimeRequirements": ["browser_or_http", "network"],
        "tools": [
            {"name": "web.fetch", "description": "Fetch a public page.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
            {"name": "browser.navigate", "description": "Open a website in browser runtime.", "sideEffects": "reads", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
        ],
    },
    "knowledge": {
        "name": "Knowledge Toolkit",
        "authFields": [],
        "configFields": ["collectionName", "sourceUrl"],
        "runtimeRequirements": ["vectorstore", "embedding_model"],
        "tools": [
            {"name": "knowledge.search", "description": "Search company documents.", "sideEffects": "none", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
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


class ConnectorUpdateRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    category: str | None = None
    description: str | None = None
    status: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    generationStatus: str | None = None


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
        "authFields": defaults["authFields"],
        "configFields": defaults["configFields"],
        "tools": tools,
    }


def _is_secret_field(field: str) -> bool:
    value = field.lower()
    return any(token in value for token in ("password", "secret", "token", "apikey", "api_key", "key"))


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, value in (config or {}).items():
        public[key] = SECRET_PLACEHOLDER if value and _is_secret_field(key) else value
    return public


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
        "config": _public_config(doc.get("config", {})),
        "lastTestAt": doc.get("lastTestAt"),
        "lastTestStatus": doc.get("lastTestStatus"),
        "lastTestMessage": doc.get("lastTestMessage"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }
    connector["toolkit"] = connector_toolkit(connector)
    return connector


async def _ensure_company(company_id: str) -> None:
    if not await companies_collection.find_one({"companyId": company_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Company not found")


@router.get("/connectors")
async def list_connectors(email: str, companyId: str):
    await _ensure_company(companyId)
    cursor = connectors_collection.find({"email": email, "companyId": companyId}, {"_id": 0}).sort("createdAt", 1)
    return {"connectors": [_serialize(doc) async for doc in cursor]}


@router.post("/connectors")
async def create_connector(body: ConnectorCreateRequest):
    await _ensure_company(body.companyId)
    now = _now()
    doc = {
        "connectorId": str(uuid.uuid4()),
        "email": body.email,
        "companyId": body.companyId,
        "name": body.name.strip() or "Untitled Connector",
        "type": body.type.strip().lower() or "api",
        "category": body.category.strip() or "software",
        "description": body.description.strip(),
        "status": body.status,
        "config": body.config,
        "provider": body.provider or ("custom" if body.type.strip().lower() == "api" else "official"),
        "generationStatus": body.generationStatus or ("needs_docs" if (body.provider == "custom" or body.type.strip().lower() == "api") else "autoppia_supported"),
        "createdAt": now,
        "updatedAt": now,
    }
    await connectors_collection.insert_one(doc)
    return {"success": True, "connector": _serialize(doc)}


@router.put("/connectors/{connector_id}")
async def update_connector(connector_id: str, body: ConnectorUpdateRequest):
    now = _now()
    existing = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")

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
    if body.config is not None:
        existing_config = existing.get("config") or {}
        next_config: dict[str, Any] = {}
        for key, value in body.config.items():
            if _is_secret_field(key) and value == SECRET_PLACEHOLDER:
                next_config[key] = existing_config.get(key, "")
            else:
                next_config[key] = value
        update["config"] = next_config
        provider = body.provider or existing.get("provider", "custom" if existing.get("type") == "api" else "official")
        connector_type = body.type or existing.get("type", "api")
        if connector_type == "api" and provider == "custom" and (next_config.get("openApiUrl") or next_config.get("docsUrl")) and body.generationStatus is None:
            update["generationStatus"] = "docs_provided"
    result = await connectors_collection.update_one({"connectorId": connector_id}, {"$set": update})
    doc = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    return {"success": True, "connector": _serialize(doc or {"connectorId": connector_id, **update})}


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str):
    result = await connectors_collection.delete_one({"connectorId": connector_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"success": True}


@router.post("/connectors/{connector_id}/test")
async def test_connector(connector_id: str):
    doc = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Connector not found")

    connector_type = str(doc.get("type") or "api").lower()
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    config = doc.get("config") or {}
    required_auth = defaults.get("authFields") or []
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
