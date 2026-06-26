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
    partial_demo = summary["demos"][0]
    missing_by_key = {item["key"]: item for item in partial_demo["coverage"]}
    assert missing_by_key["trajectory"]["missingEvidence"] == ["approved/source trajectory"]
    assert missing_by_key["skill_promotion"]["missingEvidence"] == ["promoted skill package"]
    assert missing_by_key["runtime_replay"]["missingEvidence"] == ["passing replay/eval run"]
