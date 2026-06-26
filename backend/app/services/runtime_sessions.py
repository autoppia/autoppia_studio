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


def dedupe_trace_ids(values: list[Any]) -> list[str]:
    trace_ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        trace_ids.append(clean)
    return trace_ids


def build_runtime_metrics(
    *,
    action_history: list[Any],
    runtime_state: dict[str, Any],
    credits_spent: float,
    browser_action_count: int,
    connector_action_count: int,
    runtime_kind: str,
) -> dict[str, Any]:
    step_latencies = [
        _safe_float(item.get("elapsedSeconds") or item.get("durationSeconds") or item.get("latencySeconds"))
        for item in action_history
        if isinstance(item, dict)
    ]
    step_latencies = [value for value in step_latencies if value > 0]
    runtime_duration = _safe_float(
        runtime_state.get("durationSeconds")
        or runtime_state.get("elapsedSeconds")
        or runtime_state.get("latencySeconds")
    )
    duration_seconds = runtime_duration if runtime_duration > 0 else round(sum(step_latencies), 3)
    last_step_seconds = step_latencies[-1] if step_latencies else 0.0
    trace_ids = dedupe_trace_ids([
        runtime_state.get("traceId"),
        runtime_state.get("trace_id"),
        runtime_state.get("runId"),
        runtime_state.get("workItemId"),
        *[
            item.get("traceId") or item.get("trace_id") or item.get("runId")
            for item in action_history
            if isinstance(item, dict)
        ],
    ])
    return {
        "runtimeKind": runtime_kind,
        "creditsSpent": credits_spent,
        "durationSeconds": round(duration_seconds, 3),
        "lastStepSeconds": round(last_step_seconds, 3),
        "browserActionCount": browser_action_count,
        "connectorActionCount": connector_action_count,
        "stepLatencyCount": len(step_latencies),
        "traceIds": trace_ids,
    }


def session_action_policy_boundary(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if not normalized:
        return "read"
    if any(token in normalized for token in ("send", "submit", "publish")):
        return "send"
    if any(token in normalized for token in ("update", "delete", "write", "post", "create", "save", "upload")):
        return "write"
    if any(token in normalized for token in ("draft", "artifact", "compose", "prepare")):
        return "draft"
    return "read"


def build_runtime_policy_boundary(
    *,
    action_history: list[Any],
    runtime_state: dict[str, Any],
    artifact_count: int = 0,
    pending_approval_count: int = 0,
) -> dict[str, Any]:
    boundary_counts = {"read": 0, "draft": 0, "write": 0, "send": 0}
    approval_boundaries: set[str] = set()
    approved_calls = runtime_state.get("approvedConnectorToolCalls") if isinstance(runtime_state.get("approvedConnectorToolCalls"), list) else []
    pending_approval = str(runtime_state.get("pendingConnectorApproval") or "").strip()
    for item in action_history:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("name") or "").strip()
        if not action:
            continue
        boundary = session_action_policy_boundary(action)
        boundary_counts[boundary] += 1
        if item.get("approvalKey") or item.get("approvalRequired"):
            approval_boundaries.add(boundary)
    if artifact_count:
        boundary_counts["draft"] += artifact_count
    if pending_approval:
        approval_boundaries.add(session_action_policy_boundary(pending_approval))
    for call in approved_calls:
        approval_boundaries.add(session_action_policy_boundary(str(call or "")))
    return {
        "boundaries": boundary_counts,
        "approvalRequiredFor": sorted(approval_boundaries, key=["read", "draft", "write", "send"].index),
        "pendingApprovalCount": pending_approval_count,
        "approvedApprovalCount": len(approved_calls),
        "artifactCount": artifact_count,
        "hasHumanBoundary": bool(pending_approval_count or pending_approval or approved_calls or approval_boundaries),
    }


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


def build_runtime_evidence(
    summary: dict[str, Any],
    *,
    artifact_count: int,
    pending_approval_count: int,
) -> dict[str, Any]:
    runtime_state = summary.get("runtimeState") if isinstance(summary.get("runtimeState"), dict) else {}
    runtime_metrics = summary.get("runtimeMetrics") if isinstance(summary.get("runtimeMetrics"), dict) else {}
    policy_boundary = summary.get("runtimePolicyBoundary") if isinstance(summary.get("runtimePolicyBoundary"), dict) else {}
    timeline = summary.get("runtimeTimeline") if isinstance(summary.get("runtimeTimeline"), list) else []
    trace_ids = runtime_metrics.get("traceIds") if isinstance(runtime_metrics.get("traceIds"), list) else []
    failed_steps = [item for item in timeline if isinstance(item, dict) and item.get("status") == "failed"]
    pending_steps = [item for item in timeline if isinstance(item, dict) and item.get("status") == "pending"]
    capability_refs = {
        "skillId": str(summary.get("matchedSkillId") or runtime_state.get("matchedSkillId") or ""),
        "skillName": str(summary.get("matchedSkillName") or runtime_state.get("matchedSkillName") or runtime_state.get("matchedSkill") or ""),
        "workItemId": str(summary.get("workItemId") or runtime_state.get("workItemId") or ""),
        "runId": str(summary.get("runId") or runtime_state.get("runId") or ""),
    }
    capability_refs["linked"] = any(capability_refs[key] for key in ("skillId", "workItemId", "runId"))
    browser_count = int(summary.get("browserActionCount") or runtime_metrics.get("browserActionCount") or 0)
    connector_count = int(summary.get("connectorActionCount") or runtime_metrics.get("connectorActionCount") or 0)
    return {
        "summary": {
            "runtimeKind": str(summary.get("runtimeKind") or runtime_metrics.get("runtimeKind") or "api"),
            "toolCalls": connector_count,
            "browserSteps": browser_count,
            "artifacts": artifact_count,
            "pendingApprovals": pending_approval_count,
            "creditsSpent": _safe_float(summary.get("creditsSpent") or runtime_metrics.get("creditsSpent")),
            "durationSeconds": _safe_float(runtime_metrics.get("durationSeconds")),
        },
        "trace": {
            "traceIds": trace_ids,
            "traceCount": len(trace_ids),
            "timelineSteps": len(timeline),
            "failedSteps": len(failed_steps),
            "pendingSteps": len(pending_steps),
            "lastTraceId": str(trace_ids[-1]) if trace_ids else "",
            "replayReady": bool(timeline and not pending_steps and not pending_approval_count),
        },
        "capabilityRefs": capability_refs,
        "approvalBoundary": {
            "approvalRequiredFor": policy_boundary.get("approvalRequiredFor") if isinstance(policy_boundary.get("approvalRequiredFor"), list) else [],
            "hasHumanBoundary": bool(policy_boundary.get("hasHumanBoundary")),
            "pendingConnectorApproval": str(summary.get("pendingConnectorApproval") or runtime_state.get("pendingConnectorApproval") or ""),
        },
        "outputs": {
            "artifactCount": artifact_count,
            "hasBusinessOutput": artifact_count > 0,
        },
    }


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
