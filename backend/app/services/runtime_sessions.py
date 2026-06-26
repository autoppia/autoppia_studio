from __future__ import annotations

from typing import Any

from app.services.runtime_policy import approval_boundary_matrix
from app.services.runtime_policy import ordered_policy_boundaries


SESSION_HARDENING_ACTIONS = {
    "session_contract": {
        "area": "runtime",
        "severity": "high",
        "action": "Backfill the first-class session contract before using this Runtime Lab evidence for production decisions.",
    },
    "selected_skill": {
        "area": "capabilities",
        "severity": "medium",
        "action": "Link the session to a matched skill or record why the agent operated without a reusable capability.",
    },
    "trace_ids": {
        "area": "observability",
        "severity": "high",
        "action": "Attach trace identifiers so tool calls, approvals, artifacts and replay evidence remain auditable.",
    },
    "replay_ready": {
        "area": "evals",
        "severity": "medium",
        "action": "Resolve pending steps or approvals and capture enough trace data for deterministic replay.",
    },
    "failed_steps": {
        "area": "runtime",
        "severity": "high",
        "action": "Inspect failed Runtime Lab steps before promoting trajectories or skills.",
    },
    "pending_steps": {
        "area": "runtime",
        "severity": "medium",
        "action": "Finish or cancel pending Runtime Lab steps before treating the session as evidence.",
    },
    "pending_approvals": {
        "area": "approvals",
        "severity": "high",
        "action": "Resolve pending human approvals before delivering side effects or publishing the capability.",
    },
    "artifact_outputs": {
        "area": "artifacts",
        "severity": "medium",
        "action": "Capture business artifacts separately from the trace when the session produces customer-facing output.",
    },
}


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


