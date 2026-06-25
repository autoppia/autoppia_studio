from typing import Any

from app.harvesters.base import BaseHarvester, connector_surface, now_iso, risk_from_side_effects, slug
from app.routes.connectors import connector_toolkit
from app.services.tool_contracts import apply_tool_contract


class ToolkitHarvester(BaseHarvester):
    """Turns a connector toolkit definition into persisted atomic tools.

    Official connectors already have known toolkits, so this class can publish
    those default tools without running a harvester. Custom/private systems may
    still use the same normalized output while a specialized harvester is being
    developed for that surface.
    """

    def __init__(self, harvester_type: str = "toolkit", source: str = "connector_toolkit"):
        self.harvester_type = harvester_type
        self.source = source

    async def harvest(self, connector: dict[str, Any]) -> dict[str, Any]:
        toolkit = connector_toolkit(connector)
        now = now_iso()
        surface = connector_surface(connector)
        connector_id = str(connector.get("connectorId") or "")
        company_id = str(connector.get("companyId") or "")
        email = str(connector.get("email") or "")

        tools: list[dict[str, Any]] = []
        for raw_tool in toolkit.get("tools", []):
            tool_name = str(raw_tool.get("name") or "tool")
            tool_id = f"{connector_id}:{slug(tool_name)}"
            side_effects = str(raw_tool.get("sideEffects") or "reads")
            execution_type = _execution_type(surface, tool_name)
            runtime_requirements = list(raw_tool.get("runtimeRequirements") or toolkit.get("runtimeRequirements") or [])
            if execution_type == "browser_action" and "browser" not in runtime_requirements:
                runtime_requirements.append("browser")
            contracted_tool = apply_tool_contract(
                raw_tool,
                connector=connector,
                toolkit=toolkit,
                execution_type=execution_type,
                surface=surface,
                runtime_requirements=runtime_requirements,
            )
            tools.append(
                {
                    "toolId": tool_id,
                    "email": email,
                    "companyId": company_id,
                    "connectorId": connector_id,
                    "connectorName": connector.get("name", ""),
                    "name": tool_name,
                    "displayName": tool_name.split(".")[-1].replace("_", " ").title(),
                    "description": raw_tool.get("description", ""),
                    "inputSchema": contracted_tool["inputSchema"],
                    "outputSchema": contracted_tool["outputSchema"],
                    "executionType": execution_type,
                    "surface": surface,
                    "runtimeRequirements": contracted_tool["runtimeRequirements"],
                    "sideEffects": contracted_tool["sideEffects"],
                    "policyBoundary": contracted_tool["policyBoundary"],
                    "inputEntities": contracted_tool["inputEntities"],
                    "outputEntity": contracted_tool["outputEntity"],
                    "outputCard": raw_tool.get("outputCard") if isinstance(raw_tool.get("outputCard"), dict) else {},
                    "permissions": contracted_tool["permissions"],
                    "approvalPolicy": contracted_tool["approvalPolicy"],
                    "scopes": contracted_tool["scopes"],
                    "riskLevel": contracted_tool.get("riskLevel") or risk_from_side_effects(side_effects),
                    "toolContract": contracted_tool["toolContract"],
                    "status": "ready" if connector.get("status") == "connected" or not toolkit.get("authFields") else "needs_connector_auth",
                    "source": self.source,
                    "harvesterType": self.harvester_type,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )

        return {
            "harvesterType": self.harvester_type,
            "surface": surface,
            "tools": tools,
            "trajectories": [],
            "skills": [],
            "logs": [f"Extracted {len(tools)} atomic tools from {toolkit.get('name', 'connector toolkit')}."],
        }


def _execution_type(surface: str, tool_name: str) -> str:
    if tool_name.startswith("browser.") or surface == "webapp":
        return "browser_action"
    if surface == "database":
        return "database_operation"
    if surface == "knowledge":
        return "knowledge_query"
    return "api_call"
