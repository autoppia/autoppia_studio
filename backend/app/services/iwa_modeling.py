from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return value


def _metadata(task_doc: dict[str, Any]) -> dict[str, Any]:
    return task_doc.get("metadata") if isinstance(task_doc.get("metadata"), dict) else {}


def iwa_task_payload(task_doc: dict[str, Any], agent_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the task body sent to subnet harvesters through /find_trayectory.

    This mirrors the subset emitted by IWA's Task.clean_task(): no tests/use_case
    are sent to the miner, but the prompt, URL, project id and specifications are.
    """

    agent = agent_config or {}
    metadata = _metadata(task_doc)
    task_id = str(task_doc.get("taskId") or task_doc.get("trajectoryId") or "")
    prompt = str(task_doc.get("prompt") or "")
    url = str(metadata.get("iwaStartUrl") or metadata.get("startUrl") or task_doc.get("url") or agent.get("websiteUrl") or "")
    specifications = metadata.get("specifications") if isinstance(metadata.get("specifications"), dict) else {}
    payload = {
        "id": task_id,
        "is_web_real": bool(metadata.get("isWebReal") or task_doc.get("isWebReal") or False),
        "web_project_id": str(metadata.get("iwaProjectId") or metadata.get("webProjectId") or task_doc.get("webProjectId") or ""),
        "url": url,
        "prompt": prompt,
        "specifications": _jsonable(specifications),
        "original_prompt": str(metadata.get("originalPrompt") or prompt),
        "hints": _jsonable(metadata.get("hints") if isinstance(metadata.get("hints"), list) else []),
        "expected_artifacts": _jsonable(metadata.get("expectedArtifacts") if isinstance(metadata.get("expectedArtifacts"), list) else []),
    }
    return {key: value for key, value in payload.items() if value not in ("", None, {}, [])}


def _internal_action_to_tool_call(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = str(raw.get("name") or raw.get("action") or "").strip()
    if not name:
        return None
    if name == "browser.done" or name.endswith(".done") or name == "api.human_approval" or name.startswith("api."):
        return None
    if name.startswith("browser."):
        name = name.split(".", 1)[1]
    if name in {"type"}:
        name = "input"
    if name in {"pressKey", "press_key", "press"}:
        name = "send_keys"
    args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else raw.get("args") if isinstance(raw.get("args"), dict) else {}
    args = normalize_tool_arguments(name, args if isinstance(args, dict) else {})
    return {"name": name, "arguments": _jsonable(args)}


def normalize_tool_arguments(name: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = _jsonable(args if isinstance(args, dict) else {})
    if name == "send_keys" and "keys" not in normalized and "key" in normalized:
        normalized["keys"] = normalized.pop("key")
    selector = normalized.get("selector")
    if isinstance(selector, dict):
        converted = normalize_selector(selector)
        if converted is not None:
            normalized["selector"] = converted
    return normalized


def normalize_selector(selector: dict[str, Any]) -> dict[str, Any] | None:
    selector_type = str(selector.get("type") or "").strip()
    value = str(selector.get("value") or "").strip()
    if selector_type in {"attributeValueSelector", "tagContainsSelector", "xpathSelector"}:
        return selector
    if selector_type in {"roleSelector", "role"}:
        role = str(selector.get("role") or value or "*").strip() or "*"
        name = str(selector.get("name") or selector.get("label") or selector.get("value") or "").strip()
        if not name:
            return None
        tag = "input" if role in {"searchbox", "textbox"} else role if role in {"button", "a", "textarea", "select"} else "*"
        escaped_name = name.replace('"', '\\"')
        return {
            "type": "xpathSelector",
            "value": (
                f"//{tag}[@aria-label=\"{escaped_name}\" "
                f"or @placeholder=\"{escaped_name}\" "
                f"or @title=\"{escaped_name}\" "
                f"or @name=\"{escaped_name}\" "
                f"or @value=\"{escaped_name}\" "
                f"or normalize-space(.)=\"{escaped_name}\"]"
            ),
        }
    if selector_type == "cssSelector":
        if value.startswith("#") and len(value) > 1 and not any(ch in value[1:] for ch in " .>#:["):
            return {"type": "attributeValueSelector", "attribute": "id", "value": value[1:], "case_sensitive": False}
        if value.startswith("[") and value.endswith("]") and "=" in value and " " not in value:
            key, raw = value[1:-1].split("=", 1)
            return {"type": "attributeValueSelector", "attribute": key.strip(), "value": raw.strip().strip("\"'"), "case_sensitive": False}
        if value == "[data-component-type='s-search-result'] h2 a.a-link-normal":
            return {"type": "xpathSelector", "value": "//*[@data-component-type='s-search-result']//h2//a[contains(concat(' ', normalize-space(@class), ' '), ' a-link-normal ')]"}
        if value.startswith(".") and len(value) > 1 and not any(ch in value[1:] for ch in " .>#:["):
            escaped = value[1:].replace("'", "\\'")
            return {"type": "xpathSelector", "value": f"//*[contains(concat(' ', normalize-space(@class), ' '), ' {escaped} ')]"}
    return selector


def canonical_tool_trajectory(tool_calls: list[Any], *, task_url: str = "") -> list[dict[str, Any]]:
    """Normalize harvested output to the IWA/subnet trajectory tool-call contract."""

    trajectory: list[dict[str, Any]] = []
    try:
        from autoppia_iwa.src.execution.actions.base import BaseAction
        from autoppia_iwa.src.execution.actions.actions import NavigateAction  # noqa: F401
    except Exception:
        BaseAction = None  # type: ignore[assignment]

    for raw in tool_calls:
        if not isinstance(raw, dict):
            continue
        tool_call = None
        if BaseAction is not None:
            try:
                candidate = _internal_action_to_tool_call(raw) if "action" in raw and "name" not in raw and "type" not in raw else raw
                action = BaseAction.create_action(candidate)
                if action is not None:
                    tool_call = action.to_tool_call()
            except Exception:
                tool_call = None
        if tool_call is None:
            tool_call = _internal_action_to_tool_call(raw)
        if tool_call is None:
            continue
        name = str(tool_call.get("name") or "")
        if name == "type":
            tool_call["name"] = "input"
            name = "input"
        if name in {"pressKey", "press_key", "press"}:
            tool_call["name"] = "send_keys"
            name = "send_keys"
        tool_call["arguments"] = normalize_tool_arguments(name, tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {})
        if tool_call["name"] == "navigate":
            args = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
            if isinstance(args.get("url"), str):
                args["url"] = normalize_navigation_url(args["url"], task_url)
                tool_call["arguments"] = args
        trajectory.append(tool_call)
    return trajectory


def internal_actions_from_trajectory(trajectory: list[Any]) -> list[dict[str, Any]]:
    """Store subnet/IWA tool calls in Automata's legacy action/args shape too."""

    actions: list[dict[str, Any]] = []
    for raw in canonical_tool_trajectory([item for item in trajectory if isinstance(item, dict)]):
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        action_name = name if "." in name and not name.startswith("browser.") else f"browser.{name}"
        actions.append({"action": action_name, "args": args})
    return actions


def canonical_trajectory(actions: list[Any], *, task_url: str = "") -> list[dict[str, Any]]:
    """Compatibility alias. New code should call canonical_tool_trajectory."""

    return canonical_tool_trajectory(actions, task_url=task_url)


def normalize_navigation_url(action_url: str, task_url: str) -> str:
    task_parts = urlsplit(task_url)
    action_parts = urlsplit(action_url)
    if not task_parts.scheme or not task_parts.netloc:
        return action_url
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(action_parts.query, keep_blank_values=True)
        if key not in {"X-WebAgent-Id", "web_agent_id", "X-Validator-Id", "validator_id"}
    ]
    path = action_parts.path or task_parts.path or "/"
    query = urlencode(filtered_query, doseq=True)
    if "seed=" in task_parts.query and "seed=" not in query:
        query = task_parts.query
    return urlunsplit((task_parts.scheme, task_parts.netloc, path, query, ""))
