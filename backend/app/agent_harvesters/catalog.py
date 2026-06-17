from __future__ import annotations

from dataclasses import dataclass


OFFICIAL_AGENT_HARVESTER = "autoppia_harvester"

LEGACY_HARVESTER_ALIASES = {
    "top_miner": OFFICIAL_AGENT_HARVESTER,
}

PUBLIC_HARVESTER_NAMES = {
    "autoppia_harvester",
    "claude_cli",
    "noop",
}


@dataclass(frozen=True)
class AgentHarvesterInfo:
    name: str
    status: str = "available"
    selection: str = "backend_config"

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "selection": self.selection,
        }


def normalize_harvester_name(name: str) -> str:
    key = name.strip() or OFFICIAL_AGENT_HARVESTER
    return LEGACY_HARVESTER_ALIASES.get(key, key)

