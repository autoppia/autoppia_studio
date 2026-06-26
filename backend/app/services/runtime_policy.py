from __future__ import annotations

from typing import Any

from app.services.agent_config_contract import dedupe_runtime_values
from app.services.agent_config_contract import runtime_allowed_domains
from app.services.agent_config_contract import runtime_classes


POLICY_BOUNDARY_ORDER = ("read", "draft", "write", "send")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    values: list[str] = []
    for item in value:
        clean = str(item).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            values.append(clean)
    return values


def ordered_policy_boundaries(values: list[Any]) -> list[str]:
    boundaries = dedupe_runtime_values(values)
    ranked = {boundary: index for index, boundary in enumerate(POLICY_BOUNDARY_ORDER)}
    return sorted(boundaries, key=lambda item: (ranked.get(item, len(ranked)), item))


def approval_boundary_matrix(approval_required_for: list[Any], *, observed_boundaries: list[Any] | None = None) -> dict[str, Any]:
    required = set(ordered_policy_boundaries(approval_required_for))
    observed = set(ordered_policy_boundaries(observed_boundaries or []))
    boundaries = [
        {
            "boundary": boundary,
            "requiresApproval": boundary in required,
            "observed": boundary in observed,
        }
        for boundary in POLICY_BOUNDARY_ORDER
    ]
    return {
        "boundaries": boundaries,
        "requiredFor": [item["boundary"] for item in boundaries if item["requiresApproval"]],
        "missingObservedApproval": [
            item["boundary"]
            for item in boundaries
            if item["observed"] and item["boundary"] in {"write", "send"} and not item["requiresApproval"]
        ],
        "hasHumanBoundary": bool(required.intersection({"write", "send"})),
    }


def browser_enabled(agent_config: dict[str, Any]) -> bool:
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    if "browserEnabled" in runtime_spec:
        return bool(runtime_spec.get("browserEnabled"))
    capabilities = agent_config.get("runtimeCapabilities") if isinstance(agent_config.get("runtimeCapabilities"), dict) else {}
    return bool(capabilities.get("browser", True))


def browser_runtime_policy(agent_config: dict[str, Any]) -> dict[str, Any]:
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    domains = runtime_allowed_domains(str(agent_config.get("websiteUrl") or ""), runtime_spec)
    restricted = bool(domains)
    return {
        "enabled": browser_enabled(agent_config),
        "mode": str(runtime_spec.get("browserMode") or agent_config.get("browserMode") or "visible"),
        "allowedDomains": domains,
        "restrictedByDomain": restricted,
        "defaultUse": "exception",
        "riskLevel": "medium" if restricted else "high",
        "notes": "Browser runtime should be used only when API/connectors cannot cover the task.",
    }


