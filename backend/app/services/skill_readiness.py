from __future__ import annotations

from typing import Any


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def skill_reusability_checks(skill: dict[str, Any]) -> dict[str, bool]:
    """Checks for whether a skill has enough package metadata to operate as reusable capability."""
    package = _dict(skill.get("skillPackage"))
    package_policies = _dict(package.get("policies"))
    package_evidence = _dict(package.get("evidence"))
    package_regression = _dict(package_evidence.get("regressionSuite"))
    lineage = _dict(skill.get("lineage")) or _dict(package_evidence.get("lineage"))
    activation = bool(
        str(skill.get("whenToUse") or skill.get("activationDescription") or "").strip()
        or str(_dict(package.get("activation")).get("description") or "").strip()
        or _string_list(skill.get("sourceTrajectoryIds"))
        or _string_list(skill.get("trajectoryIds"))
        or _string_list(lineage.get("trajectoryIds"))
    )
    artifacts = bool(_string_list(skill.get("expectedArtifacts")) or _string_list(skill.get("preconditions")) or skill.get("outputCard"))
    if not artifacts:
        io_contract = _dict(skill.get("ioContract")) or _dict(package.get("ioContract"))
        outputs = _dict(io_contract.get("outputs"))
        artifacts = bool(_string_list(outputs.get("artifacts")) or str(outputs.get("entity") or "").strip() or outputs.get("outputCard"))
    policy = bool(
        str(skill.get("riskPolicy") or "").strip()
        or skill.get("runtimePolicy")
        or package_policies.get("runtimePolicy")
        or package_policies.get("riskPolicy")
    )
    evidence = bool(
        _string_list(skill.get("sourceTrajectoryIds"))
        or _string_list(skill.get("trajectoryIds"))
        or _string_list(lineage.get("trajectoryIds"))
        or skill.get("latestRegression")
        or package_evidence.get("latestRegression")
        or _string_list(package_regression.get("benchmarkIds"))
        or _string_list(package_regression.get("evalIds"))
        or package_regression.get("cases")
    )
    return {
        "activation": activation,
        "instructions": bool(str(skill.get("instructions") or "").strip()),
        "artifacts": artifacts,
        "policy": policy,
        "evidence": evidence,
    }


def skill_reusability_ready(skill: dict[str, Any]) -> bool:
    checks = skill_reusability_checks(skill)
    return all(checks.values())
