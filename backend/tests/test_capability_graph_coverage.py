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
            "resourceIds": ["claims-handbook"],
            "scripts": [{"path": "scripts/normalize_claim_status.py"}],
            "version": 2,
            "promotionStatus": "published",
            "skillPackage": {
                "progressiveDisclosure": {
                    "summaryFields": ["metadata", "activation", "ioContract", "policies"],
                    "fullFields": ["execution", "assets", "evidence"],
                }
            },
            "versionHistory": [
                {"version": 1, "promotionStatus": "ready", "reason": "initial", "createdAt": "t-1"},
                {"version": 2, "promotionStatus": "published", "reason": "promoted", "createdAt": "t-2"},
            ],
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
    assert coverage["assets"] is True
    assert coverage["resources"] is True
    assert coverage["scripts"] is True
    assert coverage["progressiveDisclosure"] is True
    assert coverage["publishable"] is True
    assert coverage["versioned"] is True
    assert coverage["release"]["promotionStatus"] == "published"
    assert coverage["release"]["readyForPublish"] is True
    assert coverage["release"]["historyCount"] == 2
    assert coverage["release"]["latestEvent"]["reason"] == "promoted"


def test_skill_package_coverage_rejects_incomplete_progressive_disclosure_contract():
    coverage = skill_package_coverage(
        {
            "capabilityId": "skill-1",
            "whenToUse": "Use for claim replies.",
            "instructions": "Read the claim and draft the response.",
            "riskPolicy": "human_approval_for_writes",
            "trajectoryIds": ["traj-1"],
            "inputEntities": ["Claim"],
            "outputEntity": "DraftEmail",
            "skillPackage": {
                "ioContract": {"declared": True},
                "progressiveDisclosure": {
                    "summaryFields": ["metadata", "activation", "ioContract"],
                    "fullFields": ["execution", "evidence"],
                },
            },
        },
        trajectory_docs=[{"trajectoryId": "traj-1"}],
        eval_run_docs=[],
    )

    assert coverage["progressiveDisclosure"] is False


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
                    "budget": {"maxCreditsPerRun": 1, "exhausted": True},
                    "retry": {"runAttempts": 2},
                    "approval": {"required": True},
                    "sla": {"state": "blocked"},
                    "auditTrail": {"uniform": True},
                    "browserPolicy": {"allowedDomains": ["erp.example.com"]},
                    "automationGate": {"canRunUnattended": False, "blockers": ["pending_approval"]},
                },
            },
        }
    )

    assert coverage["withContract"] is True
    assert coverage["scheduled"] is True
    assert coverage["budgeted"] is True
    assert coverage["perRunBudgeted"] is True
    assert coverage["budgetExhausted"] is True
    assert coverage["runAttempts"] == 2
    assert coverage["slaNeedsAttention"] is True
    assert coverage["approvalGate"] is True
    assert coverage["auditTrail"] is True
    assert coverage["browserAllowlist"] is True
    assert coverage["automationBlockers"] == ["pending_approval"]


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
                        "initialState": {"url": "https://claims.example.com/cases"},
                        "allowedSystems": ["imap", "erp"],
                        "expectedArtifacts": ["draft_email"],
                        "successCriteria": "Draft exists and is not sent.",
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
                "resourceIds": ["claims-handbook"],
                "scripts": [{"path": "scripts/normalize_claim_status.py"}],
                "version": 2,
                "promotionStatus": "published",
                "skillPackage": {
                    "progressiveDisclosure": {
                        "summaryFields": ["metadata", "activation", "ioContract", "policies"],
                        "fullFields": ["execution", "assets", "evidence"],
                    }
                },
                "versionHistory": [
                    {"version": 1, "promotionStatus": "ready", "reason": "initial", "createdAt": "t-1"},
                    {"version": 2, "promotionStatus": "published", "reason": "promoted", "createdAt": "t-2"},
                ],
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
        vertical_demo_payloads=[
            {
                "state": "partial",
                "evidence": {"passingRuns": 1},
                "insuranceFlowProofGate": {
                    "runtimeReplayContract": {
                        "ready": False,
                        "missing": ["approvedSkillAvailable"],
                    },
                    "businessOutputContract": {
                        "ready": False,
                        "missing": ["passingReplayAssertsOutput"],
                    },
                },
            }
        ],
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
            {"relation": "exercised_skill"},
            {"relation": "opened_session"},
            {"relation": "orchestrates_skill"},
            {"relation": "validates_vertical_demo"},
            {"relation": "requires_business_output_contract"},
            {"relation": "restricted_to_domains"},
        ],
    )

    assert coverage["resources"]["linkedVectorStores"] == 1
    assert coverage["resources"]["withResourceContract"] == 1
    assert coverage["resources"]["withReadTools"] == 1
    assert coverage["resources"]["citable"] == 1
    assert coverage["tools"]["ready"] == 1
    assert coverage["policies"]["sendProtected"] is True
    assert coverage["benchmarks"]["tasksWithContracts"] == 1
    assert coverage["skills"]["packages"]["publishable"] == 1
    assert coverage["skills"]["packages"]["assets"] == 1
    assert coverage["skills"]["packages"]["resources"] == 1
    assert coverage["skills"]["packages"]["scripts"] == 1
    assert coverage["skills"]["packages"]["progressiveDisclosure"] == 1
    assert coverage["skills"]["packages"]["releaseStatus"] == [{"name": "published", "count": 1}]
    assert coverage["skills"]["packages"]["releaseReadiness"] == {
        "readyForPublish": 1,
        "published": 1,
        "withVersionHistory": 1,
        "draft": 0,
        "ready": 0,
        "archived": 0,
    }
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
    assert coverage["verticalDemos"]["runtimeReplayReady"] == 0
    assert coverage["verticalDemos"]["businessOutputContractReady"] == 0
    assert coverage["verticalDemos"]["businessOutputContractBlocked"] == 1
    assert coverage["verticalDemos"]["linkedToBusinessOutputContract"] is True
    assert coverage["work"]["scheduled"] == 1
    assert coverage["promotionPath"]["hasTrajectoryToSkill"] is True
    assert coverage["operationalGraphGate"] == {
        "state": "ready",
        "ready": True,
        "readyCount": 5,
        "total": 5,
        "coverageRatio": 1.0,
        "checks": {
            "factoryAssetsLinked": True,
            "promotionPathLinked": True,
            "evalsLinked": True,
            "runtimeEvidenceLinked": True,
            "workLinked": True,
        },
        "blockers": [],
        "hardeningPlaybook": [],
    }
    assert coverage["coveragePlaybook"] == [
        {
            "gap": "failing_regressions",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Inspect recent failing eval runs before publishing or widening runtime access.",
        },
        {
            "gap": "pending_approvals",
            "count": 1,
            "area": "approvals",
            "severity": "high",
            "action": "Resolve pending approvals blocking write/send boundaries.",
        },
    ]


