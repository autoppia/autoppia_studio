from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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


def _missing_observed_approval_boundaries(policies: list[dict[str, Any]]) -> list[str]:
    missing: set[str] = set()
    for policy in policies:
        approval_policy = policy.get("approvalPolicy") if isinstance(policy.get("approvalPolicy"), dict) else {}
        for boundary in approval_policy.get("missingObservedApproval") or []:
            clean = str(boundary or "").strip()
            if clean:
                missing.add(clean)
    return sorted(missing)


def _approval_hardening(missing_boundaries: list[str]) -> dict[str, Any]:
    next_actions = [
        {
            "boundary": boundary,
            "severity": "high" if boundary in {"write", "send"} else "medium",
            "action": f"Require human approval for observed {boundary} side effects before publishing runtime capabilities.",
        }
        for boundary in missing_boundaries
    ]
    return {
        "ready": not missing_boundaries,
        "missingBoundaries": missing_boundaries,
        "severity": (
            "high"
            if any(boundary in {"write", "send"} for boundary in missing_boundaries)
            else "medium"
            if missing_boundaries
            else "none"
        ),
        "nextActions": next_actions,
    }


def normalize_runtime_domains(values: list[Any]) -> list[str]:
    domains: set[str] = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or raw).strip().lower()
        if host:
            domains.add(host)
    return sorted(domains)


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in allowed_domains)


def _iter_url_values(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith(("http://", "https://")):
            urls.append(raw)
        return urls
    if isinstance(value, list):
        for item in value:
            urls.extend(_iter_url_values(item))
        return urls
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "").lower()
            if key_text in {"url", "href", "currenturl", "starturl", "websiteurl", "targeturl"}:
                urls.extend(_iter_url_values(item))
            elif isinstance(item, (dict, list)):
                urls.extend(_iter_url_values(item))
        return urls
    return urls


def observed_browser_domains(sessions: list[dict[str, Any]]) -> list[str]:
    urls: list[Any] = []
    for session in sessions:
        session_contract = session.get("sessionContract") if isinstance(session.get("sessionContract"), dict) else {}
        agent_runtime = session_contract.get("agentRuntime") if isinstance(session_contract.get("agentRuntime"), dict) else {}
        runtime_kind = str(
            session.get("runtimeKind")
            or session.get("runtimeType")
            or agent_runtime.get("runtimeKind")
            or agent_runtime.get("runtimeType")
            or ""
        ).lower()
        action_history = session.get("actionHistory") if isinstance(session.get("actionHistory"), list) else []
        has_browser_actions = any(
            isinstance(action, dict) and str(action.get("action") or action.get("name") or "").startswith("browser.")
            for action in action_history
        )
        if runtime_kind not in {"browser", "hybrid", "browser_runtime", "hybrid_runtime"} and not has_browser_actions:
            continue
        urls.extend(_iter_url_values(session))
    return normalize_runtime_domains(urls)


def summarize_runtime_policy_map(
    *,
    skills: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    runtime_kinds: list[str],
    browser_allowlisted: bool,
    browser_allowed_domains: list[Any] | None = None,
    browser_observed_domains: list[Any] | None = None,
    pending_approvals: int,
    approved_approvals: int,
) -> dict[str, Any]:
    skill_policies = [serialize_runtime_policy(skill) for skill in skills]
    tool_policies = [serialize_runtime_policy(tool) for tool in tools]
    all_policies = [*skill_policies, *tool_policies]
    missing_observed_approval = _missing_observed_approval_boundaries(all_policies)
    approval_hardening = _approval_hardening(missing_observed_approval)
    browser_policy_count = sum(1 for policy in all_policies if policy.get("browserRuntime"))
    api_policy_count = sum(1 for policy in all_policies if policy.get("runtimeClass") == "api")
    browser_session_count = sum(1 for kind in runtime_kinds if kind in {"browser_runtime", "hybrid_runtime", "browser", "hybrid"})
    allowed_domains = normalize_runtime_domains(browser_allowed_domains or [])
    observed_domains = normalize_runtime_domains(browser_observed_domains or [])
    covered_domains = [domain for domain in observed_domains if _domain_allowed(domain, allowed_domains)]
    uncovered_domains = [domain for domain in observed_domains if not _domain_allowed(domain, allowed_domains)]
    restricted_by_domain = bool(browser_allowlisted or allowed_domains)
    gaps = [
        gap
        for gap in [
            {"key": "browser_allowlist", "label": "Browser-capable runtime exists but no domain allowlist is configured.", "target": "governance"} if (browser_policy_count or browser_session_count) and not restricted_by_domain else None,
            {"key": "browser_domain_coverage", "label": "Browser runtime observed domains outside the configured allowlist.", "target": "governance"} if browser_session_count and uncovered_domains else None,
            {"key": "side_effect_approval_coverage", "label": "Write or send capability boundaries were observed without matching approval requirements.", "target": "capabilities"} if missing_observed_approval else None,
            {"key": "write_approval", "label": "Writable tools or skills exist without write approval boundaries.", "target": "capabilities"} if all_policies and not any("write" in (policy.get("approvalRequiredFor") or []) for policy in all_policies) else None,
            {"key": "runtime_policy", "label": "No tool or skill runtime policies are available yet.", "target": "capabilities"} if not all_policies else None,
        ]
        if gap
    ]
    return {
        "defaultBrowserUse": "exception",
        "browserRestrictedByDomain": restricted_by_domain,
        "browserDomainGovernance": {
            "allowedDomains": allowed_domains,
            "observedDomains": observed_domains,
            "coveredDomains": covered_domains,
            "uncoveredDomains": uncovered_domains,
            "coverageRatio": round(len(covered_domains) / len(observed_domains), 3) if observed_domains else 1.0,
            "sessionsRequireAllowlist": bool(browser_session_count),
        },
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
            "missingObservedApproval": missing_observed_approval,
            "sideEffectsProtected": not missing_observed_approval,
            "hardening": approval_hardening,
        },
        "humanApproval": {
            "pending": pending_approvals,
            "approved": approved_approvals,
            "writesProtected": any("write" in (policy.get("approvalRequiredFor") or []) for policy in all_policies),
            "sendsProtected": any("send" in (policy.get("approvalRequiredFor") or []) for policy in all_policies),
        },
        "gaps": gaps,
    }
