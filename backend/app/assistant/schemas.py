from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AssistantMode = Literal[
    "studio_global",
    "onboarding",
    "agent_detail",
    "connectors",
    "capabilities",
    "evals",
    "work",
]


class AssistantConversationCreateRequest(BaseModel):
    email: str
    mode: AssistantMode = "studio_global"
    companyId: str = ""
    route: str = ""
    visibleState: dict[str, Any] = Field(default_factory=dict)
    seedPrompt: str = ""


class AssistantMessageRequest(BaseModel):
    email: str
    message: str
    mode: AssistantMode | None = None
    companyId: str = ""
    route: str = ""
    visibleState: dict[str, Any] = Field(default_factory=dict)


class AssistantMessage(BaseModel):
    role: str
    content: str = ""
    type: str = "message"
    toolName: str = ""
    status: str = "completed"
    createdAt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

