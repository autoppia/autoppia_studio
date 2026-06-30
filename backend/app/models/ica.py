from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.runtimes.base import AgentRuntimeKind, ModelProvider


SurfaceKind = Literal["web", "openapi", "api_docs", "document_url", "file", "knowledge_note"]
ExpectedSurface = Literal["web", "api", "documents", "email", "database", "other"]
IcaBenchmarkModeKind = Literal["api_only", "web_only", "hybrid"]
IcaEvaluationPhase = Literal["task_discovery", "solution_discovery", "agent_execution"]


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


class IcaTaskDiscoveryExpectation(BaseModel):
    taskId: str
    required: bool = True
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    expectedSurfaces: list[ExpectedSurface] = Field(default_factory=list)
    minSimilarity: float = 0.45
    judge: Literal["rules", "llm", "hybrid"] = "hybrid"


class IcaTrajectorySpec(BaseModel):
    trajectoryId: str = ""
    description: str = ""
    toolCalls: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["expected", "generated", "approved"] = "expected"


class IcaSkillSpec(BaseModel):
    skillId: str = ""
    name: str
    description: str = ""
    trajectoryIds: list[str] = Field(default_factory=list)
    instructions: str = ""
    source: Literal["trajectory", "text", "hybrid"] = "hybrid"


class IcaAgentProviderSpec(BaseModel):
    runtimeKind: AgentRuntimeKind = "model_agent"
    provider: ModelProvider = "openai"
    model: str = ""
    systemPrompt: str = ""


class IcaTaskSolutionSpec(BaseModel):
    taskId: str
    connectors: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    trajectories: list[IcaTrajectorySpec] = Field(default_factory=list)
    skills: list[IcaSkillSpec] = Field(default_factory=list)
    agentProvider: IcaAgentProviderSpec = Field(default_factory=IcaAgentProviderSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IcaExpectedHarvest(BaseModel):
    connectors: list[str] = Field(default_factory=list)
    minimumTaskCount: int = 0
    minimumToolCount: int = 0
    requiresKnowledge: bool = False
    requiresApiTools: bool = False
    requiresBrowserTasks: bool = False
    minimumSolutionCount: int = 0


class IcaBenchmarkMode(BaseModel):
    modeId: IcaBenchmarkModeKind
    description: str = ""
    surfaceFilter: list[ExpectedSurface] = Field(default_factory=list)
    taskIds: list[str] = Field(default_factory=list)
    discoveryInput: list[ExpectedSurface] = Field(default_factory=list)
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
    taskDiscoveryExpectations: list[IcaTaskDiscoveryExpectation] = Field(default_factory=list)
    expectedSolutions: list[IcaTaskSolutionSpec] = Field(default_factory=list)
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


class IcaTaskDiscoveryMatch(BaseModel):
    expectedTaskId: str
    expectedName: str = ""
    matchedTaskId: str = ""
    matchedName: str = ""
    score: float = 0.0
    matched: bool = False
    judge: Literal["rules", "llm", "hybrid"] = "rules"
    reason: str = ""


class IcaTaskDiscoveryEvaluation(BaseModel):
    projectId: str
    mode: IcaBenchmarkModeKind | None = None
    phase: Literal["task_discovery"] = "task_discovery"
    passed: bool
    score: float
    recall: float
    precision: float
    expectedCount: int
    discoveredCount: int
    matchedCount: int
    matches: list[IcaTaskDiscoveryMatch] = Field(default_factory=list)
    missingTaskIds: list[str] = Field(default_factory=list)
    extraTaskNames: list[str] = Field(default_factory=list)


class IcaSolutionDiscoveryEvaluation(BaseModel):
    projectId: str
    mode: IcaBenchmarkModeKind | None = None
    phase: Literal["solution_discovery"] = "solution_discovery"
    passed: bool
    score: float
    expectedTaskCount: int
    solutionCount: int
    missingTaskIds: list[str] = Field(default_factory=list)
    incompleteTaskIds: list[str] = Field(default_factory=list)
    solutions: list[IcaTaskSolutionSpec] = Field(default_factory=list)


class IcaCompanyBenchmarkResult(BaseModel):
    projectId: str
    mode: IcaBenchmarkModeKind | None = None
    passed: bool
    score: float
    phases: dict[str, Any] = Field(default_factory=dict)
