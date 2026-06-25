from __future__ import annotations

from typing import Any


def serialize_runtime_policy(doc: dict[str, Any]) -> dict[str, Any]:
    """Derive the explicit runtime policy contract from legacy skill/tool fields."""
    risk_policy = str(doc.get("riskPolicy") or "").strip().lower()
    permissions = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
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

    if approval_mode == "always":
        approval_required_for = ["read", "draft", "write", "send"]
    elif approval_mode == "auto":
        approval_required_for = ["write", "send"]
    else:
        approval_required_for = []

    return {
        "policy": risk_policy or "human_approval_for_writes",
        "approvalMode": approval_mode,
        "approvalRequiredFor": approval_required_for,
        "writesRequireApproval": approval_mode in {"always", "auto"},
        "sendsRequireApproval": approval_mode in {"always", "auto"},
        "browserRuntime": browser_runtime,
        "runtimeClass": runtime_class,
        "runtimeRequirements": requirements,
    }
