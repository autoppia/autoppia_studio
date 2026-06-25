from __future__ import annotations

from typing import Any


def skill_io_contract(skill: dict[str, Any]) -> dict[str, Any]:
    input_entities = skill.get("inputEntities", [])
    preconditions = skill.get("preconditions", [])
    output_entity = skill.get("outputEntity", "")
    expected_artifacts = skill.get("expectedArtifacts", [])
    output_card = skill.get("outputCard", {})
    return {
        "inputs": {
            "entities": input_entities,
            "preconditions": preconditions,
        },
        "outputs": {
            "entity": output_entity,
            "artifacts": expected_artifacts,
            "outputCard": output_card,
        },
        "declared": bool(input_entities or preconditions or output_entity or expected_artifacts or output_card),
    }


def skill_production_gate(
    *,
    hardening: dict[str, Any],
    latest_regression: dict[str, Any] | None,
    io_contract: dict[str, Any],
) -> dict[str, Any]:
    checks = hardening.get("checks") if isinstance(hardening.get("checks"), dict) else {}
    required = {
        "activation": bool(checks.get("activation")),
        "instructions": bool(checks.get("instructions")),
        "riskPolicy": bool(checks.get("riskPolicy")),
        "sourceTrajectory": bool(checks.get("lineage")),
        "ioContract": bool(io_contract.get("declared")),
        "publishableRegression": bool(checks.get("publishableRegression")),
    }
    blockers = [key for key, ready in required.items() if not ready]
    next_actions: list[str] = []
    if not required["activation"]:
        next_actions.append("Declare when the skill should activate.")
    if not required["instructions"]:
        next_actions.append("Add reusable execution instructions.")
    if not required["riskPolicy"]:
        next_actions.append("Define the runtime risk and approval policy.")
    if not required["sourceTrajectory"]:
        next_actions.append("Attach at least one approved source trajectory.")
    if not required["ioContract"]:
        next_actions.append("Declare inputs, preconditions, output entity, expected artifacts, or output card.")
    if latest_regression is None:
        next_actions.append("Run a linked benchmark regression.")
    elif latest_regression.get("label") != "pass":
        next_actions.append("Fix the latest linked benchmark regression before publishing.")
    elif not required["publishableRegression"]:
        next_actions.append("Link a passing benchmark regression to the skill.")

    if blockers:
        if blockers == ["publishableRegression"] and latest_regression is None:
            state = "needs_regression"
        else:
            state = "blocked"
    else:
        state = "publishable"

    return {
        "state": state,
        "canPublish": state == "publishable",
        "blockers": blockers,
        "nextActions": next_actions,
        "checks": required,
        "latestRegression": latest_regression,
    }


def skill_package_manifest(
    skill: dict[str, Any],
    *,
    version: int,
    promotion_status: str,
    runtime_policy: dict[str, Any],
    lineage: dict[str, Any],
    hardening: dict[str, Any],
    latest_regression: dict[str, Any] | None,
    source_trajectories: list[dict[str, Any]],
    regression_cases: list[dict[str, Any]],
    version_history: list[dict[str, Any]],
) -> dict[str, Any]:
    package_id = str(skill.get("capabilityId") or skill.get("skillId") or "")
    input_entities = skill.get("inputEntities", [])
    preconditions = skill.get("preconditions", [])
    output_entity = skill.get("outputEntity", "")
    expected_artifacts = skill.get("expectedArtifacts", [])
    output_card = skill.get("outputCard", {})
    io_contract = skill_io_contract(skill)
    production_gate = skill_production_gate(hardening=hardening, latest_regression=latest_regression, io_contract=io_contract)
    return {
        "format": "autoppia.agent_skill",
        "manifestVersion": 1,
        "packageId": package_id,
        "metadata": {
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "version": version,
            "versionLabel": skill.get("versionLabel") or f"v{version}",
            "promotionStatus": promotion_status,
            "source": skill.get("source", ""),
            "createdAt": skill.get("createdAt"),
            "updatedAt": skill.get("updatedAt"),
        },
        "activation": {
            "description": skill.get("whenToUse", ""),
            "preconditions": preconditions,
        },
        "interface": {
            "inputEntities": input_entities,
            "outputEntity": output_entity,
            "expectedArtifacts": expected_artifacts,
            "outputCard": output_card,
            "ioContract": io_contract,
        },
        "ioContract": io_contract,
        "execution": {
            "instructions": skill.get("instructions", ""),
            "connectorIds": lineage.get("connectorIds", []),
            "toolIds": lineage.get("toolIds", []),
            "trajectoryIds": lineage.get("trajectoryIds", []),
            "runtimeRequirements": skill.get("runtimeRequirements", []),
            "runtime": skill.get("runtime", ""),
        },
        "policies": {
            "riskPolicy": skill.get("riskPolicy", ""),
            "permissions": skill.get("permissions", {}),
            "runtimePolicy": runtime_policy,
        },
        "productionGate": production_gate,
        "evidence": {
            "lineage": lineage,
            "sourceTrajectories": source_trajectories,
            "latestRegression": latest_regression,
            "hardeningStatus": hardening,
            "versionHistory": version_history,
            "regressionSuite": {
                "benchmarkIds": lineage.get("benchmarkIds", []),
                "evalIds": lineage.get("evalIds", []),
                "cases": regression_cases,
                "publishable": bool(latest_regression and latest_regression.get("label") == "pass"),
            },
        },
        "progressiveDisclosure": {
            "summaryFields": ["metadata", "activation", "interface", "ioContract", "policies"],
            "fullFields": ["execution", "evidence"],
        },
    }
