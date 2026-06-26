from app.services.benchmark_coverage import (
    benchmark_coverage_summary,
    coverage_portfolio,
    judge_strategy_gate,
    regression_gate_from_matrix,
    task_contract_completeness,
)


def test_task_contract_completeness_reuses_central_hardening_with_legacy_field_names():
    completeness = task_contract_completeness(
        {
            "businessIntent": "Answer claim status",
            "allowedSystems": ["claims_erp"],
            "successCriteria": "Draft exists.",
            "riskClass": "draft",
        }
    )

    assert completeness["checks"]["expectedArtifact"] is False
    assert "expectedArtifacts" not in completeness["checks"]
    assert completeness["missingFields"] == ["initialState", "expectedArtifact"]
    assert completeness["state"] == "incomplete"


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
    assert coverage["taskContractCoverage"]["productionReady"] == 1
    assert coverage["taskContractCoverage"]["missingFields"] == []
    assert coverage["taskContractCoverage"]["reproducibility"] == {
        "withInitialState": 1,
        "withEvaluatorConfig": 1,
        "withFixtures": 1,
        "withSeed": 1,
        "readyForReplay": 1,
    }
    assert coverage["judgeStrategyGate"] == {
        "state": "ready",
        "ready": True,
        "total": 1,
        "deterministic": 1,
        "stateful": 1,
        "llm": 0,
        "llmOnly": 0,
        "checks": {
            "tasksHaveJudgeStrategy": True,
            "deterministicFirst": True,
            "statefulReplayAvailable": True,
            "llmAsComplementOnly": True,
        },
        "blockers": [],
        "hardeningPlaybook": [],
    }
    assert coverage["systems"] == ["email", "erp"]
    assert coverage["expectedInputs"] == ["claim_id", "customer_email"]
    assert coverage["expectedArtifacts"] == ["draft_email", "claim_summary"]
    assert coverage["fixtures"] == ["claim-123"]
    assert coverage["skillCoverage"]["published"] == 1
    assert coverage["runCoverage"]["pass"] == 1
    assert coverage["promotionGate"]["state"] == "published"


def test_judge_strategy_gate_blocks_llm_only_evaluators():
    gate = judge_strategy_gate(
        [
            {
                "businessIntent": "Classify customer message",
                "evaluatorConfig": {"evaluator": "llm"},
            }
        ]
    )

    assert gate["state"] == "needs_hardening"
    assert gate["blockers"] == ["judge_strategy", "deterministic_judge", "llm_only_judge"]
    assert gate["hardeningPlaybook"] == [
        {
            "gap": "deterministic_judge",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Add success criteria or rules-based assertions so deterministic checks run before replay or LLM judging.",
        },
        {
            "gap": "judge_strategy",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Declare deterministic or stateful judge layers before relying on benchmark promotion gates.",
        },
        {
            "gap": "llm_only_judge",
            "count": 1,
            "area": "evals",
            "severity": "medium",
            "action": "Add deterministic checks or stateful replay so LLM judges remain complementary.",
        },
    ]


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
                "judgeStrategyGate": {
                    "total": 1,
                    "deterministic": 0,
                    "stateful": 0,
                    "llm": 1,
                    "llmOnly": 1,
                    "hardeningPlaybook": [{"gap": "llm_only_judge", "count": 1}],
                },
            }
        ]
    )

    assert portfolio["benchmarks"] == 1
    assert portfolio["taskContracts"]["coverageRatio"] == 0.0
    assert portfolio["taskContracts"]["evaluationReady"] == 0
    assert portfolio["taskContracts"]["productionReady"] == 0
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
    assert portfolio["evalCenterGate"]["state"] == "blocked"
    assert portfolio["evalCenterGate"]["checks"] == {
        "benchmarksPresent": True,
        "taskContractsComplete": False,
        "tasksEvaluationReady": False,
        "tasksProductionReady": False,
        "tasksReplayReady": False,
        "judgeStrategyReady": False,
        "regressionMatrixReady": False,
        "promotionGateReady": False,
    }
    assert portfolio["evalCenterGate"]["taskCoverage"] == {
        "total": 1,
        "complete": 0,
        "evaluationReady": 0,
        "productionReady": 0,
        "replayReady": 0,
    }
    assert portfolio["evalCenterGate"]["capabilityRegression"] == {"gated": 0, "total": 3, "state": "failing"}
    assert portfolio["evalCenterGate"]["hardeningPlaybook"][0] == {
        "gap": "benchmark_promotion_gate",
        "count": 4,
        "area": "evals",
        "severity": "high",
        "action": "Resolve benchmark promotion blockers before publishing capabilities.",
    }
    assert portfolio["judgeStrategyGate"]["state"] == "needs_hardening"
    assert portfolio["judgeStrategyGate"]["llmOnly"] == 1
    assert portfolio["regressionGate"]["failingRegression"] == [
        {"kind": "connectors", "count": 1},
        {"kind": "entities", "count": 1},
        {"kind": "skills", "count": 1},
    ]
    assert portfolio["hardeningPlaybook"][0] == {
        "gap": "failing_regression",
        "count": 3,
        "area": "evals",
        "severity": "high",
        "action": "Inspect failing regression traces before publishing or widening runtime access.",
    }
    assert {
        "gap": "llm_only_judge",
        "count": 1,
        "area": "evals",
        "severity": "medium",
        "action": "Add deterministic checks or stateful replay so LLM judges remain complementary.",
    } in portfolio["hardeningPlaybook"]
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
