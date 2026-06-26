from app.services.vertical_demos import summarize_vertical_demos, vertical_demo_payload


def _benchmark():
    return {
        "benchmarkId": "bench-insurance",
        "metadata": {
            "vertical": "insurance",
            "verticalDemo": {
                "objective": "Reply to a customer about claim status without sending the final email.",
                "runtimePath": "hybrid_runtime",
                "coverage": [
                    {"key": "email_read", "label": "Email read"},
                    {"key": "erp_lookup", "label": "ERP lookup"},
                    {"key": "document_grounding", "label": "Document grounding"},
                    {"key": "draft_artifact", "label": "Draft artifact"},
                    {"key": "approval_boundary", "label": "Approval boundary"},
                    {"key": "benchmark", "label": "Benchmark"},
                    {"key": "trajectory", "label": "Trajectory"},
                    {"key": "skill_promotion", "label": "Skill promotion"},
                    {"key": "runtime_replay", "label": "Runtime replay"},
                ],
            },
        },
    }


def _task():
    return {
        "taskId": "task-claim-status",
        "benchmarkId": "bench-insurance",
        "metadata": {
            "expectedTools": ["imap.search_emails", "erp.claims.get", "knowledge.claims.search"],
            "initialState": {"approvalBoundary": "draft_only_before_send"},
        },
        "allowedSystems": ["email", "insurance_erp", "knowledge"],
        "expectedArtifacts": ["draft_email"],
        "riskClass": "send",
    }


def _skill():
    return {
        "capabilityId": "skill-claim-status",
        "benchmarkId": "bench-insurance",
        "promotionStatus": "published",
        "trajectoryIds": ["traj-claim-status"],
    }


def test_vertical_demo_payload_marks_complete_insurance_flow_ready():
    payload = vertical_demo_payload(
        benchmark=_benchmark(),
        tasks=[_task()],
        skills=[_skill()],
        runs=[{"benchmarkId": "bench-insurance", "label": "pass"}],
    )

    assert payload is not None
    assert payload["state"] == "ready"
    assert payload["readyCount"] == payload["total"] == 9
    assert payload["missing"] == []
    assert payload["operationalReadiness"]["enterpriseReady"] is True
    assert payload["operationalReadiness"]["state"] == "ready"
    assert payload["insuranceFlowProofGate"]["state"] == "ready"
    assert payload["insuranceFlowProofGate"]["ready"] is True
    assert payload["insuranceFlowProofGate"]["readySteps"] == 9
    assert payload["insuranceFlowProofGate"]["totalSteps"] == 9
    assert payload["insuranceFlowProofGate"]["missing"] == []
    assert [step["key"] for step in payload["insuranceFlowProofGate"]["steps"]] == [
        "email_read",
        "erp_lookup",
        "document_grounding",
        "draft_artifact",
        "approval_boundary",
        "benchmark",
        "trajectory",
        "skill_promotion",
        "runtime_replay",
    ]
    assert payload["smokeGate"] == {
        "state": "ready",
        "ready": True,
        "checks": {
            "objectiveDeclared": True,
            "integrationReady": True,
            "factoryReady": True,
            "runtimeReady": True,
            "draftArtifact": True,
            "noFinalSendGuard": True,
            "passingReplay": True,
        },
        "missing": [],
        "hardeningPlaybook": [],
    }
    readiness_by_key = {item["key"]: item for item in payload["operationalReadiness"]["groups"]}
    assert readiness_by_key["integration"]["state"] == "ready"
    assert readiness_by_key["factory"]["state"] == "ready"
    assert readiness_by_key["runtime"]["state"] == "ready"
    assert payload["evidence"]["skillIds"] == ["skill-claim-status"]
    assert payload["evidence"]["trajectoryIds"] == ["traj-claim-status"]
    assert payload["evidence"]["passingRuns"] == 1
    coverage_by_key = {item["key"]: item for item in payload["coverage"]}
    assert coverage_by_key["email_read"]["evidenceFound"]["tools"] == ["imap.search_emails"]
    assert coverage_by_key["erp_lookup"]["evidenceFound"]["systems"] == ["insurance_erp"]
    assert coverage_by_key["draft_artifact"]["evidenceFound"]["artifacts"] == ["draft_email"]
    assert coverage_by_key["runtime_replay"]["evidenceFound"]["passingRuns"] == 1


