from __future__ import annotations

from typing import Any

from app.services.runtime_policy import serialize_runtime_policy


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _approval_boundary_counts(policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries = ["read", "draft", "write", "send"]
    return [
        {"name": boundary, "count": sum(1 for policy in policies if boundary in (policy.get("approvalRequiredFor") or []))}
        for boundary in boundaries
    ]


def summarize_runtime_policy_map(
    *,
    skills: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    runtime_kinds: list[str],
    browser_allowlisted: bool,
    pending_approvals: int,
    approved_approvals: int,
) -> dict[str, Any]:
    skill_policies = [serialize_runtime_policy(skill) for skill in skills]
    tool_policies = [serialize_runtime_policy(tool) for tool in tools]
    all_policies = [*skill_policies, *tool_policies]
    browser_policy_count = sum(1 for policy in all_policies if policy.get("browserRuntime"))
    api_policy_count = sum(1 for policy in all_policies if policy.get("runtimeClass") == "api")
    browser_session_count = sum(1 for kind in runtime_kinds if kind in {"browser_runtime", "hybrid_runtime", "browser", "hybrid"})
    gaps = [
        gap
        for gap in [
            {"key": "browser_allowlist", "label": "Browser-capable runtime exists but no domain allowlist is configured.", "target": "governance"} if (browser_policy_count or browser_session_count) and not browser_allowlisted else None,
            {"key": "write_approval", "label": "Writable tools or skills exist without write approval boundaries.", "target": "capabilities"} if all_policies and not any("write" in (policy.get("approvalRequiredFor") or []) for policy in all_policies) else None,
            {"key": "runtime_policy", "label": "No tool or skill runtime policies are available yet.", "target": "capabilities"} if not all_policies else None,
        ]
        if gap
    ]
    return {
        "defaultBrowserUse": "exception",
        "browserRestrictedByDomain": browser_allowlisted,
        "runtimeClasses": {
            "declared": _sorted_counts([str(policy.get("runtimeClass") or "api") for policy in all_policies]),
            "observed": _sorted_counts(runtime_kinds),
            "apiCapabilities": api_policy_count,
            "browserCapabilities": browser_policy_count,
            "browserSessions": browser_session_count,
        },
        "approvalBoundaries": {
            "skills": _approval_boundary_counts(skill_policies),
            "tools": _approval_boundary_counts(tool_policies),
            "all": _approval_boundary_counts(all_policies),
        },
        "humanApproval": {
            "pending": pending_approvals,
            "approved": approved_approvals,
            "writesProtected": any("write" in (policy.get("approvalRequiredFor") or []) for policy in all_policies),
            "sendsProtected": any("send" in (policy.get("approvalRequiredFor") or []) for policy in all_policies),
        },
        "gaps": gaps,
    }
