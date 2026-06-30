from __future__ import annotations

import os

from app.company_harvesters.base import CompanyHarvester
from app.company_harvesters.agent_engines import AgenticHarvester, ClaudeCodeCompanyHarvester, CodexCompanyHarvester


HARVESTERS: dict[str, CompanyHarvester] = {
    "agentic": AgenticHarvester(),
    "claude_code": ClaudeCodeCompanyHarvester(),
    "codex": CodexCompanyHarvester(),
}


ALIASES = {
    "local": "agentic",
    "heuristic": "agentic",
    "local_heuristic": "agentic",
    "model_agent": "agentic",
    "agent": "agentic",
    "default": "agentic",
    "claude": "claude_code",
    "claude-code": "claude_code",
}


def normalize_company_harvester_name(name: str | None = None) -> str:
    raw = (name or os.getenv("AUTOMATA_COMPANY_HARVESTER") or "agentic").strip().lower()
    return ALIASES.get(raw, raw)


def get_company_harvester(name: str | None = None) -> CompanyHarvester:
    key = normalize_company_harvester_name(name)
    if key not in HARVESTERS:
        raise KeyError(f"Unknown company harvester: {key}")
    return HARVESTERS[key]


def list_company_harvesters() -> list[dict[str, object]]:
    return [harvester.info().model_dump(mode="json") for harvester in HARVESTERS.values()]
