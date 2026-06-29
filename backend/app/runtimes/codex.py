from __future__ import annotations

import os
from app.runtimes.base import AgentRuntimeDescriptor, AgentRuntimeProfile
from app.runtimes.external_step import ExternalStepRuntimeMixin


DEFAULT_MODEL = os.getenv("AUTOMATA_DEFAULT_CODEX_MODEL", "gpt-5-codex")


class CodexRuntimeAdapter(ExternalStepRuntimeMixin):
    kind = "codex"

    def descriptor(self) -> AgentRuntimeDescriptor:
        return AgentRuntimeDescriptor(
            kind="codex",
            label="Codex",
            description="Codex-backed runtime for code-oriented company automation using the same tools, skills and knowledge contracts.",
            defaultProvider="openai",
            defaultModel=DEFAULT_MODEL,
            executionMode="codex_step",
            supports={
                "tools": True,
                "skills": True,
                "knowledge": True,
                "browser": True,
                "code": True,
                "humanApproval": True,
            },
            requiredProfileFields=["model", "systemPrompt"],
        )

    def default_profile(self) -> AgentRuntimeProfile:
        return AgentRuntimeProfile(
            kind="codex",
            provider="openai",
            model=DEFAULT_MODEL,
            systemPrompt="Use the provided Autoppia tools, skills and knowledge to solve company tasks.",
        )
