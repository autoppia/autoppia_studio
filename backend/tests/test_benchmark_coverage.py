from app.services.benchmark_coverage import benchmark_coverage_summary, coverage_portfolio


def test_benchmark_coverage_summary_builds_eval_gate_evidence():
    coverage = benchmark_coverage_summary(
        benchmark={"benchmarkId": "bench-1", "websiteUrl": "https://claims.example.com/start"},
        tasks=[
            {
                "taskId": "task-1",
                "benchmarkId": "bench-1",
                "prompt": "Answer claim status",
                "successCriteria": "Draft includes claim status.",
                "metadata": {
                    "allowedSystems": ["email", "erp"],
                    "expectedArtifacts": ["draft_email"],
                    "riskClass": "draft",
                    "businessIntent": "Respond to claim status request",
                },
            }
        ],
        skills=[
            {
                "capabilityId": "skill-1",
                "status": "published",
                "connectorIds": ["email-1", "erp-1"],
                "inputEntities": ["Claim", "Customer"],
                "outputEntity": "DraftEmail",
                "expectedArtifacts": ["claim_summary"],
            }
        ],
        runs=[{"runId": "run-1", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"}],
    )

    assert coverage["taskCount"] == 1
    assert coverage["taskContractCoverage"]["complete"] == 1
    assert coverage["systems"] == ["email", "erp"]
    assert coverage["expectedArtifacts"] == ["draft_email", "claim_summary"]
    assert coverage["skillCoverage"]["published"] == 1
    assert coverage["runCoverage"]["pass"] == 1
    assert coverage["promotionGate"]["state"] == "published"


def test_coverage_portfolio_rolls_up_matrix_and_blockers():
    portfolio = coverage_portfolio(
        [
            {
                "taskContractCoverage": {"complete": 0, "total": 1},
                "connectorIds": ["email-1"],
                "systems": ["email"],
                "entityNames": ["Claim"],
                "expectedArtifacts": ["draft_email"],
                "skillCoverage": {"skillIds": ["skill-1"], "ready": 0, "published": 0},
                "runCoverage": {"total": 1, "pass": 0, "fail": 1, "pending": 0, "latestRunId": "run-1", "latestLabel": "fail"},
            }
        ]
    )

    assert portfolio["benchmarks"] == 1
    assert portfolio["taskContracts"]["coverageRatio"] == 0.0
    assert portfolio["promotionGate"]["state"] == "blocked"
    assert portfolio["promotionGate"]["blockers"] == ["incomplete_task_contracts", "no_ready_skills", "no_passing_regression", "failing_regressions"]
    assert portfolio["coverageMatrix"]["connectors"][0]["state"] == "failing"
    assert portfolio["coverageMatrix"]["skills"][0]["state"] == "failing"
