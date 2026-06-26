from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def _list_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item or "").strip()]


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_domains(values: list[Any]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = str(value or "").strip().lower()
        if not raw:
            continue
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or raw).strip().lower()
        if host and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def work_orchestration_audit_trail(
    doc: dict[str, Any],
    *,
    queue_state: str,
    trigger_type: str,
    deadline_state: str,
    pending_approval_count: int,
    latest_credits_spent: float,
    budget_exhausted: bool,
    retry_count: int,
    review_blocked: bool,
    browser_policy_state: str,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = [
        {
            "event": "work.queued",
            "actor": "work_orchestration",
            "state": queue_state,
            "at": doc.get("createdAt"),
            "description": "Work item entered the orchestration queue.",
        }
    ]
    if trigger_type == "scheduled":
        events.append(
            {
                "event": "work.scheduled",
                "actor": "scheduler",
                "state": deadline_state,
                "at": doc.get("nextRunAt", ""),
                "description": "Scheduled run window tracked by Work Orchestration.",
            }
        )
    if retry_count > 0:
        events.append(
            {
                "event": "work.retry",
                "actor": "worker",
                "state": "retry_recorded",
                "count": retry_count,
                "at": doc.get("updatedAt"),
                "description": f"{retry_count} retry attempt(s) recorded.",
            }
        )
    if latest_credits_spent > 0 or budget_exhausted:
        events.append(
            {
                "event": "work.budget",
                "actor": "metering",
                "state": "exhausted" if budget_exhausted else "tracked",
                "creditsSpent": latest_credits_spent,
                "at": doc.get("updatedAt"),
                "description": "Runtime budget usage captured for this work item.",
            }
        )
    if pending_approval_count or review_blocked:
        events.append(
            {
                "event": "work.approval_block",
                "actor": "human",
                "state": "pending",
                "pendingApprovalCount": pending_approval_count,
                "at": doc.get("updatedAt"),
                "description": "Work item is blocked on human review or approval.",
            }
        )
    if browser_policy_state == "unrestricted":
        events.append(
            {
                "event": "work.browser_policy",
                "actor": "control_plane",
                "state": "unrestricted",
                "at": doc.get("updatedAt"),
                "description": "Browser-enabled work has no domain allowlist.",
            }
        )
    return {
        "uniform": True,
        "eventCount": len(events),
        "events": events,
        "hasApprovalCheckpoint": bool(pending_approval_count or review_blocked),
        "hasBudgetCheckpoint": bool(latest_credits_spent > 0 or budget_exhausted),
        "hasRetryCheckpoint": retry_count > 0,
        "hasScheduleCheckpoint": trigger_type == "scheduled",
        "hasBrowserPolicyCheckpoint": browser_policy_state != "disabled",
    }


def build_work_orchestration_contract(
    doc: dict[str, Any],
    *,
    pending_approval_count: int,
    approval_refs: list[dict[str, Any]] | None = None,
    latest_credits_spent: float,
    review_blocked: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    max_budget = _safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun", 0.0)))
    max_per_run = _safe_float(doc.get("maxCreditsPerRun"))
    retry_count = max(0, len(doc.get("runHistory") if isinstance(doc.get("runHistory"), list) else []) - 1)
    budget_remaining = max(0.0, max_budget - latest_credits_spent) if max_budget > 0 else 0.0
    budget_exhausted = bool(max_budget > 0 and latest_credits_spent >= max_budget)
    queue_state = str(doc.get("status") or "TODO")
    trigger_type = str(doc.get("triggerType") or "manual")
    next_run_at = str(doc.get("nextRunAt") or "")
    browser_enabled = bool(doc.get("browserEnabled", True))
    allowed_domains = _normalize_domains(doc.get("allowedDomains") if isinstance(doc.get("allowedDomains"), list) else [])
    browser_restricted = bool(doc.get("browserRestrictedByDomain")) if doc.get("browserRestrictedByDomain") is not None else bool(allowed_domains)
    browser_default_use = str(doc.get("browserDefaultUse") or "exception")
    browser_policy_state = "disabled" if not browser_enabled else "restricted" if browser_restricted and allowed_domains else "unrestricted"
    deadline_at = _parse_iso(next_run_at) if next_run_at else None
    now = now or datetime.now(timezone.utc)
    minutes_until_due = round((deadline_at - now).total_seconds() / 60, 1) if deadline_at else None
    overdue_minutes = round((now - deadline_at).total_seconds() / 60, 1) if deadline_at and deadline_at < now else 0.0
    if trigger_type != "scheduled":
        deadline_state = "manual"
    elif not deadline_at:
        deadline_state = "missing_schedule"
    elif overdue_minutes >= 15:
        deadline_state = "overdue"
    elif overdue_minutes > 0:
        deadline_state = "due"
    else:
        deadline_state = "upcoming"
    run_attempts = len(doc.get("runHistory") if isinstance(doc.get("runHistory"), list) else [])
    max_steps = int(doc.get("maxSteps", 8) or 8)
    pending_approval_refs = [
        {
            "approvalId": str(ref.get("approvalId") or ""),
            "title": str(ref.get("title") or ""),
            "actionUrl": str(ref.get("actionUrl") or ref.get("action_url") or ""),
            "sourceKind": str(ref.get("sourceKind") or ""),
        }
        for ref in approval_refs or []
        if str(ref.get("approvalId") or "").strip()
    ][:8]
    blockers: list[str] = []
    next_actions: list[str] = []
    if review_blocked:
        blockers.append("pending_approval")
        next_actions.append("Resolve pending approvals before allowing unattended execution.")
    if budget_exhausted:
        blockers.append("budget_exhausted")
        next_actions.append("Increase the work budget or reduce runtime scope before retrying.")
    if queue_state.upper() in {"FAILED", "ERROR", "BUDGET_EXHAUSTED"}:
        blockers.append("failed_state")
        next_actions.append("Review the latest run result and retry once the cause is fixed.")
    if trigger_type == "scheduled" and not next_run_at:
        blockers.append("missing_schedule")
        next_actions.append("Set the next scheduled run time or switch this item to manual.")
    if trigger_type == "scheduled" and browser_policy_state == "unrestricted":
        blockers.append("missing_browser_allowlist")
        next_actions.append("Add allowed domains before running browser-enabled scheduled work unattended.")
    if not blockers and trigger_type == "manual":
        next_actions.append("Manual work is ready; schedule it if it should run unattended.")
    if not blockers and deadline_state == "overdue":
        next_actions.append("Scheduled work is overdue; confirm the worker is healthy or run it manually.")
    elif not blockers and deadline_state == "due":
        next_actions.append("Scheduled work is due now and can be claimed by the worker loop.")
    elif not blockers and trigger_type == "scheduled":
        next_actions.append("Scheduled work can run under the current budget, retry and approval policy.")
    gate_state = "blocked" if blockers else "scheduled" if trigger_type == "scheduled" else "manual_ready"
    sla_state = "blocked" if review_blocked else deadline_state if trigger_type == "scheduled" else "manual"
    audit_trail = work_orchestration_audit_trail(
        doc,
        queue_state=queue_state,
        trigger_type=trigger_type,
        deadline_state=deadline_state,
        pending_approval_count=pending_approval_count,
        latest_credits_spent=latest_credits_spent,
        budget_exhausted=budget_exhausted,
        retry_count=retry_count,
        review_blocked=review_blocked,
        browser_policy_state=browser_policy_state,
    )
    return {
        "queueState": queue_state,
        "triggerType": trigger_type,
        "schedule": {
            "frequency": str(doc.get("scheduleFrequency") or "none"),
            "time": str(doc.get("scheduleTime") or "09:00"),
            "dayOfWeek": int(doc.get("scheduleDayOfWeek", 1) or 0),
            "nextRunAt": next_run_at,
            "deadlineState": deadline_state,
        },
        "budget": {
            "maxCreditsPerRun": max_per_run,
            "maxBudgetCredits": max_budget,
            "latestCreditsSpent": latest_credits_spent,
            "remainingCredits": round(budget_remaining, 4),
            "exhausted": budget_exhausted,
        },
        "retry": {
            "runAttempts": run_attempts,
            "retryCount": retry_count,
            "maxSteps": max_steps,
        },
        "approval": {
            "pendingApprovalCount": pending_approval_count,
            "pendingApprovalIds": [ref["approvalId"] for ref in pending_approval_refs],
            "pendingApprovals": pending_approval_refs,
            "reviewBlocked": review_blocked,
        },
        "browserPolicy": {
            "enabled": browser_enabled,
            "defaultUse": browser_default_use,
            "restrictedByDomain": browser_restricted,
            "allowedDomains": allowed_domains,
            "requiresSandbox": browser_enabled,
            "leastPrivilege": True,
            "state": browser_policy_state,
        },
        "sla": {
            "state": sla_state,
            "deadlineState": deadline_state,
            "dueAt": next_run_at,
            "minutesUntilDue": minutes_until_due,
            "overdueMinutes": overdue_minutes,
            "needsAttention": bool(review_blocked or budget_exhausted or deadline_state == "overdue"),
            "needsHumanReview": review_blocked,
        },
        "automationGate": {
            "state": gate_state,
            "canRunUnattended": gate_state == "scheduled",
            "blockers": blockers,
            "nextActions": next_actions,
            "policy": {
                "requiresSchedule": trigger_type == "scheduled",
                "requiresApprovalClearance": True,
                "requiresBudget": max_budget > 0,
                "requiresBrowserAllowlist": bool(trigger_type == "scheduled" and browser_enabled),
                "maxSteps": max_steps,
            },
        },
        "auditTrail": audit_trail,
    }


def work_orchestration_contract(work_item: dict[str, Any]) -> dict[str, Any]:
    operational = work_item.get("operational") if isinstance(work_item.get("operational"), dict) else {}
    orchestration = operational.get("orchestration") if isinstance(operational.get("orchestration"), dict) else {}
    budget = orchestration.get("budget") if isinstance(orchestration.get("budget"), dict) else {}
    retry = orchestration.get("retry") if isinstance(orchestration.get("retry"), dict) else {}
    schedule = orchestration.get("schedule") if isinstance(orchestration.get("schedule"), dict) else {}
    sla = orchestration.get("sla") if isinstance(orchestration.get("sla"), dict) else {}
    approval = orchestration.get("approval") if isinstance(orchestration.get("approval"), dict) else {}
    audit = orchestration.get("auditTrail") if isinstance(orchestration.get("auditTrail"), dict) else {}
    browser = orchestration.get("browserPolicy") if isinstance(orchestration.get("browserPolicy"), dict) else {}
    automation_gate = orchestration.get("automationGate") if isinstance(orchestration.get("automationGate"), dict) else {}
    history = work_item.get("runHistory") if isinstance(work_item.get("runHistory"), list) else []
    allowed_domains = _list_values(browser.get("allowedDomains")) or _list_values(work_item.get("allowedDomains"))
    trigger_type = str(work_item.get("triggerType") or orchestration.get("triggerType") or "").lower()
    run_attempts = _safe_int(retry.get("runAttempts") or len(history) or 0)
    approval_gate = bool(
        approval
        or operational.get("reviewBlocked")
        or operational.get("pendingApprovalCount")
        or str(work_item.get("status") or "").upper() == "REVIEW"
    )
    return {
        "withContract": bool(orchestration),
        "scheduled": trigger_type == "scheduled" or bool(schedule),
        "budgeted": bool(budget) or _safe_float(work_item.get("maxBudgetCredits", work_item.get("maxCreditsPerRun"))) > 0,
        "budgetExhausted": bool(budget.get("exhausted")),
        "retryConfigured": bool(retry) or _safe_int(work_item.get("maxSteps")) > 0,
        "runAttempts": run_attempts,
        "slaTracked": bool(sla) or bool(schedule.get("dueAt") or work_item.get("nextRunAt")),
        "slaNeedsAttention": bool(sla.get("needsAttention") or str(sla.get("state") or "").lower() in {"blocked", "overdue"}),
        "approvalGate": approval_gate,
        "pendingApprovalIds": _list_values(approval.get("pendingApprovalIds")),
        "auditTrail": bool(audit.get("uniform") or audit.get("eventCount") or audit.get("events")),
        "browserPolicy": bool(browser) or bool(work_item.get("browserEnabled")),
        "browserAllowlist": bool(allowed_domains),
        "unattendedReady": bool(automation_gate.get("canRunUnattended")),
        "automationBlockers": _list_values(automation_gate.get("blockers")),
        "automationNextActions": _list_values(automation_gate.get("nextActions")),
        "sample": {
            "workItemId": str(work_item.get("workItemId") or ""),
            "title": str(work_item.get("title") or ""),
            "contract": bool(orchestration),
            "slaState": str(sla.get("state") or ""),
            "approvalGate": approval_gate,
            "pendingApprovalIds": _list_values(approval.get("pendingApprovalIds"))[:5],
            "runAttempts": run_attempts,
            "automationBlockers": _list_values(automation_gate.get("blockers"))[:5],
        },
    }


def summarize_work_orchestration_contracts(work_items: list[dict[str, Any]], *, sample_limit: int = 8) -> dict[str, Any]:
    contracts = [work_orchestration_contract(item) for item in work_items]
    blocker_counts: dict[str, int] = {}
    next_actions: list[str] = []
    for contract in contracts:
        for blocker in contract["automationBlockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        for action in contract["automationNextActions"]:
            if action not in next_actions:
                next_actions.append(action)
    return {
        "total": len(work_items),
        "withContract": sum(1 for item in contracts if item["withContract"]),
        "scheduled": sum(1 for item in contracts if item["scheduled"]),
        "budgeted": sum(1 for item in contracts if item["budgeted"]),
        "budgetExhausted": sum(1 for item in contracts if item["budgetExhausted"]),
        "retryConfigured": sum(1 for item in contracts if item["retryConfigured"]),
        "runAttempts": sum(item["runAttempts"] for item in contracts),
        "slaTracked": sum(1 for item in contracts if item["slaTracked"]),
        "slaNeedsAttention": sum(1 for item in contracts if item["slaNeedsAttention"]),
        "approvalGates": sum(1 for item in contracts if item["approvalGate"]),
        "pendingApprovalRefs": sum(len(item["pendingApprovalIds"]) for item in contracts),
        "auditTrails": sum(1 for item in contracts if item["auditTrail"]),
        "browserPolicies": sum(1 for item in contracts if item["browserPolicy"]),
        "browserAllowlists": sum(1 for item in contracts if item["browserAllowlist"]),
        "unattendedReady": sum(1 for item in contracts if item["unattendedReady"]),
        "unattendedBlocked": sum(1 for item in contracts if item["automationBlockers"]),
        "automationBlockers": [{"name": key, "count": blocker_counts[key]} for key in sorted(blocker_counts, key=lambda item: (-blocker_counts[item], item))],
        "automationNextActions": next_actions[:8],
        "sample": [item["sample"] for item in contracts[:sample_limit]],
    }
