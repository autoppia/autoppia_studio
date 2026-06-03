from typing import Any

from app.harvesters.base import connector_surface
from app.harvesters.toolkit import ToolkitHarvester


HARVESTER_BY_SURFACE = {
    "api": "api_harvester",
    "webapp": "webapp_harvester",
    "database": "database_harvester",
    "desktop": "desktop_harvester",
    "cli": "cli_harvester",
    "repo": "repo_harvester",
    "mixed": "mixed_harvester",
    "knowledge": "knowledge_harvester",
}


async def harvest_connector_capabilities(connector: dict[str, Any]) -> dict[str, Any]:
    surface = connector_surface(connector)
    harvester = ToolkitHarvester(HARVESTER_BY_SURFACE.get(surface, "api_harvester"), source="harvested_toolkit")
    result = await harvester.harvest(connector)
    result["surface"] = surface
    result["specializedRuntimeReady"] = surface in {"api", "database", "knowledge"}
    if surface not in {"api", "database", "knowledge"}:
        result.setdefault("logs", []).append(
            f"{surface} harvesting currently publishes toolkit tools; deep trajectory discovery needs its specialized runtime."
        )
    return result