def enterprise_runtime_policy(
    agent_config: dict[str, Any],
    *,
    tools: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    runtime_tools = runtime_spec.get("tools") if isinstance(runtime_spec.get("tools"), dict) else {}
    capabilities = agent_config.get("runtimeCapabilities") if isinstance(agent_config.get("runtimeCapabilities"), dict) else {}
    browser_policy = browser_runtime_policy(agent_config)
    api_enabled = bool(capabilities.get("apiCalls", runtime_tools.get("connectors", True)))
    runtime_browser_enabled = bool(browser_policy.get("enabled"))
    if api_enabled and runtime_browser_enabled:
        runtime_class = "hybrid"
    elif runtime_browser_enabled:
        runtime_class = "browser"
    else:
        runtime_class = "api"

    callables = [*tools, *skills]
    tools_enabled = {
        "browser": runtime_browser_enabled,
        "connectors": bool(runtime_tools.get("connectors", True)),
        "skills": bool(runtime_tools.get("skills", True)),
        "knowledge": bool(runtime_tools.get("knowledge", False)),
    }
    boundaries = ordered_policy_boundaries([str(item.get("policyBoundary") or "read") for item in callables])
    approval_required_for = runtime_spec.get("approvalRequiredFor")
    if not isinstance(approval_required_for, list) or not approval_required_for:
        approval_required_for = ["write", "send"] if capabilities.get("humanApprovalForWrites", True) else []
    approval_required_for = ordered_policy_boundaries(approval_required_for)
    approval_required_boundaries = ordered_policy_boundaries(
        {
            str(item.get("policyBoundary") or "read")
            for item in callables
            if item.get("policyBoundary") in approval_required_for
            or (isinstance(item.get("approvalPolicy"), dict) and item["approvalPolicy"].get("required"))
        }
    )
    approval_required_tools = [
        str(item.get("name") or "")
        for item in tools
        if isinstance(item.get("approvalPolicy"), dict) and item["approvalPolicy"].get("required")
    ]
    return {
        "runtimeClass": runtime_class,
        "runtimeType": f"{runtime_class}_runtime",
        "runtimeTypes": [f"{runtime_class}_runtime"] if runtime_class != "hybrid" else ["api_runtime", "browser_runtime", "hybrid_runtime"],
        "runtimeClasses": runtime_classes(browser_enabled=runtime_browser_enabled, tools=tools_enabled),
        "browser": {
            **browser_policy,
            "requiresSandbox": runtime_browser_enabled,
            "leastPrivilege": True,
        },
        "api": {
            "enabled": api_enabled,
            "connectorToolsEnabled": bool(runtime_tools.get("connectors", True)),
            "toolCount": len(tools),
        },
        "approvals": {
            "humanApprovalForWrites": bool(capabilities.get("humanApprovalForWrites", True)),
            "requiredFor": approval_required_for,
            "requiredBoundaries": approval_required_boundaries,
            "requiredTools": approval_required_tools,
            "boundaryMatrix": approval_boundary_matrix(approval_required_for, observed_boundaries=boundaries),
        },
        "budgets": {
            "maxCreditsPerRun": runtime_spec.get("maxCreditsPerRun", 5.0),
            "maxSteps": runtime_spec.get("maxSteps"),
        },
        "policyBoundaries": boundaries,
        "resources": {
            "total": len(resources),
            "indexed": sum(1 for item in resources if item.get("indexed")),
            "citable": sum(1 for item in resources if item.get("citable")),
        },
    }


def serialize_runtime_policy(doc: dict[str, Any]) -> dict[str, Any]:
    """Derive the explicit runtime policy contract from legacy skill/tool fields."""
    risk_policy = str(doc.get("riskPolicy") or "").strip().lower()
    permissions = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    runtime_spec = doc.get("runtimeSpec") if isinstance(doc.get("runtimeSpec"), dict) else {}
    approval = str(
        permissions.get("approval")
        or permissions.get("requiresHumanApproval")
        or permissions.get("requiresApproval")
        or ""
    ).strip().lower()
    if approval in {"always", "true", "yes"} or risk_policy == "human_approval_always":
        approval_mode = "always"
    elif approval in {"never", "false", "no"} or risk_policy == "autonomous":
        approval_mode = "never"
    else:
        approval_mode = "auto"

    requirements = [str(item) for item in doc.get("runtimeRequirements") or [] if item]
    requirement_set = {item.lower() for item in requirements}
    browser_runtime = bool(requirement_set.intersection({"browser", "computer_use", "web_runtime", "display"}))
    api_runtime = not requirements or bool(requirement_set.intersection({"api", "network", "http", "connector"}))
    if browser_runtime and api_runtime:
        runtime_class = "hybrid"
    elif browser_runtime:
        runtime_class = "browser"
    else:
        runtime_class = "api"
    runtime_type = f"{runtime_class}_runtime"

    if approval_mode == "always":
        approval_required_for = ["read", "draft", "write", "send"]
    elif approval_mode == "auto":
        approval_required_for = ["write", "send"]
    else:
        approval_required_for = []
    approval_required_for = ordered_policy_boundaries(approval_required_for)
    allowed_domains = _string_list(
        runtime_spec.get("allowedDomains")
        or permissions.get("allowedDomains")
        or permissions.get("domainAllowlist")
        or doc.get("allowedDomains")
    )
    browser_policy = {
        "defaultUse": "exception",
        "restrictedByDomain": bool(allowed_domains),
        "allowedDomains": allowed_domains,
        "requiresSandbox": browser_runtime,
        "leastPrivilege": True,
    }

    return {
        "policy": risk_policy or "human_approval_for_writes",
        "approvalMode": approval_mode,
        "approvalRequiredFor": approval_required_for,
        "approvalPolicy": approval_boundary_matrix(approval_required_for, observed_boundaries=[doc.get("policyBoundary") or "read"]),
        "writesRequireApproval": approval_mode in {"always", "auto"},
        "sendsRequireApproval": approval_mode in {"always", "auto"},
        "browserRuntime": browser_runtime,
        "runtimeClass": runtime_class,
        "runtimeType": runtime_type,
        "runtimeTypes": [runtime_type] if runtime_class != "hybrid" else ["api_runtime", "browser_runtime", "hybrid_runtime"],
        "runtimeRequirements": requirements,
        "browserPolicy": browser_policy,
    }