def _session_hardening_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = SESSION_HARDENING_ACTIONS.get(
            gap,
            {
                "area": "runtime",
                "severity": "medium",
                "action": "Review Runtime Lab session evidence before production reuse.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


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
    required_for = ordered_policy_boundaries(list(approval_boundaries))
    matrix = approval_boundary_matrix(required_for, observed_boundaries=[boundary for boundary, count in boundary_counts.items() if count > 0])
    return {
        "boundaries": boundary_counts,
        "approvalRequiredFor": required_for,
        "approvalPolicy": matrix,
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
            "approvalPolicy": policy_boundary.get("approvalPolicy") if isinstance(policy_boundary.get("approvalPolicy"), dict) else {},
            "hasHumanBoundary": bool(policy_boundary.get("hasHumanBoundary")),
            "pendingConnectorApproval": str(summary.get("pendingConnectorApproval") or runtime_state.get("pendingConnectorApproval") or ""),
        },
        "outputs": {
            "artifactCount": artifact_count,
            "hasBusinessOutput": artifact_count > 0,
        },
    }


def build_runtime_lab(
    summary: dict[str, Any],
    *,
    artifact_count: int,
    pending_approval_count: int,
) -> dict[str, Any]:
    runtime_state = summary.get("runtimeState") if isinstance(summary.get("runtimeState"), dict) else {}
    runtime_metrics = summary.get("runtimeMetrics") if isinstance(summary.get("runtimeMetrics"), dict) else {}
    policy_boundary = summary.get("runtimePolicyBoundary") if isinstance(summary.get("runtimePolicyBoundary"), dict) else {}
    evidence = summary.get("runtimeEvidence") if isinstance(summary.get("runtimeEvidence"), dict) else {}
    trace = evidence.get("trace") if isinstance(evidence.get("trace"), dict) else {}
    timeline = summary.get("runtimeTimeline") if isinstance(summary.get("runtimeTimeline"), list) else []
    runtime_kind = str(summary.get("runtimeKind") or runtime_metrics.get("runtimeKind") or "api")
    runtime_type = runtime_type_from_kind(runtime_kind)
    tool_steps = [
        {
            "index": item.get("index"),
            "action": str(item.get("action") or ""),
            "label": str(item.get("label") or item.get("action") or ""),
            "status": str(item.get("status") or "ok"),
            "traceId": str(item.get("traceId") or ""),
            "elapsedSeconds": _safe_float(item.get("elapsedSeconds")),
        }
        for item in timeline
        if isinstance(item, dict) and item.get("activity") == "tool"
    ]
    skill_steps = [item for item in timeline if isinstance(item, dict) and item.get("activity") == "skill"]
    browser_steps = [item for item in timeline if isinstance(item, dict) and item.get("activity") == "browser"]
    approved_calls = runtime_state.get("approvedConnectorToolCalls") if isinstance(runtime_state.get("approvedConnectorToolCalls"), list) else []
    return {
        "controlPlane": {
            "sessionId": str(summary.get("sessionId") or ""),
            "runtimeKind": runtime_kind,
            "runtimeType": runtime_type,
            "sourceKind": str(summary.get("sourceKind") or runtime_state.get("sourceKind") or ""),
            "agentId": str(summary.get("agentId") or ""),
            "agentName": str(summary.get("agentName") or ""),
            "workItemId": str(summary.get("workItemId") or runtime_state.get("workItemId") or ""),
            "runId": str(summary.get("runId") or runtime_state.get("runId") or ""),
        },
        "timeline": {
            "steps": len(timeline),
            "browserSteps": len(browser_steps),
            "toolSteps": len(tool_steps),
            "skillSteps": len(skill_steps),
            "failedSteps": int(trace.get("failedSteps") or 0),
            "pendingSteps": int(trace.get("pendingSteps") or 0),
            "lastAction": str(summary.get("latestAction") or ""),
            "lastActivityAt": str(summary.get("latestActivityAt") or ""),
            "traceIds": trace.get("traceIds") if isinstance(trace.get("traceIds"), list) else runtime_metrics.get("traceIds", []),
            "replayReady": bool(trace.get("replayReady")),
        },
        "toolCalls": {
            "total": int(summary.get("connectorActionCount") or runtime_metrics.get("connectorActionCount") or 0),
            "approved": len(approved_calls),
            "pendingApproval": str(summary.get("pendingConnectorApproval") or runtime_state.get("pendingConnectorApproval") or ""),
            "sample": tool_steps[:8],
        },
        "skillMatch": {
            "matched": bool(summary.get("matchedSkillId") or summary.get("matchedSkillName") or skill_steps),
            "skillId": str(summary.get("matchedSkillId") or runtime_state.get("matchedSkillId") or ""),
            "skillName": str(summary.get("matchedSkillName") or runtime_state.get("matchedSkillName") or runtime_state.get("matchedSkill") or ""),
        },
        "approvals": {
            "pending": pending_approval_count,
            "approvedConnectorCalls": len(approved_calls),
            "approvedConnectorToolCalls": _list_values(approved_calls),
            "pendingConnectorApproval": str(summary.get("pendingConnectorApproval") or runtime_state.get("pendingConnectorApproval") or ""),
            "requiredFor": policy_boundary.get("approvalRequiredFor") if isinstance(policy_boundary.get("approvalRequiredFor"), list) else [],
            "approvalPolicy": policy_boundary.get("approvalPolicy") if isinstance(policy_boundary.get("approvalPolicy"), dict) else {},
            "hasHumanBoundary": bool(policy_boundary.get("hasHumanBoundary")),
        },
        "outputs": {
            "artifacts": artifact_count,
            "hasBusinessOutput": artifact_count > 0,
            "creditsSpent": _safe_float(summary.get("creditsSpent") or runtime_metrics.get("creditsSpent")),
            "durationSeconds": _safe_float(runtime_metrics.get("durationSeconds")),
            "lastStepSeconds": _safe_float(runtime_metrics.get("lastStepSeconds")),
        },
    }


def build_runtime_audit_trail(
    summary: dict[str, Any],
    *,
    action_history: list[Any],
    artifact_count: int,
    pending_approval_count: int,
) -> dict[str, Any]:
    runtime_state = summary.get("runtimeState") if isinstance(summary.get("runtimeState"), dict) else {}
    policy_boundary = summary.get("runtimePolicyBoundary") if isinstance(summary.get("runtimePolicyBoundary"), dict) else {}
    events: list[dict[str, Any]] = [
        {
            "event": "session.started",
            "actor": "user",
            "boundary": "read",
            "at": summary.get("createdAt"),
            "traceId": str(summary.get("sessionId") or ""),
            "description": "Runtime session created.",
        }
    ]
    for index, item in enumerate(action_history):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("name") or "").strip()
        if not action:
            continue
        activity = "browser" if action.startswith("browser.") else "skill" if action == "skill.use" else "runtime" if action.startswith(("router.", "runtime.")) else "tool"
        events.append(
            {
                "event": f"{activity}.action",
                "actor": "agent_runtime",
                "boundary": session_action_policy_boundary(action),
                "action": action,
                "status": str(item.get("status") or "ok"),
                "at": session_action_timestamp(item),
                "traceId": str(item.get("traceId") or item.get("toolCallId") or ""),
                "description": pretty_session_action(action),
            }
        )
        if item.get("approvalKey") or item.get("approvalRequired"):
            events.append(
                {
                    "event": "approval.boundary",
                    "actor": "agent_runtime",
                    "boundary": session_action_policy_boundary(action),
                    "action": action,
                    "status": "pending",
                    "at": session_action_timestamp(item),
                    "traceId": str(item.get("approvalKey") or ""),
                    "description": "Human approval required before side effect execution.",
                }
            )
        if index >= 24:
            break
    if runtime_state.get("matchedSkillId") or runtime_state.get("matchedSkillName"):
        events.append(
            {
                "event": "skill.matched",
                "actor": "agent_runtime",
                "boundary": "read",
                "skillId": str(runtime_state.get("matchedSkillId") or ""),
                "status": "matched",
                "at": str(summary.get("latestActivityAt") or ""),
                "traceId": str(runtime_state.get("matchedTrajectoryId") or ""),
                "description": str(runtime_state.get("matchedSkillName") or runtime_state.get("matchedSkill") or "Skill matched"),
            }
        )
    pending_approval = str(summary.get("pendingConnectorApproval") or runtime_state.get("pendingConnectorApproval") or "")
    if pending_approval or pending_approval_count:
        events.append(
            {
                "event": "approval.pending",
                "actor": "human",
                "boundary": session_action_policy_boundary(pending_approval),
                "status": "pending",
                "at": str(summary.get("latestActivityAt") or ""),
                "traceId": pending_approval,
                "description": "Runtime is waiting for human approval.",
            }
        )
    if artifact_count:
        events.append(
            {
                "event": "artifact.created",
                "actor": "agent_runtime",
                "boundary": "draft",
                "status": "created",
                "at": str(summary.get("latestActivityAt") or ""),
                "traceId": str(summary.get("sessionId") or ""),
                "description": f"{artifact_count} business artifact(s) created.",
            }
        )
    approval_required_for = policy_boundary.get("approvalRequiredFor") if isinstance(policy_boundary.get("approvalRequiredFor"), list) else []
    return {
        "sessionId": str(summary.get("sessionId") or ""),
        "uniform": True,
        "eventCount": len(events),
        "events": events,
        "boundaries": policy_boundary.get("boundaries") if isinstance(policy_boundary.get("boundaries"), dict) else {},
        "approvalRequiredFor": approval_required_for,
        "hasHumanBoundary": bool(policy_boundary.get("hasHumanBoundary")),
        "artifactCount": artifact_count,
        "pendingApprovalCount": pending_approval_count,
    }


