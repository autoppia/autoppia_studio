from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SurfaceKind = Literal["web", "openapi", "api_docs", "document_url", "file", "knowledge_note"]
ExpectedSurface = Literal["web", "api", "documents", "email", "database", "other"]
IcaBenchmarkModeKind = Literal["api_only", "web_only", "hybrid"]


class IcaAuthProfile(BaseModel):
    required: bool = False
    kind: str = "demo_owner"
    username: str = ""
    password: str = ""
    instructions: str = ""
    token: str = ""


class IcaProjectSurface(BaseModel):
    surfaceId: str
    kind: SurfaceKind
    name: str
    url: str = ""
    authRequired: bool = False
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class IcaBenchmarkTask(BaseModel):
    taskId: str
    name: str
    prompt: str
    successCriteria: str
    expectedSurfaces: list[ExpectedSurface] = Field(default_factory=list)
    riskClass: str = "read"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IcaExpectedHarvest(BaseModel):
    connectors: list[str] = Field(default_factory=list)
    minimumTaskCount: int = 0
    minimumToolCount: int = 0
    requiresKnowledge: bool = False
    requiresApiTools: bool = False
    requiresBrowserTasks: bool = False


class IcaBenchmarkMode(BaseModel):
    modeId: IcaBenchmarkModeKind
    description: str = ""
    surfaceFilter: list[ExpectedSurface] = Field(default_factory=list)
    taskIds: list[str] = Field(default_factory=list)
    expectedHarvest: IcaExpectedHarvest = Field(default_factory=IcaExpectedHarvest)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IcaDemoProject(BaseModel):
    projectId: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    industry: str = ""
    defaultBaseUrl: str = ""
    auth: IcaAuthProfile = Field(default_factory=IcaAuthProfile)
    surfaces: list[IcaProjectSurface] = Field(default_factory=list)
    tasks: list[IcaBenchmarkTask] = Field(default_factory=list)
    expectedHarvest: IcaExpectedHarvest = Field(default_factory=IcaExpectedHarvest)
    benchmarkModes: list[IcaBenchmarkMode] = Field(default_factory=list)


class IcaMaterializedProject(BaseModel):
    project: IcaDemoProject
    materials: list[dict[str, Any]]
    userTasks: list[dict[str, Any]]
    expectedHarvest: IcaExpectedHarvest
    mode: IcaBenchmarkModeKind | None = None


class IcaEvaluationMetric(BaseModel):
    expected: list[str] = Field(default_factory=list)
    found: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    passed: bool = True


class IcaMinimumMetric(BaseModel):
    minimum: int = 0
    found: int = 0
    passed: bool = True


class IcaEvaluationResult(BaseModel):
    projectId: str
    mode: IcaBenchmarkModeKind | None = None
    passed: bool
    score: float
    connectors: IcaEvaluationMetric
    tools: IcaMinimumMetric
    tasks: IcaMinimumMetric
    benchmarks: IcaMinimumMetric
    missing: list[str] = Field(default_factory=list)
    run: dict[str, Any] = Field(default_factory=dict)