def test_summarize_vertical_demos_counts_partial_and_missing_states():
    partial_benchmark = _benchmark()
    partial_benchmark["benchmarkId"] = "bench-partial"
    missing_benchmark = _benchmark()
    missing_benchmark["benchmarkId"] = "bench-missing"

    summary = summarize_vertical_demos(
        benchmarks=[partial_benchmark, missing_benchmark],
        tasks=[{**_task(), "benchmarkId": "bench-partial"}],
        skills=[],
        runs=[],
    )

    assert summary["total"] == 2
    assert summary["ready"] == 0
    assert summary["partial"] == 1
    assert summary["missing"] == 1
    assert summary["smokeReady"] == 0
    assert summary["smokeBlocked"] == 2
    assert summary["proofReady"] == 0
    assert summary["proofBlocked"] == 2
    assert summary["enterpriseReady"] == 0
    assert summary["integrationReady"] == 1
    assert summary["factoryReady"] == 0
    assert summary["runtimeReady"] == 0
    assert summary["hardeningPlaybook"][:2] == [
        {
            "gap": "runtime_replay",
            "count": 2,
            "group": "runtime",
            "area": "runtime",
            "severity": "high",
            "action": "Capture a passing runtime replay or eval run for the vertical flow.",
            "example": {
                "benchmarkId": "bench-partial",
                "objective": "Reply to a customer about claim status without sending the final email.",
            },
        },
        {
            "gap": "skill_promotion",
            "count": 2,
            "group": "factory",
            "area": "skills",
            "severity": "high",
            "action": "Promote the approved trajectory into a reusable skill package.",
            "example": {
                "benchmarkId": "bench-partial",
                "objective": "Reply to a customer about claim status without sending the final email.",
            },
        },
    ]
    assert summary["smokeHardeningPlaybook"][:2] == [
        {
            "gap": "factoryReady",
            "count": 2,
            "area": "vertical_demo",
            "severity": "high",
            "action": "Complete the insurance smoke gate before using the vertical demo as enterprise proof.",
            "example": {
                "benchmarkId": "bench-partial",
                "objective": "Reply to a customer about claim status without sending the final email.",
            },
        },
        {
            "gap": "passingReplay",
            "count": 2,
            "area": "vertical_demo",
            "severity": "high",
            "action": "Complete the insurance smoke gate before using the vertical demo as enterprise proof.",
            "example": {
                "benchmarkId": "bench-partial",
                "objective": "Reply to a customer about claim status without sending the final email.",
            },
        },
    ]
    partial_demo = summary["demos"][0]
    assert partial_demo["operationalReadiness"]["enterpriseReady"] is False
    assert partial_demo["insuranceFlowProofGate"]["state"] == "needs_hardening"
    assert partial_demo["insuranceFlowProofGate"]["missing"] == ["trajectory", "skill_promotion", "runtime_replay", "smoke_gate"]
    assert partial_demo["insuranceFlowProofGate"]["readySteps"] == 6
    assert partial_demo["smokeGate"]["state"] == "needs_hardening"
    assert partial_demo["smokeGate"]["missing"] == ["factoryReady", "runtimeReady", "passingReplay"]
    readiness_by_key = {item["key"]: item for item in partial_demo["operationalReadiness"]["groups"]}
    assert readiness_by_key["integration"]["state"] == "ready"
    assert readiness_by_key["factory"]["state"] == "partial"
    assert readiness_by_key["runtime"]["state"] == "partial"
    assert partial_demo["operationalReadiness"]["missingGroups"] == ["factory", "runtime"]
    missing_by_key = {item["key"]: item for item in partial_demo["coverage"]}
    assert missing_by_key["trajectory"]["missingEvidence"] == ["approved/source trajectory"]
    assert missing_by_key["skill_promotion"]["missingEvidence"] == ["promoted skill package"]
    assert missing_by_key["runtime_replay"]["missingEvidence"] == ["passing replay/eval run"]