def session_runtime_kind(session: dict[str, Any]) -> str:
    contract = session.get("sessionContract") if isinstance(session.get("sessionContract"), dict) else {}
    runtime = contract.get("agentRuntime") if isinstance(contract.get("agentRuntime"), dict) else {}
    runtime_kind = str(runtime.get("runtimeType") or runtime.get("runtimeKind") or session.get("runtimeType") or session.get("runtimeKind") or "").strip()
    if runtime_kind:
        return runtime_type_from_kind(runtime_kind)
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


def runtime_type_from_kind(value: str) -> str:
    clean = str(value or "").strip().lower()
    if clean in {"api", "browser", "hybrid"}:
        return f"{clean}_runtime"
    if clean in {"api_runtime", "browser_runtime", "hybrid_runtime"}:
        return clean
    if clean:
        return clean
    return "api_runtime"


def runtime_kind_from_type(value: str) -> str:
    clean = runtime_type_from_kind(value)
    if clean in {"api_runtime", "browser_runtime", "hybrid_runtime"}:
        return clean.replace("_runtime", "")
    return clean


def build_session_contract(
    summary: dict[str, Any],
    *,
    artifact_count: int,
    pending_approval_count: int,
) -> dict[str, Any]:
    runtime_state = summary.get("runtimeState") if isinstance(summary.get("runtimeState"), dict) else {}
    runtime_metrics = summary.get("runtimeMetrics") if isinstance(summary.get("runtimeMetrics"), dict) else {}
    runtime_lab = summary.get("runtimeLab") if isinstance(summary.get("runtimeLab"), dict) else {}
    runtime_evidence = summary.get("runtimeEvidence") if isinstance(summary.get("runtimeEvidence"), dict) else {}
    runtime_policy = summary.get("runtimePolicyBoundary") if isinstance(summary.get("runtimePolicyBoundary"), dict) else {}
    skill_match = runtime_lab.get("skillMatch") if isinstance(runtime_lab.get("skillMatch"), dict) else {}
    outputs = runtime_lab.get("outputs") if isinstance(runtime_lab.get("outputs"), dict) else {}
    approvals = runtime_lab.get("approvals") if isinstance(runtime_lab.get("approvals"), dict) else {}
    trace = runtime_evidence.get("trace") if isinstance(runtime_evidence.get("trace"), dict) else {}
    runtime_kind = runtime_kind_from_type(str(summary.get("runtimeType") or summary.get("runtimeKind") or runtime_metrics.get("runtimeType") or runtime_metrics.get("runtimeKind") or "api"))
    runtime_type = runtime_type_from_kind(str(summary.get("runtimeType") or runtime_metrics.get("runtimeType") or runtime_kind))
    return {
        "contractVersion": "2026-06-25",
        "sessionId": str(summary.get("sessionId") or ""),
        "agentRuntime": {
            "runtimeKind": runtime_kind,
            "runtimeType": runtime_type,
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
            "approvedConnectorToolCalls": (
                approvals.get("approvedConnectorToolCalls")
                if isinstance(approvals.get("approvedConnectorToolCalls"), list)
                else _list_values(runtime_state.get("approvedConnectorToolCalls"))
            ),
            "pendingConnectorApproval": str(
                approvals.get("pendingConnectorApproval")
                or summary.get("pendingConnectorApproval")
                or runtime_state.get("pendingConnectorApproval")
                or ""
            ),
            "requiredFor": approvals.get("requiredFor") if isinstance(approvals.get("requiredFor"), list) else [],
            "approvalPolicy": (
                approvals.get("approvalPolicy")
                if isinstance(approvals.get("approvalPolicy"), dict)
                else runtime_policy.get("approvalPolicy")
                if isinstance(runtime_policy.get("approvalPolicy"), dict)
                else {}
            ),
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


def _runtime_session_gate(
    *,
    total: int,
    with_contract: int,
    selected_skill: int,
    pending_approvals: int,
    artifact_outputs: int,
    replay_ready: int,
    trace_count: int,
    gap_counts: dict[str, int],
) -> dict[str, Any]:
    checks = {
        "sessionsObserved": total > 0,
        "contractsDurable": total > 0 and with_contract == total,
        "selectedSkillLinked": total > 0 and selected_skill == total,
        "traceAuditable": total > 0 and trace_count >= total and not gap_counts.get("trace_ids"),
        "replayReady": total > 0 and replay_ready == total,
        "approvalsResolved": pending_approvals == 0,
        "artifactOutputsCaptured": total > 0 and artifact_outputs >= total and not gap_counts.get("artifact_outputs"),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "state": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "checks": checks,
        "blockers": blockers,
        "hardeningPlaybook": _session_hardening_playbook(gap_counts),
    }


def summarize_session_contracts(sessions: list[dict[str, Any]], *, sample_limit: int = 8) -> dict[str, Any]:
    with_contract = 0
    selected_skill = 0
    pending_approvals = 0
    artifact_outputs = 0
    replay_ready = 0
    total_credits = 0.0
    total_duration_seconds = 0.0
    trace_count = 0
    timeline_steps = 0
    browser_steps = 0
    tool_steps = 0
    skill_steps = 0
    failed_steps = 0
    pending_steps = 0
    runtime_kinds: list[str] = []
    samples: list[dict[str, Any]] = []
    gap_counts: dict[str, int] = {}
    for session in sessions:
        contract = session.get("sessionContract") if isinstance(session.get("sessionContract"), dict) else {}
        runtime_lab = session.get("runtimeLab") if isinstance(session.get("runtimeLab"), dict) else {}
        lab_timeline = runtime_lab.get("timeline") if isinstance(runtime_lab.get("timeline"), dict) else {}
        runtime = contract.get("agentRuntime") if isinstance(contract.get("agentRuntime"), dict) else {}
        skill = contract.get("selectedSkill") if isinstance(contract.get("selectedSkill"), dict) else {}
        approvals = contract.get("approvalState") if isinstance(contract.get("approvalState"), dict) else {}
        artifacts = contract.get("artifactState") if isinstance(contract.get("artifactState"), dict) else {}
        cost = contract.get("costState") if isinstance(contract.get("costState"), dict) else {}
        trace = contract.get("traceState") if isinstance(contract.get("traceState"), dict) else {}
        if contract:
            with_contract += 1
        else:
            gap_counts["session_contract"] = gap_counts.get("session_contract", 0) + 1
        runtime_type = session_runtime_kind(session)
        runtime_kind = runtime_kind_from_type(str(runtime.get("runtimeKind") or runtime_type)) or "unknown"
        runtime_kinds.append(runtime_kind)
        skill_id = str(skill.get("skillId") or session.get("matchedSkillId") or "").strip()
        if skill.get("matched") or skill_id:
            selected_skill += 1
        else:
            gap_counts["selected_skill"] = gap_counts.get("selected_skill", 0) + 1
        approval_count = int(approvals.get("pending") or session.get("pendingApprovalCount") or 0)
        pending_approvals += approval_count
        if approval_count:
            gap_counts["pending_approvals"] = gap_counts.get("pending_approvals", 0) + approval_count
        artifact_count = int(artifacts.get("count") or session.get("artifactCount") or 0)
        artifact_outputs += artifact_count
        if not artifact_count:
            gap_counts["artifact_outputs"] = gap_counts.get("artifact_outputs", 0) + 1
        credits = _safe_float(cost.get("creditsSpent") or session.get("creditsSpent"))
        total_credits += credits
        duration_seconds = _safe_float(cost.get("durationSeconds") or session.get("durationSeconds"))
        total_duration_seconds += duration_seconds
        traces = trace.get("traceIds") if isinstance(trace.get("traceIds"), list) else session.get("traceIds") if isinstance(session.get("traceIds"), list) else []
        trace_ids = _list_values(traces)
        trace_count += len(trace_ids)
        if not trace_ids:
            gap_counts["trace_ids"] = gap_counts.get("trace_ids", 0) + 1
        timeline_count = int(trace.get("timelineSteps") or lab_timeline.get("steps") or 0)
        browser_count = int(lab_timeline.get("browserSteps") or 0)
        tool_count = int(lab_timeline.get("toolSteps") or 0)
        skill_count = int(lab_timeline.get("skillSteps") or 0)
        failed_count = int(trace.get("failedSteps") or lab_timeline.get("failedSteps") or 0)
        pending_count = int(trace.get("pendingSteps") or lab_timeline.get("pendingSteps") or 0)
        timeline_steps += timeline_count
        browser_steps += browser_count
        tool_steps += tool_count
        skill_steps += skill_count
        failed_steps += failed_count
        pending_steps += pending_count
        if trace.get("replayReady"):
            replay_ready += 1
        else:
            gap_counts["replay_ready"] = gap_counts.get("replay_ready", 0) + 1
        if failed_count:
            gap_counts["failed_steps"] = gap_counts.get("failed_steps", 0) + failed_count
        if pending_count:
            gap_counts["pending_steps"] = gap_counts.get("pending_steps", 0) + pending_count
        if len(samples) < sample_limit:
            samples.append(
                {
                    "sessionId": str(session.get("sessionId") or contract.get("sessionId") or ""),
                    "runtimeKind": runtime_kind,
                    "runtimeType": runtime_type,
                    "skillId": skill_id,
                    "pendingApprovals": approval_count,
                    "artifacts": artifact_count,
                    "creditsSpent": round(credits, 4),
                    "durationSeconds": round(duration_seconds, 3),
                    "traceCount": len(trace_ids),
                    "timelineSteps": timeline_count,
                    "browserSteps": browser_count,
                    "toolSteps": tool_count,
                    "skillSteps": skill_count,
                    "replayReady": bool(trace.get("replayReady")),
                }
            )
    hardening_playbook = _session_hardening_playbook(gap_counts)
    return {
        "total": len(sessions),
        "withContract": with_contract,
        "selectedSkill": selected_skill,
        "pendingApprovals": pending_approvals,
        "artifactOutputs": artifact_outputs,
        "traceIds": trace_count,
        "replayReady": replay_ready,
        "creditsSpent": round(total_credits, 4),
        "durationSeconds": round(total_duration_seconds, 3),
        "runtimeKinds": _sorted_counts(runtime_kinds),
        "timeline": {
            "steps": timeline_steps,
            "browserSteps": browser_steps,
            "toolSteps": tool_steps,
            "skillSteps": skill_steps,
            "failedSteps": failed_steps,
            "pendingSteps": pending_steps,
            "replayReadySessions": replay_ready,
        },
        "sample": samples,
        "runtimeSessionGate": _runtime_session_gate(
            total=len(sessions),
            with_contract=with_contract,
            selected_skill=selected_skill,
            pending_approvals=pending_approvals,
            artifact_outputs=artifact_outputs,
            replay_ready=replay_ready,
            trace_count=trace_count,
            gap_counts=gap_counts,
        ),
        "hardeningPlaybook": hardening_playbook,
    }
