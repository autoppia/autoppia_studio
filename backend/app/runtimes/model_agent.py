from __future__ import annotations

import os
from app.runtimes.base import AgentRuntimeDescriptor, AgentRuntimeProfile
from app.runtimes.external_step import ExternalStepRuntimeMixin


DEFAULT_MODEL = os.getenv("AUTOMATA_DEFAULT_MODEL_AGENT_MODEL", "gpt-5-mini")


class ModelAgentRuntimeAdapter(ExternalStepRuntimeMixin):
    kind = "model_agent"

    def descriptor(self) -> AgentRuntimeDescriptor:
        return AgentRuntimeDescriptor(
            kind="model_agent",
            label="Model Agent",
            description="General conversational agent driven by a configured model, system prompt, tools, skills and knowledge.",
            defaultProvider="openai",
            defaultModel=DEFAULT_MODEL,
            executionMode="model_step",
            supports={
                "tools": True,
                "skills": True,
                "knowledge": True,
                "browser": True,
                "code": False,
                "humanApproval": True,
            },
            requiredProfileFields=["provider", "model", "systemPrompt"],
        )

    def default_profile(self) -> AgentRuntimeProfile:
        return AgentRuntimeProfile(
            kind="model_agent",
            provider="openai",
            model=DEFAULT_MODEL,
            systemPrompt=(
                "You are an Autoppia company operations agent. Prefer approved skills "
                "and governed tools, cite knowledge sources, and request approval for writes or sends."
            ),
        )
