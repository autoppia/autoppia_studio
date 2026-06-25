from app.services.task_contracts import build_task_contract, task_contract_from_record, task_contract_ready


def test_task_contract_from_record_normalizes_current_and_legacy_shapes():
    task = {
        "name": "Review claim",
        "businessIntent": "Top-level intent",
        "allowedSystems": ["claims_erp"],
        "expectedArtifacts": ["claim_summary"],
        "riskClass": "medium",
        "successCriteria": "Claim status is summarized.",
        "metadata": {
            "taskContract": {
                "businessIntent": "Nested intent",
                "allowedSystems": ["legacy_erp"],
                "expectedArtifacts": ["legacy_summary"],
                "riskClass": "low",
            }
        },
    }

    contract = task_contract_from_record(task)

    assert contract["businessIntent"] == "Top-level intent"
    assert contract["allowedSystems"] == ["legacy_erp", "claims_erp"]
    assert contract["expectedArtifacts"] == ["claim_summary"]
    assert contract["riskClass"] == "medium"
    assert contract["successCriteria"] == "Claim status is summarized."
    assert task_contract_ready(task) is True


def test_build_task_contract_adds_runtime_context_defaults():
    contract = build_task_contract(
        {"prompt": "Draft a reply", "metadata": {"allowedSystems": ["email"]}},
        website_url="https://portal.example.com/start",
        allowed_systems=["knowledge"],
    )

    assert contract["businessIntent"] == "Draft a reply"
    assert contract["initialUrl"] == "https://portal.example.com/start"
    assert contract["initialState"]["url"] == "https://portal.example.com/start"
    assert contract["allowedSystems"] == ["email", "knowledge", "https://portal.example.com/start", "portal.example.com"]
    assert contract["expectedArtifacts"] == ["trajectory_trace"]
    assert contract["riskClass"] == "low"
