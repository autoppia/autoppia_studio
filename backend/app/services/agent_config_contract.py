from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


EXECUTION_STATE_KEYS = {
    "actionHistory",
    "actions",
    "approvalRequests",
    "artifacts",
    "cost",
    "currentSession",
    "currentUrl",
    "history",
    "latency",
    "messages",
    "pendingApprovals",
    "screenshots",
    "session",
    "sessionId",
    "state",
    "state_in",
    "state_out",
    "toolCalls",
    "tool_calls",
    "trace",
    "traceId",
    "traces",
    "trajectory",
}


def dedupe_runtime_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def runtime_host(value: str) -> str:
    try:
        return (urlparse(str(value or "")).hostname or "").lower()
    except Exception:
        return ""


def runtime_allowed_domains(website_url: str, existing_spec: dict[str, Any]) -> list[str]:
    raw_domains = (
        existing_spec.get("allowedDomains")
        or existing_spec.get("browserAllowedDomains")
        or existing_spec.get("allowedOrigins")
        or []
    )
    domains = dedupe_runtime_values(raw_domains if isinstance(raw_domains, list) else [])
    website_host = runtime_host(website_url)
    if website_host and website_host not in domains:
        domains.append(website_host)
    return domains


def runtime_classes(*, browser_enabled: bool, tools: dict[str, Any]) -> list[str]:
    classes = ["api_runtime"]
    if tools.get("connectors"):
        classes.append("connector_runtime")
    if tools.get("skills"):
        classes.append("skill_runtime")
    if browser_enabled:
        classes.append("browser_runtime")
        if tools.get("connectors") or tools.get("skills"):
            classes.append("hybrid_runtime")
    return classes


def build_runtime_spec(
    *,
    browser_enabled: bool = True,
    browser_mode: str = "visible",
    max_credits_per_run: float = 5.0,
    existing_tools: dict[str, Any] | None = None,
    website_url: str = "",
    existing_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = browser_mode if browser_mode in {"visible", "headless"} else "visible"
    credits = max(0.0, float(max_credits_per_run or 0.0))
    existing_spec = existing_spec if isinstance(existing_spec, dict) else {}
    tools = {
        "browser": browser_enabled,
        "connectors": True,
        "skills": True,
        "knowledge": False,
        **(existing_tools or {}),
    }
    tools["browser"] = browser_enabled
    allowed_domains = runtime_allowed_domains(website_url, existing_spec)
    approval_required_for = dedupe_runtime_values(existing_spec.get("approvalRequiredFor") or ["write", "send"])
    return {
        "browserEnabled": browser_enabled,
        "browserMode": mode,
        "browserDefaultUse": "exception",
        "browserRestrictedByDomain": bool(allowed_domains),
        "allowedDomains": allowed_domains,
        "approvalRequiredFor": approval_required_for,
        "runtimeClasses": runtime_classes(browser_enabled=browser_enabled, tools=tools),
        "maxCreditsPerRun": credits,
        "tools": tools,
    }


def _truthy_capability_inventory(
    *,
    runtime_spec: dict[str, Any],
    tools: list[dict[str, Any]] | None,
    skills: list[dict[str, Any]] | None,
    resources: list[dict[str, Any]] | None,
) -> bool:
    runtime_tools = runtime_spec.get("tools") if isinstance(runtime_spec.get("tools"), dict) else {}
    return bool(
        any(bool(value) for value in runtime_tools.values())
        or tools
        or skills
        or resources
    )


def control_plane_separation_gate(
    agent_config: dict[str, Any],
    *,
    tools: list[dict[str, Any]] | None = None,
    skills: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    capability_discovery = (
        agent_config.get("capabilityDiscovery")
        if isinstance(agent_config.get("capabilityDiscovery"), dict)
        else {"mode": "task_scoped"}
    )
    leaked_execution_keys = sorted(key for key in EXECUTION_STATE_KEYS if key in agent_config)
    checks = {
        "agentConfigDeclared": bool(agent_config.get("agentId") or agent_config.get("agentConfigId")),
        "runtimeSpecDeclared": bool(runtime_spec),
        "capabilityDiscoveryDeclared": bool(capability_discovery.get("mode")),
        "capabilityInventoryDeclared": _truthy_capability_inventory(
            runtime_spec=runtime_spec,
            tools=tools,
            skills=skills,
            resources=resources,
        ),
        "executionStateExternalized": not leaked_execution_keys,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    playbook: list[dict[str, Any]] = []
    if not checks["runtimeSpecDeclared"]:
        playbook.append(
            {
                "area": "agent_config",
                "severity": "high",
                "action": "Declare runtimeSpec before deployment so the external AgentRuntime receives an explicit execution contract.",
            }
        )
    if not checks["capabilityInventoryDeclared"]:
        playbook.append(
            {
                "area": "capabilities",
                "severity": "medium",
                "action": "Attach at least one governed tool, skill or resource before treating this AgentConfig as production-ready.",
            }
        )
    if leaked_execution_keys:
        playbook.append(
            {
                "area": "runtime_state",
                "severity": "high",
                "action": "Move session, trace, approval and artifact state out of AgentConfig and into runtime session records.",
            }
        )

    return {
        "state": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "checks": checks,
        "blockers": blockers,
        "leakedExecutionKeys": leaked_execution_keys,
        "hardeningPlaybook": playbook,
    }
