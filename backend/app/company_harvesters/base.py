from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.models.company_harvester import CompanyHarvesterInput, CompanyHarvesterOutput


CompanyHarvesterEngineKind = Literal["claude_code", "codex", "agentic", "remote_miner"]


class CompanyHarvesterEngineInfo(BaseModel):
    name: str
    kind: CompanyHarvesterEngineKind
    displayName: str = ""
    description: str = ""
    status: str = "ready"
    supportsTaskDiscovery: bool = True
    supportsSolutionDiscovery: bool = True
    supportsAgentBuildPlan: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)


class CompanyHarvester(Protocol):
    name: str
    kind: CompanyHarvesterEngineKind

    def info(self) -> CompanyHarvesterEngineInfo:
        ...

    async def harvest(self, request: CompanyHarvesterInput) -> CompanyHarvesterOutput:
        ...
