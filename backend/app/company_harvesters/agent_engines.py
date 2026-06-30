from __future__ import annotations

from dataclasses import dataclass

from app.company_harvesters.base import CompanyHarvesterEngineInfo
from app.company_harvesters.local_heuristic import AgenticDiscoveryCore


@dataclass(frozen=True)
class AgenticHarvester(AgenticDiscoveryCore):
    name: str = "agentic"
    kind: str = "agentic"
    display_name: str = "Agentic Harvester"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="agentic",
            displayName=self.display_name,
            description="Default model-agent CompanyHarvester profile. It plans task discovery and solution discovery with the agentic discovery core.",
            metadata={"adapter": "agentic", "agentRuntime": "model_agent"},
        )


@dataclass(frozen=True)
class ClaudeCodeCompanyHarvester(AgenticDiscoveryCore):
    name: str = "claude_code"
    kind: str = "claude_code"
    display_name: str = "Claude Code Harvester"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="claude_code",
            displayName=self.display_name,
            description="Claude Code CompanyHarvester profile for miner submissions that use Claude Code as the outer company harvester runtime.",
            metadata={"adapter": "claude_code", "agentRuntime": "claude_code"},
        )


@dataclass(frozen=True)
class CodexCompanyHarvester(AgenticDiscoveryCore):
    name: str = "codex"
    kind: str = "codex"
    display_name: str = "Codex Harvester"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="codex",
            displayName=self.display_name,
            description="Codex CompanyHarvester profile for miner submissions that use Codex as the outer company harvester runtime.",
            metadata={"adapter": "codex", "agentRuntime": "codex"},
        )