def test_capability_graph_coverage_operational_gate_exposes_hardening_playbook():
    coverage = capability_graph_coverage(
        entity_docs=[],
        resource_docs=[],
        vector_store_docs=[],
        tool_docs=[],
        benchmark_docs=[],
        task_docs=[],
        trajectory_docs=[],
        skill_docs=[],
        eval_run_docs=[],
        session_docs=[],
        approval_docs=[],
        artifact_docs=[],
        work_item_docs=[],
        vertical_demo_payloads=[],
        edges=[{"relation": "produced_trajectory"}],
    )

    assert coverage["operationalGraphGate"]["state"] == "needs_hardening"
    assert coverage["operationalGraphGate"]["readyCount"] == 0
    assert coverage["operationalGraphGate"]["hardeningPlaybook"][:3] == [
        {
            "gap": "factoryAssetsLinked",
            "count": 1,
            "area": "factory",
            "severity": "high",
            "action": "Link connectors, entities, tools and benchmark tasks inside the capability graph.",
        },
        {
            "gap": "promotionPathLinked",
            "count": 1,
            "area": "promotion",
            "severity": "high",
            "action": "Connect benchmark tasks to generated trajectories and promoted skills.",
        },
        {
            "gap": "evalsLinked",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Attach eval runs to benchmark tasks and use passing runs as skill gates.",
        },
    ]


def test_capability_graph_coverage_flags_missing_skill_progressive_disclosure():
    coverage = capability_graph_coverage(
        entity_docs=[],
        resource_docs=[],
        vector_store_docs=[],
        tool_docs=[],
        benchmark_docs=[],
        task_docs=[],
        trajectory_docs=[],
        skill_docs=[{"capabilityId": "skill-1", "whenToUse": "Use it.", "instructions": "Do it."}],
        eval_run_docs=[],
        session_docs=[],
        approval_docs=[],
        artifact_docs=[],
        work_item_docs=[],
        vertical_demo_payloads=[],
        edges=[],
    )

    assert {
        "gap": "skill_progressive_disclosure",
        "count": 1,
        "area": "capabilities",
        "severity": "medium",
        "action": "Declare summary and full-load fields so AgentRuntime can load skills on demand.",
    } in coverage["coveragePlaybook"]
