import re
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return normalized or "item"


def connector_surface(connector: dict[str, Any]) -> str:
    explicit = str(connector.get("surface") or "").strip().lower()
    if explicit:
        return explicit
    connector_type = str(connector.get("type") or "api").lower()
    if connector_type == "web":
        return "webapp"
    if connector_type in {"postgres", "mongodb"}:
        return "database"
    if connector_type in {"knowledge"}:
        return "knowledge"
    return "api"


def risk_from_side_effects(side_effects: str) -> str:
    value = (side_effects or "reads").lower()
    if value in {"none", "read", "reads"}:
        return "low"
    if "write" in value:
        return "medium"
    return "medium"


class BaseHarvester:
    harvester_type = "base"

    async def harvest(self, connector: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
