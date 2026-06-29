from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable


CustomConnectorExecutor = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]

_EXECUTORS: dict[str, CustomConnectorExecutor] = {}


def register_custom_connector_executor(name: str, executor: CustomConnectorExecutor) -> None:
    clean = str(name or "").strip()
    if not clean:
        raise ValueError("Custom connector executor name is required")
    _EXECUTORS[clean] = executor


def unregister_custom_connector_executor(name: str) -> None:
    _EXECUTORS.pop(str(name or "").strip(), None)


def clear_custom_connector_executors() -> None:
    _EXECUTORS.clear()


def custom_connector_executor_name(tool_doc: dict[str, Any] | None) -> str:
    if not isinstance(tool_doc, dict):
        return ""
    metadata = tool_doc.get("metadata") if isinstance(tool_doc.get("metadata"), dict) else {}
    return str(tool_doc.get("runtimeExecutor") or tool_doc.get("executor") or metadata.get("runtimeExecutor") or metadata.get("executor") or "").strip()


def has_custom_connector_executor(tool_doc: dict[str, Any] | None) -> bool:
    name = custom_connector_executor_name(tool_doc)
    return bool(name and name in _EXECUTORS)


async def execute_custom_connector_tool(
    *,
    company_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    tool_doc: dict[str, Any],
    agent_config: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    executor_name = custom_connector_executor_name(tool_doc)
    executor = _EXECUTORS.get(executor_name)
    if not executor:
        return None
    result = executor(
        {
            "companyId": company_id,
            "toolName": tool_name,
            "arguments": arguments,
            "tool": tool_doc,
            "agentConfig": agent_config or {},
            "payload": payload or {},
            "executor": executor_name,
        }
    )
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        result = {"output": result}
    return {
        "tool": tool_name,
        "success": result.get("success", True),
        "status": str(result.get("status") or "ok"),
        "output": result.get("output", result),
        "executor": executor_name,
    }
