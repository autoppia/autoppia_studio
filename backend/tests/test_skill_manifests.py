from app.services.skill_manifests import skill_io_contract, skill_package_assets, skill_package_manifest, skill_production_gate


def _skill():
    return {
        "capabilityId": "skill-1",
        "name": "Draft claim response",
        "description": "Draft response for claim status.",
        "versionLabel": "v2",
        "whenToUse": "Use for customer claim status emails.",
        "instructions": "Look up the claim, draft the reply and stop before sending.",
        "parameters": [{"name": "claim_id", "description": "Claim identifier"}],
        "actions": [{"action": "erp.claims.get", "args": {"claimId": "{{claim_id}}"}}],
        "preconditions": ["Customer identity verified"],
        "expectedArtifacts": ["draft_email"],
        "inputEntities": ["Claim"],
        "outputEntity": "DraftEmail",
        "riskPolicy": "human_approval_for_writes",
        "permissions": {"approval": "always"},
        "runtimeRequirements": ["browser"],
        "runtime": "hybrid_runtime",
        "resourceIds": ["claims-handbook"],
        "resources": [{"path": "resources/claims-handbook.md", "description": "Claim status reference"}],
        "scriptIds": ["normalize_claim_status"],
        "scripts": [{"path": "scripts/normalize_claim_status.py", "description": "Normalize ERP claim status"}],
        "references": [{"path": "references/escalation-policy.md"}],
        "createdAt": "2026-06-25T10:00:00+00:00",
        "updatedAt": "2026-06-25T11:00:00+00:00",
    }


def test_skill_io_contract_declares_business_inputs_and_outputs():
    contract = skill_io_contract(_skill())

    assert contract["declared"] is True
    assert contract["inputs"]["entities"] == ["Claim"]
    assert contract["inputs"]["preconditions"] == ["Customer identity verified"]
    assert contract["outputs"]["entity"] == "DraftEmail"
    assert contract["outputs"]["artifacts"] == ["draft_email"]


def test_skill_package_assets_declares_optional_resources_and_scripts():
    assets = skill_package_assets(_skill())

    assert assets["declared"] is True
    assert assets["resourceIds"] == ["claims-handbook"]
    assert assets["resources"][0]["path"] == "resources/claims-handbook.md"
    assert assets["scriptIds"] == ["normalize_claim_status"]
    assert assets["scripts"][0]["path"] == "scripts/normalize_claim_status.py"
    assert assets["references"] == [{"path": "references/escalation-policy.md"}]


def test_skill_package_manifest_exposes_publishable_agent_skill_contract():
    hardening = {
        "checks": {
            "activation": True,
            "instructions": True,
            "riskPolicy": True,
            "lineage": True,
            "publishableRegression": True,
        }
    }
    package = skill_package_manifest(
        _skill(),
        version=2,
        promotion_status="published",
        runtime_policy={"runtimeClass": "hybrid", "approvalMode": "always"},
        lineage={"trajectoryIds": ["traj-1"], "benchmarkIds": ["bench-1"], "evalIds": ["task-1"], "connectorIds": ["erp"], "toolIds": ["erp.claims.get"]},
        hardening=hardening,
        latest_regression={"runId": "run-1", "label": "pass"},
        source_trajectories=[{"trajectoryId": "traj-1", "actionCount": 3}],
        regression_cases=[{"taskId": "task-1", "expectedArtifacts": ["draft_email"]}],
        version_history=[{"version": 2, "versionLabel": "v2", "promotionStatus": "published"}],
    )

    assert package["format"] == "autoppia.agent_skill"
    assert package["metadata"]["promotionStatus"] == "published"
    assert package["ioContract"]["declared"] is True
    assert package["ioContract"]["inputs"]["parameters"][0]["name"] == "claim_id"
    assert package["execution"]["actions"][0]["action"] == "erp.claims.get"
    assert package["hardening"]["readyForPublish"] is True
    assert package["hardening"]["blockers"] == []
    assert package["hardening"]["checks"]["sourceTrajectory"] is True
    assert package["productionGate"]["state"] == "publishable"
    assert package["productionGate"]["canPublish"] is True
    assert package["assets"]["declared"] is True
    assert package["assets"]["resources"][0]["path"] == "resources/claims-handbook.md"
    assert package["assets"]["scripts"][0]["path"] == "scripts/normalize_claim_status.py"
    assert package["evidence"]["regressionSuite"]["publishable"] is True
    assert package["progressiveDisclosure"]["summaryFields"] == ["metadata", "activation", "interface", "ioContract", "policies"]
    assert "assets" in package["progressiveDisclosure"]["fullFields"]


def test_skill_production_gate_blocks_missing_io_and_regression():
    gate = skill_production_gate(
        hardening={"checks": {"activation": True, "instructions": True, "riskPolicy": True, "lineage": True}},
        latest_regression=None,
        io_contract={"declared": False},
    )

    assert gate["state"] == "blocked"
    assert gate["canPublish"] is False
    assert gate["blockers"] == ["ioContract", "publishableRegression"]
    assert "Declare inputs, preconditions, output entity, expected artifacts, or output card." in gate["nextActions"]
    assert "Run a linked benchmark regression." in gate["nextActions"]
