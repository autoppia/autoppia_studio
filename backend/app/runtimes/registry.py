from __future__ import annotations

from typing import Any

from app.runtimes.base import AgentRuntimeAdapter, AgentRuntimeDescriptor, AgentRuntimeKind, AgentRuntimeProfile
from app.runtimes.claude_code import ClaudeCodeRuntimeAdapter
from app.runtimes.codex import CodexRuntimeAdapter
from app.runtimes.model_agent import ModelAgentRuntimeAdapter


_ADAPTERS: dict[str, AgentRuntimeAdapter] = {
    "model_agent": ModelAgentRuntimeAdapter(),
    "codex": CodexRuntimeAdapter(),
    "claude_code": ClaudeCodeRuntimeAdapter(),
}

VALID_RUNTIME_KINDS = frozenset(_ADAPTERS.keys())
DEFAULT_RUNTIME_KIND: AgentRuntimeKind = "model_agent"


def normalize_runtime_kind(value: Any) -> AgentRuntimeKind:
    clean = str(value or DEFAULT_RUNTIME_KIND).strip()
    if clean in _ADAPTERS:
        return clean  # type: ignore[return-value]
    return DEFAULT_RUNTIME_KIND


def get_runtime_adapter(kind: Any) -> AgentRuntimeAdapter:
    return _ADAPTERS[normalize_runtime_kind(kind)]


def list_runtime_adapters() -> list[AgentRuntimeAdapter]:
    return [_ADAPTERS[key] for key in sorted(_ADAPTERS)]


def runtime_descriptor(kind: Any) -> AgentRuntimeDescriptor:
    return get_runtime_adapter(kind).descriptor()


def runtime_descriptor_payload(kind: Any) -> dict[str, Any]:
    return runtime_descriptor(kind).model_dump()


def runtime_catalog_payload() -> list[dict[str, Any]]:
    return [adapter.descriptor().model_dump() for adapter in list_runtime_adapters()]


def default_runtime_profile(kind: Any) -> AgentRuntimeProfile:
    return get_runtime_adapter(kind).default_profile()


def default_runtime_profile_payload(kind: Any) -> dict[str, Any]:
    return default_runtime_profile(kind).model_dump()
