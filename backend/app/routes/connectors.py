import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import companies_collection, connectors_collection

router = APIRouter()


CONNECTOR_TOOLKIT_DEFAULTS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail Toolkit",
        "runtimeRequirements": ["oauth:gmail", "network"],
        "tools": [
            {"name": "gmail.search_emails", "description": "Search client emails.", "sideEffects": "reads"},
            {"name": "gmail.read_email", "description": "Read an email thread.", "sideEffects": "reads"},
            {"name": "gmail.send_email", "description": "Send an email after approval.", "sideEffects": "writes"},
        ],
    },
    "holded": {
        "name": "Holded Toolkit",
        "runtimeRequirements": ["api_credentials", "network"],
        "tools": [
            {"name": "holded.search_clients", "description": "Search clients in Holded.", "sideEffects": "reads"},
            {"name": "holded.get_invoice", "description": "Fetch an invoice.", "sideEffects": "reads"},
        ],
    },
    "telegram": {
        "name": "Telegram Toolkit",
        "runtimeRequirements": ["bot_token", "network"],
        "tools": [
            {"name": "telegram.send_message", "description": "Send a Telegram message after approval.", "sideEffects": "writes"},
        ],
    },
    "web": {
        "name": "Web Toolkit",
        "runtimeRequirements": ["browser_or_http", "network"],
        "tools": [
            {"name": "web.fetch", "description": "Fetch a public page.", "sideEffects": "reads"},
            {"name": "browser.navigate", "description": "Open a website in browser runtime.", "sideEffects": "reads"},
        ],
    },
    "knowledge": {
        "name": "Knowledge Toolkit",
        "runtimeRequirements": ["vectorstore", "embedding_model"],
        "tools": [
            {"name": "knowledge.search", "description": "Search company documents.", "sideEffects": "none"},
            {"name": "knowledge.read_document", "description": "Read a document chunk.", "sideEffects": "none"},
        ],
    },
    "api": {
        "name": "API Toolkit",
        "runtimeRequirements": ["openapi_optional", "network"],
        "tools": [
            {"name": "api.call", "description": "Call an approved API endpoint.", "sideEffects": "writes"},
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


class ConnectorUpdateRequest(BaseModel):
    name: str
    type: str = "api"
    category: str = "software"
    description: str = ""
    status: str = "not_connected"
    config: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connector_toolkit(connector: dict[str, Any]) -> dict[str, Any]:
    connector_type = str(connector.get("type") or "api").lower()
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    toolkit_id = f"{connector.get('connectorId')}:toolkit"
    return {
        "toolkitId": toolkit_id,
        "connectorId": connector.get("connectorId", ""),
        "name": defaults["name"],
        "connectorName": connector.get("name", ""),
        "category": connector.get("category", "software"),
        "status": connector.get("status", "not_connected"),
        "runtimeRequirements": defaults["runtimeRequirements"],
        "tools": defaults["tools"],
    }


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
        "config": doc.get("config", {}),
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
        "createdAt": now,
        "updatedAt": now,
    }
    await connectors_collection.insert_one(doc)
    return {"success": True, "connector": _serialize(doc)}


@router.put("/connectors/{connector_id}")
async def update_connector(connector_id: str, body: ConnectorUpdateRequest):
    now = _now()
    update = {
        "name": body.name.strip() or "Untitled Connector",
        "type": body.type.strip().lower() or "api",
        "category": body.category.strip() or "software",
        "description": body.description.strip(),
        "status": body.status,
        "config": body.config,
        "updatedAt": now,
    }
    result = await connectors_collection.update_one({"connectorId": connector_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Connector not found")
    doc = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    return {"success": True, "connector": _serialize(doc or {"connectorId": connector_id, **update})}


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str):
    result = await connectors_collection.delete_one({"connectorId": connector_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"success": True}
