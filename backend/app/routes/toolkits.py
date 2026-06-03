from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import capabilities_collection, connectors_collection, agents_collection
from app.routes.connectors import connector_toolkit

router = APIRouter()


def _tool(name: str, description: str, side_effects: str = "reads") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "sideEffects": side_effects,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    }


async def _agent_config(agent_id: str) -> dict[str, Any]:
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_config


@router.get("/agents/{agent_id}/toolkits")
async def list_agent_toolkits(agent_id: str):
    agent_config = await _agent_config(agent_id)
    skills = await capabilities_collection.count_documents({"agentId": agent_id})
    runtime = agent_config.get("runtimeCapabilities") or {}
    browser_enabled = bool(runtime.get("browser", True))
    api_enabled = bool(runtime.get("apiCalls", True) or agent_config.get("apiSpecUrl"))
    knowledge_enabled = bool(runtime.get("knowledge", False))
    python_enabled = bool(runtime.get("python", False))

    toolkits: list[dict[str, Any]] = []
    if browser_enabled:
        toolkits.append({
            "toolkitId": f"{agent_id}:browser",
            "name": "Browser Toolkit",
            "connectorName": "Browser Runtime",
            "category": "runtime",
            "runtimeRequirements": ["browser_session", "network"],
            "permissions": {"browser": True, "network": True, "sideEffects": "writes_possible"},
            "tools": [
                _tool("browser.navigate", "Open a page in the browser."),
                _tool("browser.click", "Click a visible page element.", "writes"),
                _tool("browser.input", "Type text into a page field.", "writes"),
                _tool("browser.extract", "Extract visible page data.", "reads"),
            ],
        })
    if api_enabled:
        toolkits.append({
            "toolkitId": f"{agent_id}:api",
            "name": "API Toolkit",
            "connectorName": "OpenAPI / HTTP",
            "category": "api",
            "runtimeRequirements": ["network", "api_credentials_optional"],
            "permissions": {"network": True, "sideEffects": "writes_possible"},
            "tools": [_tool("api.call", "Call an approved API endpoint.", "writes")],
        })
    if knowledge_enabled:
        toolkits.append({
            "toolkitId": f"{agent_id}:knowledge",
            "name": "Knowledge Toolkit",
            "connectorName": "Company Knowledge",
            "category": "knowledge",
            "runtimeRequirements": ["vectorstore", "embedding_model"],
            "permissions": {"knowledge": True, "sideEffects": "none"},
            "tools": [
                _tool("knowledge.search", "Search company documents.", "none"),
                _tool("knowledge.read_document", "Read a referenced document chunk.", "none"),
            ],
        })
    if python_enabled:
        toolkits.append({
            "toolkitId": f"{agent_id}:python",
            "name": "Python Toolkit",
            "connectorName": "Python Runtime",
            "category": "runtime",
            "runtimeRequirements": ["sandboxed_python"],
            "permissions": {"codeExecution": True, "sideEffects": "none"},
            "tools": [_tool("python.execute", "Run sandboxed Python for analysis.", "none")],
        })
    if skills:
        toolkits.append({
            "toolkitId": f"{agent_id}:skills",
            "name": "Skills Toolkit",
            "connectorName": "Approved Training Traces",
            "category": "skills",
            "runtimeRequirements": ["skill_registry"],
            "permissions": {"sideEffects": "inherits_skill"},
            "tools": [_tool("skill.run", "Run an approved reusable skill.", "writes")],
        })

    company_id = agent_config.get("companyId")
    if company_id:
        cursor = connectors_collection.find({"companyId": company_id}, {"_id": 0}).sort("createdAt", 1)
        async for connector in cursor:
            toolkit = connector_toolkit(connector)
            toolkit["permissions"] = {"sideEffects": "inherits_connector", "connectorId": connector.get("connectorId")}
            toolkits.append(toolkit)

    return {"toolkits": toolkits}
