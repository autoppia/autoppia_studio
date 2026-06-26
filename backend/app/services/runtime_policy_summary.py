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


def _runtime_policy_playbook(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = {
        "browser_allowlist": "Configure explicit domain allowlists before enabling browser-capable runtime sessions.",
        "browser_domain_coverage": "Restrict or approve the observed browser domains before replaying or publishing the capability.",
        "browser_default_discipline": "Move repeat browser-only paths behind API or hybrid capabilities so browser remains an exception.",
        "side_effect_approval_coverage": "Require human approval for observed write/send side effects before production runtime use.",
        "write_approval": "Add write approval boundaries to writable runtime capabilities.",
        "runtime_policy": "Declare runtime policies for tools and skills before using them in AgentRuntime.",
    }
    severities = {
        "browser_default_discipline": "medium",
        "side_effect_approval_coverage": "high",
        "write_approval": "high",
    }
    return [
        {
            "gap": str(gap.get("key") or "runtime_policy"),
            "target": gap.get("target") or "runtime",
            "severity": severities.get(str(gap.get("key") or ""), "medium"),
            "action": actions.get(str(gap.get("key") or ""), str(gap.get("label") or "Resolve runtime policy gap.")),
        }
        for gap in gaps
    ]


def _runtime_class(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"hybrid", "hybrid_runtime"}:
        return "hybrid"
    if raw in {"browser", "browser_runtime", "computer_use", "web_runtime"}:
        return "browser"
    if raw in {"api", "api_runtime", "connector", "connector_runtime"}:
        return "api"
    return raw or "unknown"


def _runtime_class_gate(
    *,
    policies: list[dict[str, Any]],
    runtime_kinds: list[str],
    restricted_by_domain: bool,
    uncovered_domains: list[str],
    missing_observed_approval: list[str],
    browser_exception_ready: bool,
    browser_only_session_count: int,
) -> dict[str, Any]:
    declared = {_runtime_class(policy.get("runtimeClass")) for policy in policies if policy.get("runtimeClass")}
    observed = {_runtime_class(kind) for kind in runtime_kinds if str(kind or "").strip()}
    observed_supported = not observed or bool(declared & observed) or ("hybrid" in declared and observed <= {"api", "browser", "hybrid"})
    browser_in_use = bool({"browser", "hybrid"} & (declared | observed))
    checks = {
        "declaredPolicies": bool(policies),
        "observedRuntimeCovered": observed_supported,
        "browserAsException": browser_exception_ready,
        "browserDomainGoverned": (not browser_in_use) or (restricted_by_domain and not uncovered_domains),
        "sideEffectsApproved": not missing_observed_approval,
    }
    blockers = []
    if not checks["declaredPolicies"]:
        blockers.append({"name": "runtime_policy", "count": 1})
    if not checks["observedRuntimeCovered"]:
        blockers.append({"name": "observed_runtime_policy", "count": len(observed)})
    if not checks["browserDomainGoverned"]:
        blockers.append({"name": "browser_domain_governance", "count": len(uncovered_domains) or 1})
    if not checks["browserAsException"]:
        blockers.append({"name": "browser_runtime_default_discipline", "count": browser_only_session_count})
    if not checks["sideEffectsApproved"]:
        blockers.append({"name": "side_effect_approval_coverage", "count": len(missing_observed_approval)})
    ready = all(checks.values())
    return {
        "state": "ready" if ready else "needs_hardening",
        "ready": ready,
        "declared": sorted(declared),
        "observed": sorted(observed),
        "checks": checks,
        "blockers": blockers,
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
    hybrid_policy_count = sum(1 for policy in all_policies if policy.get("runtimeClass") == "hybrid")
    observed_runtime_classes = [_runtime_class(kind) for kind in runtime_kinds]
    api_session_count = sum(1 for kind in observed_runtime_classes if kind == "api")
    hybrid_session_count = sum(1 for kind in observed_runtime_classes if kind == "hybrid")
    browser_session_count = sum(1 for kind in runtime_kinds if kind in {"browser_runtime", "hybrid_runtime", "browser", "hybrid"})
    browser_only_session_count = sum(1 for kind in observed_runtime_classes if kind == "browser")
    api_first_session_count = api_session_count + hybrid_session_count
    browser_exception_ready = not browser_only_session_count or api_first_session_count >= browser_only_session_count
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
            {"key": "browser_default_discipline", "label": "Browser-only runtime sessions exceed API-first or hybrid runtime evidence.", "target": "runtime"} if not browser_exception_ready else None,
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
            "hybridCapabilities": hybrid_policy_count,
            "browserCapabilities": browser_policy_count,
            "apiSessions": api_session_count,
            "hybridSessions": hybrid_session_count,
            "browserSessions": browser_session_count,
        },
        "runtimeTaxonomy": {
            "defaultMode": "api_runtime",
            "browserDefault": "exception",
            "apiFirst": True,
            "browserRequiresAllowlist": bool(browser_policy_count or browser_session_count),
            "browserExceptionDiscipline": {
                "state": "ready" if browser_exception_ready else "needs_review",
                "ready": browser_exception_ready,
                "apiFirstSessions": api_first_session_count,
                "browserOnlySessions": browser_only_session_count,
                "hybridSessions": hybrid_session_count,
                "checks": {
                    "browserNotDefault": not browser_only_session_count or api_first_session_count >= browser_only_session_count,
                    "hybridCountsAsFallback": hybrid_session_count > 0 or browser_only_session_count == 0,
                },
            },
            "modes": [
                {
                    "runtimeType": "api_runtime",
                    "role": "Structured API, connector, database, email and document operations.",
                    "capabilities": api_policy_count,
                    "observedSessions": api_session_count,
                },
                {
                    "runtimeType": "browser_runtime",
                    "role": "Sandboxed UI automation for legacy portals or UI-only steps.",
                    "capabilities": browser_policy_count,
                    "observedSessions": sum(1 for kind in observed_runtime_classes if kind == "browser"),
                },
                {
                    "runtimeType": "hybrid_runtime",
                    "role": "API-first execution with browser fallback for uncovered enterprise steps.",
                    "capabilities": hybrid_policy_count,
                    "observedSessions": hybrid_session_count,
                },
            ],
        },
        "runtimeClassGate": _runtime_class_gate(
            policies=all_policies,
            runtime_kinds=runtime_kinds,
            restricted_by_domain=restricted_by_domain,
            uncovered_domains=uncovered_domains,
            missing_observed_approval=missing_observed_approval,
            browser_exception_ready=browser_exception_ready,
            browser_only_session_count=browser_only_session_count,
        ),
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
        "hardeningPlaybook": _runtime_policy_playbook(gaps),
    }
