from app.services.task_contracts import build_task_contract, task_contract_from_record, task_contract_ready, task_evaluation_harness


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


def test_task_evaluation_harness_keeps_manual_override_when_contract_is_incomplete():
    harness = task_evaluation_harness({}, "manual")

    assert harness["preferredOrder"] == ["manual"]
    assert harness["deterministicFirst"] is False
    assert harness["statefulReplay"] is False
    assert harness["llmAsComplement"] is False
    assert harness["layers"][-1]["key"] == "manual"
