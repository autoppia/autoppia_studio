from app.services.task_contracts import (
    build_task_contract,
    task_contract_from_record,
    task_contract_hardening,
    task_contract_hardening_summary,
    task_contract_ready,
    task_evaluation_harness,
    task_reproducibility_summary,
)


def test_task_contract_from_record_normalizes_current_and_legacy_shapes():
    task = {
        "name": "Review claim",
        "businessIntent": "Top-level intent",
        "allowedSystems": ["claims_erp"],
        "expectedInputs": ["claim_id"],
        "expectedArtifacts": ["claim_summary"],
        "riskClass": "medium",
        "successCriteria": "Claim status is summarized.",
        "evaluatorConfig": {"evaluator": "rules", "assertions": ["draft_exists"]},
        "fixtures": ["claim-123", "claim-123"],
        "seed": "seed-1",
        "metadata": {
            "taskContract": {
                "businessIntent": "Nested intent",
                "allowedSystems": ["legacy_erp"],
                "expectedInputs": ["legacy_claim_id"],
                "expectedArtifacts": ["legacy_summary"],
                "riskClass": "low",
            }
        },
    }

    contract = task_contract_from_record(task)

    assert contract["businessIntent"] == "Top-level intent"
    assert contract["allowedSystems"] == ["legacy_erp", "claims_erp"]
    assert contract["expectedInputs"] == ["claim_id"]
    assert contract["expectedArtifacts"] == ["claim_summary"]
    assert contract["riskClass"] == "medium"
    assert contract["successCriteria"] == "Claim status is summarized."
    assert contract["evaluatorConfig"] == {"evaluator": "rules", "assertions": ["draft_exists"]}
    assert contract["fixtures"] == ["claim-123"]
    assert contract["seed"] == "seed-1"
    assert task_contract_ready(task) is True


def test_build_task_contract_adds_runtime_context_defaults():
    contract = build_task_contract(
        {"prompt": "Draft a reply", "metadata": {"allowedSystems": ["email"], "inputRequirements": ["customer_email"]}},
        website_url="https://portal.example.com/start",
        allowed_systems=["knowledge"],
    )

    assert contract["businessIntent"] == "Draft a reply"
    assert contract["initialUrl"] == "https://portal.example.com/start"
    assert contract["initialState"]["url"] == "https://portal.example.com/start"
    assert contract["allowedSystems"] == ["email", "knowledge", "https://portal.example.com/start", "portal.example.com"]
    assert contract["expectedInputs"] == ["customer_email"]
    assert contract["expectedArtifacts"] == ["trajectory_trace"]
    assert contract["riskClass"] == "low"


def test_task_evaluation_harness_layers_deterministic_stateful_llm_and_manual_review():
    harness = task_evaluation_harness(
        {
            "successCriteria": "Draft exists and is not sent.",
            "initialUrl": "https://portal.example.com/start",
        },
        "llm",
    )

    assert harness["strategy"] == "layered"
    assert harness["preferredOrder"] == ["deterministic", "stateful", "llm", "manual"]
    assert harness["deterministicFirst"] is True
    assert harness["statefulReplay"] is True
    assert harness["llmAsComplement"] is True
    assert harness["humanOverride"] is True


def test_task_reproducibility_summary_counts_replay_ready_contracts():
    summary = task_reproducibility_summary(
        [
            {"initialState": {"mailbox": "claims"}, "evaluatorConfig": {"evaluator": "rules"}, "fixtures": ["claim-1"], "seed": "seed-1"},
            {"businessIntent": "Incomplete"},
        ]
    )

    assert summary == {
        "total": 2,
        "withInitialState": 1,
        "withEvaluatorConfig": 1,
        "withFixtures": 1,
        "withSeed": 1,
        "readyForReplay": 1,
        "replayReadyRatio": 0.5,
    }


def test_task_evaluation_harness_keeps_manual_override_when_contract_is_incomplete():
    harness = task_evaluation_harness({}, "manual")

    assert harness["preferredOrder"] == ["manual"]
    assert harness["deterministicFirst"] is False
    assert harness["statefulReplay"] is False
    assert harness["llmAsComplement"] is False
    assert harness["layers"][-1]["key"] == "manual"


def test_task_contract_hardening_surfaces_missing_eval_gate_fields():
    hardening = task_contract_hardening(
        {
            "businessIntent": "Answer claim status",
            "allowedSystems": ["claims_erp"],
            "expectedArtifacts": ["draft_email"],
        }
    )

    assert hardening["state"] == "incomplete"
    assert hardening["missingFields"] == ["initialState", "successCriteria", "riskClass"]
    assert hardening["evaluationReady"] is False
    assert hardening["productionReady"] is False
    assert hardening["nextActions"] == [
        "Attach an initial URL or state so the task can be replayed.",
        "Add deterministic success criteria before using this task as an eval gate.",
        "Assign a risk class for runtime policy and approval routing.",
    ]


def test_task_contract_hardening_summary_builds_actionable_playbook():
    summary = task_contract_hardening_summary(
        [
            {
                "businessIntent": "Answer claim status",
                "initialUrl": "https://claims.example.com",
                "allowedSystems": ["claims_erp"],
                "expectedArtifacts": ["draft_email"],
                "successCriteria": "Draft exists and email is not sent.",
                "riskClass": "medium",
                "fixtures": ["claim-1"],
            },
            {"businessIntent": "Incomplete"},
        ]
    )

    assert summary["total"] == 2
    assert summary["complete"] == 1
    assert summary["evaluationReady"] == 1
    assert summary["productionReady"] == 1
    assert summary["averageScore"] == 0.584
    assert summary["missingFields"] == [
        {"name": "allowedSystems", "count": 1},
        {"name": "expectedArtifacts", "count": 1},
        {"name": "initialState", "count": 1},
        {"name": "riskClass", "count": 1},
        {"name": "successCriteria", "count": 1},
    ]
    assert summary["playbook"][0] == {
        "field": "allowedSystems",
        "count": 1,
        "severity": "medium",
        "action": "List the systems, connectors, or domains the agent may use.",
    }
