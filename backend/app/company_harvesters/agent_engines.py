from __future__ import annotations

from dataclasses import dataclass

from app.company_harvesters.base import CompanyHarvesterEngineInfo
from app.company_harvesters.local_heuristic import LocalHeuristicCompanyHarvester


@dataclass(frozen=True)
class ModelAgentCompanyHarvester(LocalHeuristicCompanyHarvester):
    name: str = "model_agent"
    kind: str = "model_agent"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="model_agent",
            description="Model-agent CompanyHarvester adapter. Currently uses the deterministic baseline planner until the LLM caller is wired.",
        )


@dataclass(frozen=True)
class ClaudeCodeCompanyHarvester(LocalHeuristicCompanyHarvester):
    name: str = "claude_code"
    kind: str = "claude_code"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="claude_code",
            description="Claude Code CompanyHarvester adapter. Placeholder over the baseline contract until the Claude Code company prompt is wired.",
        )


@dataclass(frozen=True)
class CodexCompanyHarvester(LocalHeuristicCompanyHarvester):
    name: str = "codex"
    kind: str = "codex"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="codex",
            description="Codex CompanyHarvester adapter. Placeholder over the baseline contract until the Codex company prompt is wired.",
        )
