from __future__ import annotations

from typing import Any, Type

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorExecutionError
from app.connectors.implementations import (
    GenericApiConnector,
    GmailConnector,
    HoldedConnector,
    KnowledgeConnector,
    SMTPConnector,
    TelegramConnector,
    WebConnector,
)
from app.database import connectors_collection
from app.routes.connectors import connector_toolkit
from app.routes.credentials import resolve_secret_refs
from app.services.credentials import resolve_secret_refs_deep


CONNECTOR_CLASSES: dict[str, Type[BaseConnector]] = {
    "api": GenericApiConnector,
    "openai": GenericApiConnector,
    "weather": GenericApiConnector,
    "google": GenericApiConnector,
    "taostats": GenericApiConnector,
    "aws": GenericApiConnector,
    "runpod": GenericApiConnector,
    "contabo": GenericApiConnector,
    "cloudflare": GenericApiConnector,
    "kubernetes": GenericApiConnector,
    "slack": GenericApiConnector,
    "discord": GenericApiConnector,
    "matrix": GenericApiConnector,
    "signal": GenericApiConnector,
    "teams": GenericApiConnector,
    "whatsapp": GenericApiConnector,
    "github": GenericApiConnector,
    "gitlab": GenericApiConnector,
    "jira": GenericApiConnector,
    "google_calendar": GenericApiConnector,
    "google_drive": GenericApiConnector,
    "confluence": GenericApiConnector,
    "asana": GenericApiConnector,
    "notion": GenericApiConnector,
    "trello": GenericApiConnector,
    "linear": GenericApiConnector,
    "postgres": GenericApiConnector,
    "mongodb": GenericApiConnector,
    "twitter": GenericApiConnector,
    "twitterapi": GenericApiConnector,
    "bittensor_directory": GenericApiConnector,
    "bittensor_subnet_vendor": GenericApiConnector,
    "bittensor_desearch": GenericApiConnector,
    "bittensor_datauniverse": GenericApiConnector,
    "bittensor_chutes": GenericApiConnector,
    "bittensor_computehorde": GenericApiConnector,
    "gmail": GmailConnector,
    "smtp": SMTPConnector,
    "holded": HoldedConnector,
    "telegram": TelegramConnector,
    "knowledge": KnowledgeConnector,
    "web": WebConnector,
}


def _tool_prefix(tool_name: str) -> str:
    return tool_name.split(".", 1)[0].lower()


def _connector_config(doc: dict[str, Any], resolved: dict[str, str]) -> ConnectorConfig:
    config = dict(doc.get("config") or {})
    config.update(resolved)
    return ConnectorConfig(
        connector_id=str(doc.get("connectorId") or ""),
        company_id=str(doc.get("companyId") or ""),
        email=str(doc.get("email") or ""),
        name=str(doc.get("name") or doc.get("type") or "Connector"),
        type=str(doc.get("type") or "api").lower(),
        status=str(doc.get("status") or "not_connected"),
        config=config,
    )


async def connector_for(doc: dict[str, Any]) -> BaseConnector:
    connector_type = str(doc.get("type") or "api").lower()
    cls = CONNECTOR_CLASSES.get(connector_type, GenericApiConnector)
    resolved = await resolve_secret_refs(doc.get("credentialRefs") or {})
    config_doc = dict(doc)
    config_doc["config"] = await resolve_secret_refs_deep(dict(doc.get("config") or {}))
    return cls(_connector_config(config_doc, resolved))


async def find_connector_for_tool(*, company_id: str, tool_name: str) -> dict[str, Any] | None:
    prefix = _tool_prefix(tool_name)
    cursor = connectors_collection.find({"companyId": company_id}, {"_id": 0}).sort("createdAt", 1)
    async for connector in cursor:
        toolkit = connector_toolkit(connector)
        names = {str(tool.get("name") or "") for tool in toolkit.get("tools", [])}
        if tool_name in names:
            return connector
        connector_type = str(connector.get("type") or "").lower()
        if prefix == connector_type:
            return connector
        if prefix == "api" and connector_type == "api":
            return connector
    return None


async def execute_connector_tool(*, company_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    connector_doc = await find_connector_for_tool(company_id=company_id, tool_name=tool_name)
    if not connector_doc:
        raise ConnectorExecutionError(f"No connector in this company exposes {tool_name}")
    connector = await connector_for(connector_doc)
    result = await connector.execute(tool_name, arguments)
    return result.model_dump()
