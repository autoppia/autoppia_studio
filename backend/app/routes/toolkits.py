from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import capabilities_collection, operators_collection

router = APIRouter()


def _tool(name: str, description: str, side_effects: str = "reads") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "sideEffects": side_effects,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    }


async def _operator(operator_id: str) -> dict[str, Any]:
    operator = await operators_collection.find_one({"operatorId": operator_id}, {"_id": 0})
    if not operator:
        raise HTTPException(status_code=404, detail="Agent not found")
    return operator


@router.get("/agents/{operator_id}/toolkits")
async def list_agent_toolkits(operator_id: str):
    operator = await _operator(operator_id)
    skills = await capabilities_collection.count_documents({"operatorId": operator_id})
    runtime = operator.get("runtimeCapabilities") or {}
    browser_enabled = bool(runtime.get("browser", True))
    api_enabled = bool(runtime.get("apiCalls", True) or operator.get("apiSpecUrl"))
    knowledge_enabled = bool(runtime.get("knowledge", False))
    python_enabled = bool(runtime.get("python", False))

    toolkits: list[dict[str, Any]] = []
    if browser_enabled:
        toolkits.append({
            "toolkitId": f"{operator_id}:browser",
            "name": "Browser Toolkit",
            "integrationName": "Browser Runtime",
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
            "toolkitId": f"{operator_id}:api",
            "name": "API Toolkit",
            "integrationName": "OpenAPI / HTTP",
            "category": "api",
            "runtimeRequirements": ["network", "api_credentials_optional"],
            "permissions": {"network": True, "sideEffects": "writes_possible"},
            "tools": [_tool("api.call", "Call an approved API endpoint.", "writes")],
        })
    if knowledge_enabled:
        toolkits.append({
            "toolkitId": f"{operator_id}:knowledge",
            "name": "Knowledge Toolkit",
            "integrationName": "Company Knowledge",
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
            "toolkitId": f"{operator_id}:python",
            "name": "Python Toolkit",
            "integrationName": "Python Runtime",
            "category": "runtime",
            "runtimeRequirements": ["sandboxed_python"],
            "permissions": {"codeExecution": True, "sideEffects": "none"},
            "tools": [_tool("python.execute", "Run sandboxed Python for analysis.", "none")],
        })
    if skills:
        toolkits.append({
            "toolkitId": f"{operator_id}:skills",
            "name": "Skills Toolkit",
            "integrationName": "Approved Training Traces",
            "category": "skills",
            "runtimeRequirements": ["skill_registry"],
            "permissions": {"sideEffects": "inherits_skill"},
            "tools": [_tool("skill.run", "Run an approved reusable skill.", "writes")],
        })

    return {"toolkits": toolkits}
