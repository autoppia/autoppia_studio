from app.services.capability_graph_coverage import capability_graph_coverage
from app.services.capability_graph_coverage import session_contract_coverage
from app.services.capability_graph_coverage import skill_package_coverage
from app.services.capability_graph_coverage import work_orchestration_coverage


def test_session_contract_coverage_counts_runtime_contract_fields():
    coverage = session_contract_coverage(
        {
            "sessionId": "session-1",
            "sessionContract": {
                "selectedSkill": {"matched": True, "skillId": "skill-1"},
                "approvalState": {"pending": 2},
                "artifactState": {"count": 3},
                "costState": {"creditsSpent": "1.25"},
                "traceState": {"traceIds": ["trace-1", "trace-2"], "replayReady": True},
            },
        }
    )

    assert coverage == {
        "withContract": True,
        "selectedSkill": True,
        "pendingApprovals": 2,
        "artifactOutputs": 3,
        "traceIds": 2,
        "replayReady": True,
        "creditsSpent": 1.25,
    }


def test_skill_package_coverage_detects_publishable_skill_package():
    coverage = skill_package_coverage(
        {
            "capabilityId": "skill-1",
            "whenToUse": "Use for claim replies.",
            "instructions": "Read the claim and draft the response.",
            "riskPolicy": "human_approval_for_writes",
            "trajectoryIds": ["traj-1"],
            "benchmarkId": "bench-1",
            "evalId": "task-1",
            "expectedArtifacts": ["draft_email"],
            "inputEntities": ["Claim"],
            "outputEntity": "DraftEmail",
            "version": 2,
        },
        trajectory_docs=[{"trajectoryId": "traj-1", "benchmarkId": "bench-1", "evalId": "task-1"}],
        eval_run_docs=[
            {"runId": "run-pass", "evalId": "task-1", "benchmarkId": "bench-1", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"},
            {"runId": "run-fail", "evalId": "task-2", "benchmarkId": "bench-1", "label": "fail", "createdAt": "2026-06-26T10:00:00+00:00"},
        ],
    )

    assert coverage["manifestReady"] is True
    assert coverage["ioContract"] is True
    assert coverage["regressionSuite"] is True
    assert coverage["publishable"] is True
    assert coverage["versioned"] is True


def test_work_orchestration_coverage_tracks_enterprise_controls():
    coverage = work_orchestration_coverage(
        {
            "workItemId": "work-1",
            "triggerType": "scheduled",
            "status": "REVIEW",
            "allowedDomains": ["erp.example.com"],
            "operational": {
                "reviewBlocked": True,
                "orchestration": {
                    "schedule": {"dueAt": "2026-06-26T10:00:00+00:00"},
                    "budget": {"exhausted": True},
                    "retry": {"runAttempts": 2},
                    "approval": {"required": True},
                    "sla": {"state": "blocked"},
                    "auditTrail": {"uniform": True},
                    "browserPolicy": {"allowedDomains": ["erp.example.com"]},
                    "automationGate": {"canRunUnattended": False},
                },
            },
        }
    )

    assert coverage["withContract"] is True
    assert coverage["scheduled"] is True
    assert coverage["budgeted"] is True
    assert coverage["budgetExhausted"] is True
    assert coverage["runAttempts"] == 2
    assert coverage["slaNeedsAttention"] is True
    assert coverage["approvalGate"] is True
    assert coverage["auditTrail"] is True
    assert coverage["browserAllowlist"] is True


def test_capability_graph_coverage_aggregates_factory_runtime_and_policy_state():
    coverage = capability_graph_coverage(
        entity_docs=[{"entityId": "entity-1"}],
        resource_docs=[
            {
                "documentId": "doc-1",
                "vectorDatabaseId": "vec-1",
                "metadata": {
                    "resourceContract": {"declared": True},
                    "citability": {"citable": True},
                    "readTools": ["knowledge.claims.search"],
                },
                "status": "indexed",
            }
        ],
        vector_store_docs=[{"vectorDatabaseId": "vec-1"}],
        tool_docs=[
            {
                "toolId": "tool-1",
                "status": "ready",
                "riskLevel": "high",
                "sideEffects": "sends",
                "permissions": {"approval": "always"},
                "toolContract": {"policyBoundary": "send"},
            }
        ],
        benchmark_docs=[{"benchmarkId": "bench-1"}],
        task_docs=[
            {
                "taskId": "task-1",
                "metadata": {
                    "taskContract": {
                        "businessIntent": "Reply to claim",
                        "allowedSystems": ["imap", "erp"],
                        "expectedArtifacts": ["draft_email"],
                        "riskClass": "draft",
                    }
                },
            }
        ],
        trajectory_docs=[{"trajectoryId": "traj-1", "status": "approved", "evalId": "task-1", "benchmarkId": "bench-1"}],
        skill_docs=[
            {
                "capabilityId": "skill-1",
                "status": "published",
                "whenToUse": "Use for claim replies.",
                "instructions": "Draft the response.",
                "riskPolicy": "human_approval_for_writes",
                "trajectoryIds": ["traj-1"],
                "benchmarkId": "bench-1",
                "evalId": "task-1",
                "expectedArtifacts": ["draft_email"],
                "inputEntities": ["Claim"],
                "outputEntity": "DraftEmail",
                "version": 2,
            }
        ],
        eval_run_docs=[
            {"runId": "run-pass", "evalId": "task-1", "benchmarkId": "bench-1", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"},
            {"runId": "run-fail", "evalId": "task-2", "benchmarkId": "bench-1", "label": "fail", "createdAt": "2026-06-26T10:00:00+00:00"},
        ],
        session_docs=[
            {
                "sessionId": "session-1",
                "sessionContract": {
                    "selectedSkill": {"matched": True, "skillId": "skill-1"},
                    "approvalState": {"pending": 1},
                    "artifactState": {"count": 1},
                    "traceState": {"traceIds": ["trace-1"], "replayReady": True},
                },
            }
        ],
        approval_docs=[{"approvalId": "approval-1", "status": "pending"}],
        artifact_docs=[{"artifactId": "artifact-1"}],
        work_item_docs=[{"workItemId": "work-1", "triggerType": "scheduled", "browserEnabled": True}],
        vertical_demo_payloads=[{"state": "partial", "evidence": {"passingRuns": 1}}],
        edges=[
            {"relation": "input_entity"},
            {"relation": "read_by_tool"},
            {"relation": "evaluated_by_run"},
            {"relation": "gates_skill"},
            {"relation": "replayed_session"},
            {"relation": "produced_trajectory"},
            {"relation": "promoted_to"},
            {"relation": "used_by_skill"},
            {"relation": "requires_approval"},
            {"relation": "produced_artifact"},
            {"relation": "opened_session"},
            {"relation": "orchestrates_skill"},
            {"relation": "validates_vertical_demo"},
            {"relation": "restricted_to_domains"},
        ],
    )

    assert coverage["resources"]["linkedVectorStores"] == 1
    assert coverage["tools"]["ready"] == 1
    assert coverage["policies"]["sendProtected"] is True
    assert coverage["benchmarks"]["tasksWithContracts"] == 1
    assert coverage["skills"]["packages"]["publishable"] == 1
    assert coverage["evals"]["recentRuns"][0]["runId"] == "run-fail"
    assert coverage["evals"]["recentFailures"] == [
        {
            "runId": "run-fail",
            "evalId": "task-2",
            "benchmarkId": "bench-1",
            "label": "fail",
            "createdAt": "2026-06-26T10:00:00+00:00",
            "completedAt": "",
        }
    ]
    assert coverage["runtime"]["sessionContracts"]["selectedSkill"] == 1
    assert coverage["work"]["scheduled"] == 1
    assert coverage["promotionPath"]["hasTrajectoryToSkill"] is True
