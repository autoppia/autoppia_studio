from app.services.benchmark_coverage import benchmark_coverage_summary, coverage_portfolio, regression_gate_from_matrix


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
                    "expectedInputs": ["claim_id", "customer_email"],
                    "expectedArtifacts": ["draft_email"],
                    "riskClass": "draft",
                    "businessIntent": "Respond to claim status request",
                    "initialState": {"mailbox": "claims"},
                    "evaluatorConfig": {"evaluator": "rules"},
                    "fixtures": ["claim-123"],
                    "seed": "seed-claim",
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
    assert coverage["taskContractCoverage"]["evaluationReady"] == 1
    assert coverage["taskContractCoverage"]["missingFields"] == []
    assert coverage["taskContractCoverage"]["reproducibility"] == {
        "withInitialState": 1,
        "withEvaluatorConfig": 1,
        "withFixtures": 1,
        "withSeed": 1,
        "readyForReplay": 1,
    }
    assert coverage["systems"] == ["email", "erp"]
    assert coverage["expectedInputs"] == ["claim_id", "customer_email"]
    assert coverage["expectedArtifacts"] == ["draft_email", "claim_summary"]
    assert coverage["fixtures"] == ["claim-123"]
    assert coverage["skillCoverage"]["published"] == 1
    assert coverage["runCoverage"]["pass"] == 1
    assert coverage["promotionGate"]["state"] == "published"


def test_coverage_portfolio_rolls_up_matrix_and_blockers():
    portfolio = coverage_portfolio(
        [
            {
                "taskContractCoverage": {"complete": 0, "total": 1, "evaluationReady": 0, "missingFields": [{"name": "successCriteria", "count": 1}]},
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
    assert portfolio["taskContracts"]["evaluationReady"] == 0
    assert portfolio["taskContracts"]["missingFields"] == [{"name": "successCriteria", "count": 1}]
    assert portfolio["promotionGate"]["state"] == "blocked"
    assert portfolio["promotionGate"]["blockers"] == ["incomplete_task_contracts", "no_ready_skills", "no_passing_regression", "failing_regressions"]
    assert portfolio["coverageMatrix"]["connectors"][0]["state"] == "failing"
    assert portfolio["coverageMatrix"]["skills"][0]["state"] == "failing"
    assert portfolio["coverageMatrix"]["summary"]["connectors"] == {
        "total": 1,
        "covered": 0,
        "coverageRatio": 0.0,
        "states": [{"name": "failing", "count": 1}],
    }
    assert portfolio["coverageMatrix"]["summary"]["entities"]["states"] == [{"name": "failing", "count": 1}]
    assert portfolio["coverageMatrix"]["summary"]["skills"]["states"] == [{"name": "failing", "count": 1}]
    assert portfolio["regressionGate"]["state"] == "failing"
    assert portfolio["regressionGate"]["ready"] is False
    assert portfolio["regressionGate"]["blockers"] == ["failing_regression", "skill_hardening"]
    assert portfolio["regressionGate"]["failingRegression"] == [
        {"kind": "connectors", "count": 1},
        {"kind": "entities", "count": 1},
        {"kind": "skills", "count": 1},
    ]
    assert portfolio["regressionGate"]["failingSamples"][0]["id"] == "email-1"
    assert "Inspect failing regression traces and fix the underlying capability before publishing." in portfolio["regressionGate"]["nextActions"]


def test_regression_gate_from_matrix_flags_missing_and_ready_capabilities():
    missing_gate = regression_gate_from_matrix(
        {
            "connectors": [{"id": "erp-1", "state": "missing_regression", "benchmarkRefs": ["benchmark:0"], "regressions": {"total": 0}}],
            "entities": [],
            "skills": [{"id": "skill-1", "state": "published", "benchmarkRefs": ["benchmark:0"], "regressions": {"total": 1, "pass": 1}}],
        }
    )

    assert missing_gate["state"] == "needs_regression"
    assert missing_gate["coverageRatio"] == 0.5
    assert missing_gate["missingRegression"] == [{"kind": "connectors", "count": 1}]
    assert missing_gate["ungatedSamples"][0]["id"] == "erp-1"

    ready_gate = regression_gate_from_matrix(
        {
            "connectors": [{"id": "erp-1", "state": "passing", "benchmarkRefs": ["benchmark:0"], "regressions": {"total": 1, "pass": 1}}],
            "entities": [{"id": "Claim", "state": "passing", "benchmarkRefs": ["benchmark:0"], "regressions": {"total": 1, "pass": 1}}],
            "skills": [{"id": "skill-1", "state": "published", "benchmarkRefs": ["benchmark:0"], "regressions": {"total": 1, "pass": 1}}],
        }
    )

    assert ready_gate["state"] == "ready"
    assert ready_gate["ready"] is True
    assert ready_gate["coverageRatio"] == 1.0
    assert ready_gate["blockers"] == []
