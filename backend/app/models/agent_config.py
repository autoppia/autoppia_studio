from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeCapabilities(BaseModel):
    browser: bool = True
    apiCalls: bool = True
    knowledge: bool = False
    python: bool = False
    humanApprovalForWrites: bool = True


class AgentTask(BaseModel):
    name: str
    prompt: str
    successCriteria: str = ""
    status: str = "draft"
    trajectoryId: str = ""


class AgentCallable(BaseModel):
    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    outputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "additionalProperties": True})
    kind: Literal["tool", "skill"] = "tool"
    sideEffects: str = "reads"
    riskLevel: str = "low"
    source: str = ""
    capabilityId: str = ""
    connectorId: str = ""
    trajectoryIds: list[str] = Field(default_factory=list)
    executionType: str = ""
    runtime: str = ""
    permissions: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    schemaVersion: str = "agent_config/v1"
    agentId: str
    name: str
    email: str = ""
    companyId: str = ""
    websiteUrl: str = ""
    runtimeEndpoint: str = ""
    baseRuntimeEndpoint: str = ""
    runtimeType: str = "generalist_with_company_capabilities"
    status: str = "draft"
    trainingStatus: str = "not_started"
    runtimeCapabilities: RuntimeCapabilities = Field(default_factory=RuntimeCapabilities)
    tasks: list[AgentTask] = Field(default_factory=list)
    tools: list[AgentCallable] = Field(default_factory=list)
    skills: list[AgentCallable] = Field(default_factory=list)
    knowledge: list[dict[str, Any]] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=dict)
    riskPolicy: dict[str, Any] = Field(default_factory=lambda: {"writesRequireApproval": True})
    createdAt: Any = None
    updatedAt: Any = None


class AgentStepRequest(BaseModel):
    schemaVersion: str = "agent_step/v1"
    task_id: str = ""
    task: str = ""
    prompt: str = ""
    snapshot_html: str = ""
    url: str = ""
    step_index: int = 0
    include_reasoning: bool = True
    history: list[Any] = Field(default_factory=list)
    state_in: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    agentConfig: AgentConfig | None = None


class AgentStepResponse(BaseModel):
    schemaVersion: str = "agent_step_result/v1"
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: str | None = None
    content: str | None = None
    done: bool = False
    state_out: dict[str, Any] = Field(default_factory=dict)
