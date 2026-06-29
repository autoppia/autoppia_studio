from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

AgentRuntimeKind = Literal["codex", "claude_code", "model_agent"]
ModelProvider = Literal["openai", "anthropic", "local", "other"]


class AgentRuntimeProfile(BaseModel):
    kind: AgentRuntimeKind = "model_agent"
    provider: ModelProvider = "openai"
    model: str = ""
    systemPrompt: str = ""
    endpoint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeDescriptor(BaseModel):
    kind: AgentRuntimeKind
    label: str
    description: str = ""
    defaultProvider: ModelProvider = "openai"
    defaultModel: str = ""
    executionMode: str = "external_step"
    supports: dict[str, bool] = Field(
        default_factory=lambda: {
            "tools": True,
            "skills": True,
            "knowledge": True,
            "browser": True,
            "code": False,
            "humanApproval": True,
        }
    )
    requiredProfileFields: list[str] = Field(default_factory=list)


class AgentRuntimeContext(BaseModel):
    agentConfig: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeAdapter(Protocol):
    kind: AgentRuntimeKind

    def descriptor(self) -> AgentRuntimeDescriptor:
        ...

    def default_profile(self) -> AgentRuntimeProfile:
        ...

    async def step(self, request: Any, context: AgentRuntimeContext) -> Any:
        ...
