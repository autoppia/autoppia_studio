from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.runtimes.base import AgentRuntimeKind, ModelProvider


StudioMode = Literal["normal", "dev"]
CompanyMaterialKind = Literal["document_url", "file", "website", "api_docs", "openapi", "auth_note", "knowledge_note", "task_list"]
CompanyHarvestStatus = Literal[
    "draft",
    "intaking",
    "indexing_knowledge",
    "discovering_systems",
    "discovering_connectors",
    "discovering_tools",
    "discovering_entities",
    "discovering_tasks",
    "building_benchmarks",
    "solving_tasks",
    "judging_trajectories",
    "promoting_skills",
    "building_agents",
    "needs_user_input",
    "ready",
    "failed",
]
CompanyHarvestArtifactKind = Literal[
    "knowledge_document",
    "connector_candidate",
    "tool_candidate",
    "entity_candidate",
    "task_candidate",
    "benchmark",
    "trajectory",
    "skill",
    "agent_config",
    "company_harvester_output",
    "question_for_user",
]
Visibility = Literal["normal", "dev", "internal"]


class CompanyMaterial(BaseModel):
    kind: CompanyMaterialKind
    name: str = ""
    url: str = ""
    documentId: str = ""
    connectorId: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyIntake(BaseModel):
    schemaVersion: str = "company_intake/v1"
    intakeId: str
    email: str
    companyId: str
    companyName: str = ""
    description: str = ""
    materials: list[CompanyMaterial] = Field(default_factory=list)
    userTasks: list[dict[str, Any]] = Field(default_factory=list)
    mode: StudioMode = "normal"
    status: Literal["draft", "ready_for_harvest", "harvesting", "ready", "failed"] = "draft"
    createdAt: Any = None
    updatedAt: Any = None


class CompanyHarvesterInput(BaseModel):
    schemaVersion: str = "company_harvester_input/v1"
    companyId: str
    companyName: str = ""
    description: str = ""
    materials: list[CompanyMaterial] = Field(default_factory=list)
    authRefs: list[str] = Field(default_factory=list)
    discoveryMode: Literal["ui_only", "ui_api", "ui_api_docs", "full_company"] = "full_company"
    userTasks: list[dict[str, Any]] = Field(default_factory=list)
    runtimeKinds: list[AgentRuntimeKind] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyTaskProposal(BaseModel):
    taskId: str = ""
    name: str
    prompt: str
    successCriteria: str = ""
    expectedSurfaces: list[str] = Field(default_factory=list)
    riskClass: str = "read"
    confidence: float = 0.0
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyConnectorPlan(BaseModel):
    connectorId: str = ""
    name: str = ""
    type: Literal["web", "api", "knowledge", "email", "database", "custom"] = "custom"
    surface: str = ""
    authRequired: bool = False
    runtimeRequirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyToolPlan(BaseModel):
    toolId: str = ""
    name: str
    connectorId: str = ""
    executionType: str = ""
    policyBoundary: str = "read"
    riskLevel: str = "low"
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    outputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "additionalProperties": True})
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyTrajectoryPlan(BaseModel):
    trajectoryId: str = ""
    description: str = ""
    toolCalls: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["generated", "approved", "expected", "human"] = "generated"
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanySkillPlan(BaseModel):
    skillId: str = ""
    name: str
    description: str = ""
    trajectoryIds: list[str] = Field(default_factory=list)
    instructions: str = ""
    source: Literal["trajectory", "text", "hybrid"] = "hybrid"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyAgentProviderPlan(BaseModel):
    runtimeKind: AgentRuntimeKind = "model_agent"
    provider: ModelProvider = "openai"
    model: str = ""
    systemPrompt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyTaskSolution(BaseModel):
    taskId: str
    connectors: list[CompanyConnectorPlan] = Field(default_factory=list)
    tools: list[CompanyToolPlan] = Field(default_factory=list)
    trajectories: list[CompanyTrajectoryPlan] = Field(default_factory=list)
    skills: list[CompanySkillPlan] = Field(default_factory=list)
    agentProvider: CompanyAgentProviderPlan = Field(default_factory=CompanyAgentProviderPlan)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyHarvesterOutput(BaseModel):
    schemaVersion: str = "company_harvester_output/v1"
    companyId: str = ""
    benchmarkId: str = ""
    proposedTasks: list[CompanyTaskProposal] = Field(default_factory=list)
    taskSolutions: list[CompanyTaskSolution] = Field(default_factory=list)
    agentConfigs: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyHarvestArtifact(BaseModel):
    artifactId: str
    kind: CompanyHarvestArtifactKind
    title: str = ""
    refId: str = ""
    status: str = "pending"
    visibility: Visibility = "dev"
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: Any = None


class CompanyHarvestQuestion(BaseModel):
    questionId: str
    code: str
    prompt: str
    reason: str = ""
    severity: Literal["info", "warning", "blocking"] = "info"
    expectedAnswerType: Literal["text", "url", "credentials", "file", "choice", "task_list"] = "text"
    materialRef: str = ""
    visibility: Visibility = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyHarvestStep(BaseModel):
    key: CompanyHarvestStatus
    label: str
    status: Literal["pending", "in_progress", "done", "blocked", "skipped"] = "pending"
    message: str = ""
    visibility: Visibility = "normal"
    updatedAt: Any = None


class CompanyHarvestRun(BaseModel):
    schemaVersion: str = "company_harvest_run/v1"
    runId: str
    intakeId: str
    email: str
    companyId: str
    status: CompanyHarvestStatus = "draft"
    mode: StudioMode = "normal"
    currentStep: CompanyHarvestStatus = "draft"
    steps: list[CompanyHarvestStep] = Field(default_factory=list)
    artifacts: list[CompanyHarvestArtifact] = Field(default_factory=list)
    normalSummary: dict[str, Any] = Field(default_factory=dict)
    devSummary: dict[str, Any] = Field(default_factory=dict)
    questions: list[CompanyHarvestQuestion] = Field(default_factory=list)
    nextAction: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    createdAt: Any = None
    updatedAt: Any = None
