from __future__ import annotations

import os
from app.runtimes.base import AgentRuntimeDescriptor, AgentRuntimeProfile
from app.runtimes.external_step import ExternalStepRuntimeMixin


DEFAULT_MODEL = os.getenv("AUTOMATA_DEFAULT_CLAUDE_CODE_MODEL", "claude-3-7-sonnet-latest")


class ClaudeCodeRuntimeAdapter(ExternalStepRuntimeMixin):
    kind = "claude_code"

    def descriptor(self) -> AgentRuntimeDescriptor:
        return AgentRuntimeDescriptor(
            kind="claude_code",
            label="Claude Code",
            description="Claude Code-backed runtime for code-oriented company automation using the same tools, skills and knowledge contracts.",
            defaultProvider="anthropic",
            defaultModel=DEFAULT_MODEL,
            executionMode="claude_code_step",
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
            kind="claude_code",
            provider="anthropic",
            model=DEFAULT_MODEL,
            systemPrompt="Use the provided Autoppia tools, skills and knowledge to solve company tasks.",
        )
