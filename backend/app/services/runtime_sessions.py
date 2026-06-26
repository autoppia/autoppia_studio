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


def pretty_session_action(action: str) -> str:
    if not action:
        return "Waiting for task"
    if action == "skill.use":
        return "Using skill"
    if action.startswith("browser.") or action.startswith("user."):
        normalized = action.replace("browser.", "").replace("user.", "")
        return " ".join(word[:1].upper() + word[1:] for word in normalized.split("_") if word)
    return action


def session_action_timestamp(entry: dict[str, Any]) -> str:
    for key in ("emittedAt", "createdAt", "timestamp", "at"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def session_action_activity(action: str) -> str:
    normalized = str(action or "").lower()
    if normalized.startswith("browser."):
        return "browser"
    if normalized.startswith("skill.") or "skill" in normalized:
        return "skill"
    if normalized in {"browser.done", "done", "runtime.done"} or normalized.endswith(".done"):
        return "done"
    return "tool"


def session_action_status(entry: dict[str, Any]) -> str:
    raw = str(entry.get("status") or entry.get("state") or "").strip().lower()
    if raw in {"failed", "fail", "error"}:
        return "failed"
    if raw in {"pending", "running", "waiting"}:
        return "pending"
    result = entry.get("success")
    if result is False:
        return "failed"
    return "ok"


def build_runtime_timeline(action_history: list[Any]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for index, item in enumerate(action_history):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("name") or "").strip()
        if not action:
            continue
        timeline.append(
            {
                "index": index,
                "action": action,
                "label": pretty_session_action(action),
                "activity": session_action_activity(action),
                "status": session_action_status(item),
                "emittedAt": session_action_timestamp(item),
                "elapsedSeconds": _safe_float(item.get("elapsedSeconds") or item.get("durationSeconds") or item.get("latencySeconds")),
                "traceId": str(item.get("traceId") or item.get("trace_id") or item.get("runId") or ""),
                "toolCallId": str(item.get("toolCallId") or item.get("callId") or ""),
                "approvalKey": str(item.get("approvalKey") or ""),
                "artifactId": str(item.get("artifactId") or ""),
                "skillId": str(item.get("skillId") or item.get("matchedSkillId") or ""),
            }
        )
    return timeline


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


def build_session_contract(
    summary: dict[str, Any],
    *,
    artifact_count: int,
    pending_approval_count: int,
) -> dict[str, Any]:
    runtime_metrics = summary.get("runtimeMetrics") if isinstance(summary.get("runtimeMetrics"), dict) else {}
    runtime_lab = summary.get("runtimeLab") if isinstance(summary.get("runtimeLab"), dict) else {}
    runtime_evidence = summary.get("runtimeEvidence") if isinstance(summary.get("runtimeEvidence"), dict) else {}
    runtime_policy = summary.get("runtimePolicyBoundary") if isinstance(summary.get("runtimePolicyBoundary"), dict) else {}
    skill_match = runtime_lab.get("skillMatch") if isinstance(runtime_lab.get("skillMatch"), dict) else {}
    outputs = runtime_lab.get("outputs") if isinstance(runtime_lab.get("outputs"), dict) else {}
    approvals = runtime_lab.get("approvals") if isinstance(runtime_lab.get("approvals"), dict) else {}
    trace = runtime_evidence.get("trace") if isinstance(runtime_evidence.get("trace"), dict) else {}
    return {
        "contractVersion": "2026-06-25",
        "sessionId": str(summary.get("sessionId") or ""),
        "agentRuntime": {
            "runtimeKind": str(summary.get("runtimeKind") or runtime_metrics.get("runtimeKind") or "api"),
            "sourceKind": str(summary.get("sourceKind") or ""),
            "agentId": str(summary.get("agentId") or ""),
            "agentName": str(summary.get("agentName") or ""),
            "workItemId": str(summary.get("workItemId") or ""),
            "runId": str(summary.get("runId") or ""),
        },
        "selectedSkill": {
            "matched": bool(skill_match.get("matched") or summary.get("matchedSkillId") or summary.get("matchedSkillName")),
            "skillId": str(skill_match.get("skillId") or summary.get("matchedSkillId") or ""),
            "skillName": str(skill_match.get("skillName") or summary.get("matchedSkillName") or ""),
        },
        "approvalState": {
            "pending": pending_approval_count,
            "approvedConnectorCalls": int(approvals.get("approvedConnectorCalls") or 0),
            "requiredFor": approvals.get("requiredFor") if isinstance(approvals.get("requiredFor"), list) else [],
            "hasHumanBoundary": bool(approvals.get("hasHumanBoundary") or runtime_policy.get("hasHumanBoundary")),
        },
        "artifactState": {
            "count": artifact_count,
            "hasBusinessOutput": bool(outputs.get("hasBusinessOutput") or artifact_count > 0),
        },
        "costState": {
            "creditsSpent": _safe_float(outputs.get("creditsSpent") or summary.get("creditsSpent") or runtime_metrics.get("creditsSpent")),
            "durationSeconds": _safe_float(outputs.get("durationSeconds") or runtime_metrics.get("durationSeconds")),
            "lastStepSeconds": _safe_float(outputs.get("lastStepSeconds") or runtime_metrics.get("lastStepSeconds")),
        },
        "traceState": {
            "traceIds": trace.get("traceIds") if isinstance(trace.get("traceIds"), list) else summary.get("traceIds", []),
            "traceCount": int(trace.get("traceCount") or 0),
            "timelineSteps": int(trace.get("timelineSteps") or 0),
            "replayReady": bool(trace.get("replayReady")),
        },
    }


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
