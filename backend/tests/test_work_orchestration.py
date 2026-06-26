from datetime import datetime, timezone

from app.services.work_orchestration import build_work_orchestration_contract
from app.services.work_orchestration import summarize_work_orchestration_contracts


def test_build_work_orchestration_contract_blocks_review_and_budget_with_audit_trail():
    contract = build_work_orchestration_contract(
        {
            "workItemId": "work-1",
            "status": "REVIEW",
            "triggerType": "manual",
            "maxCreditsPerRun": 1.0,
            "maxBudgetCredits": 1.0,
            "maxSteps": 4,
            "runHistory": [{"runId": "run-1"}, {"runId": "run-2"}],
            "createdAt": "t-0",
            "updatedAt": "t-1",
        },
        pending_approval_count=1,
        approval_refs=[{"approvalId": "approval-1", "title": "Approve send", "actionUrl": "/approvals?workItemId=work-1", "sourceKind": "work"}],
        latest_credits_spent=1.25,
        review_blocked=True,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert contract["queueState"] == "REVIEW"
    assert contract["budget"]["exhausted"] is True
    assert contract["budget"]["remainingCredits"] == 0.0
    assert contract["retry"] == {"runAttempts": 2, "retryCount": 1, "maxSteps": 4}
    assert contract["approval"] == {
        "pendingApprovalCount": 1,
        "pendingApprovalIds": ["approval-1"],
        "pendingApprovals": [{"approvalId": "approval-1", "title": "Approve send", "actionUrl": "/approvals?workItemId=work-1", "sourceKind": "work"}],
        "reviewBlocked": True,
    }
    assert contract["sla"]["state"] == "blocked"
    assert contract["automationGate"]["state"] == "blocked"
    assert contract["automationGate"]["blockers"] == ["pending_approval", "budget_exhausted"]
    assert [event["event"] for event in contract["auditTrail"]["events"]] == [
        "work.queued",
        "work.retry",
        "work.budget",
        "work.approval_block",
        "work.browser_policy",
    ]


def test_build_work_orchestration_contract_blocks_unrestricted_scheduled_browser_work():
    contract = build_work_orchestration_contract(
        {
            "workItemId": "work-2",
            "status": "TODO",
            "triggerType": "scheduled",
            "nextRunAt": "2026-01-01T10:00:00+00:00",
            "browserEnabled": True,
            "browserRestrictedByDomain": False,
            "allowedDomains": [],
            "maxBudgetCredits": 5,
            "maxSteps": 8,
        },
        pending_approval_count=0,
        approval_refs=[],
        latest_credits_spent=0,
        review_blocked=False,
        now=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
    )

    assert contract["schedule"]["deadlineState"] == "upcoming"
    assert contract["browserPolicy"]["state"] == "unrestricted"
    assert contract["automationGate"]["state"] == "blocked"
    assert contract["automationGate"]["blockers"] == ["missing_browser_allowlist"]
    assert contract["auditTrail"]["events"][-1]["event"] == "work.browser_policy"


def test_summarize_work_orchestration_contracts_counts_normalized_controls():
    items = [
        {
            "workItemId": "work-1",
            "operational": {
                "orchestration": {
                    "budget": {"exhausted": True},
                    "retry": {"runAttempts": 2},
                    "sla": {"state": "blocked", "needsAttention": True},
                    "approval": {"pendingApprovalCount": 1, "pendingApprovalIds": ["approval-1"]},
                    "auditTrail": {"uniform": True, "eventCount": 3},
                    "browserPolicy": {"allowedDomains": ["erp.example.com"]},
                    "automationGate": {"canRunUnattended": False},
                }
            },
        }
    ]

    summary = summarize_work_orchestration_contracts(items)

    assert summary["withContract"] == 1
    assert summary["budgetExhausted"] == 1
    assert summary["runAttempts"] == 2
    assert summary["slaNeedsAttention"] == 1
    assert summary["approvalGates"] == 1
    assert summary["pendingApprovalRefs"] == 1
    assert summary["auditTrails"] == 1
    assert summary["browserAllowlists"] == 1
