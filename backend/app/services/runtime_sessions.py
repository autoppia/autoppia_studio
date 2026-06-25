from __future__ import annotations

from typing import Any


def _list_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item or "").strip()]


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def session_runtime_kind(session: dict[str, Any]) -> str:
    contract = session.get("sessionContract") if isinstance(session.get("sessionContract"), dict) else {}
    runtime = contract.get("agentRuntime") if isinstance(contract.get("agentRuntime"), dict) else {}
    runtime_kind = str(runtime.get("runtimeKind") or session.get("runtimeKind") or "").strip()
    if runtime_kind:
        return f"{runtime_kind}_runtime" if runtime_kind in {"api", "browser", "hybrid"} else runtime_kind
    action_history = session.get("actionHistory") if isinstance(session.get("actionHistory"), list) else []
    actions = [str(item.get("action") or "") for item in action_history if isinstance(item, dict)]
    has_browser = any(action.startswith("browser.") for action in actions)
    has_connector = any(
        not action.startswith(("browser.", "router.", "runtime.", "user."))
        and action not in {"skill.use", "Initialize", "Continue", ""}
        for action in actions
    )
    if has_browser and has_connector:
        return "hybrid_runtime"
    if has_browser:
        return "browser_runtime"
    return "api_runtime"


def summarize_session_contracts(sessions: list[dict[str, Any]], *, sample_limit: int = 8) -> dict[str, Any]:
    with_contract = 0
    selected_skill = 0
    pending_approvals = 0
    artifact_outputs = 0
    replay_ready = 0
    total_credits = 0.0
    trace_count = 0
    runtime_kinds: list[str] = []
    samples: list[dict[str, Any]] = []
    for session in sessions:
        contract = session.get("sessionContract") if isinstance(session.get("sessionContract"), dict) else {}
        runtime = contract.get("agentRuntime") if isinstance(contract.get("agentRuntime"), dict) else {}
        skill = contract.get("selectedSkill") if isinstance(contract.get("selectedSkill"), dict) else {}
        approvals = contract.get("approvalState") if isinstance(contract.get("approvalState"), dict) else {}
        artifacts = contract.get("artifactState") if isinstance(contract.get("artifactState"), dict) else {}
        cost = contract.get("costState") if isinstance(contract.get("costState"), dict) else {}
        trace = contract.get("traceState") if isinstance(contract.get("traceState"), dict) else {}
        if contract:
            with_contract += 1
        runtime_kind = str(runtime.get("runtimeKind") or session_runtime_kind(session)).replace("_runtime", "") or "unknown"
        runtime_kinds.append(runtime_kind)
        skill_id = str(skill.get("skillId") or session.get("matchedSkillId") or "").strip()
        if skill.get("matched") or skill_id:
            selected_skill += 1
        approval_count = int(approvals.get("pending") or session.get("pendingApprovalCount") or 0)
        pending_approvals += approval_count
        artifact_count = int(artifacts.get("count") or session.get("artifactCount") or 0)
        artifact_outputs += artifact_count
        credits = _safe_float(cost.get("creditsSpent") or session.get("creditsSpent"))
        total_credits += credits
        traces = trace.get("traceIds") if isinstance(trace.get("traceIds"), list) else session.get("traceIds") if isinstance(session.get("traceIds"), list) else []
        trace_ids = _list_values(traces)
        trace_count += len(trace_ids)
        if trace.get("replayReady"):
            replay_ready += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "sessionId": str(session.get("sessionId") or contract.get("sessionId") or ""),
                    "runtimeKind": runtime_kind,
                    "skillId": skill_id,
                    "pendingApprovals": approval_count,
                    "artifacts": artifact_count,
                    "creditsSpent": round(credits, 4),
                    "traceCount": len(trace_ids),
                    "replayReady": bool(trace.get("replayReady")),
                }
            )
    return {
        "total": len(sessions),
        "withContract": with_contract,
        "selectedSkill": selected_skill,
        "pendingApprovals": pending_approvals,
        "artifactOutputs": artifact_outputs,
        "traceIds": trace_count,
        "replayReady": replay_ready,
        "creditsSpent": round(total_credits, 4),
        "runtimeKinds": _sorted_counts(runtime_kinds),
        "sample": samples,
    }
