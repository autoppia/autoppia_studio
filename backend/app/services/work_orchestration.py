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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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
        "auditTrail": bool(audit.get("uniform") or audit.get("eventCount") or audit.get("events")),
        "browserPolicy": bool(browser) or bool(work_item.get("browserEnabled")),
        "browserAllowlist": bool(allowed_domains),
        "unattendedReady": bool(automation_gate.get("canRunUnattended")),
        "sample": {
            "workItemId": str(work_item.get("workItemId") or ""),
            "title": str(work_item.get("title") or ""),
            "contract": bool(orchestration),
            "slaState": str(sla.get("state") or ""),
            "approvalGate": approval_gate,
            "runAttempts": run_attempts,
        },
    }


def summarize_work_orchestration_contracts(work_items: list[dict[str, Any]], *, sample_limit: int = 8) -> dict[str, Any]:
    contracts = [work_orchestration_contract(item) for item in work_items]
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
        "auditTrails": sum(1 for item in contracts if item["auditTrail"]),
        "browserPolicies": sum(1 for item in contracts if item["browserPolicy"]),
        "browserAllowlists": sum(1 for item in contracts if item["browserAllowlist"]),
        "unattendedReady": sum(1 for item in contracts if item["unattendedReady"]),
        "sample": [item["sample"] for item in contracts[:sample_limit]],
    }
