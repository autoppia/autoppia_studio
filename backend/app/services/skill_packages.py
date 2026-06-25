from __future__ import annotations

from typing import Any


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def skill_package_readiness(doc: dict[str, Any]) -> dict[str, Any]:
    package = doc.get("skillPackage") if isinstance(doc.get("skillPackage"), dict) else {}
    activation = package.get("activation") if isinstance(package.get("activation"), dict) else {}
    policies = package.get("policies") if isinstance(package.get("policies"), dict) else {}
    evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    regression = evidence.get("regressionSuite") if isinstance(evidence.get("regressionSuite"), dict) else {}
    io_contract = package.get("ioContract") if isinstance(package.get("ioContract"), dict) else {}
    outputs = io_contract.get("outputs") if isinstance(io_contract.get("outputs"), dict) else {}
    production_gate = package.get("productionGate") if isinstance(package.get("productionGate"), dict) else {}
    latest_regression = evidence.get("latestRegression") if isinstance(evidence.get("latestRegression"), dict) else doc.get("latestRegression") if isinstance(doc.get("latestRegression"), dict) else {}
    checks = {
        "activation": bool(str(doc.get("whenToUse") or activation.get("description") or "").strip()),
        "instructions": bool(str(doc.get("instructions") or "").strip()),
        "riskPolicy": bool(str(doc.get("riskPolicy") or policies.get("riskPolicy") or "").strip() or policies.get("runtimePolicy") or doc.get("runtimePolicy")),
        "sourceTrajectory": bool(_list_values(doc.get("trajectoryIds")) or _list_values(evidence.get("sourceTrajectoryIds")) or evidence.get("sourceTrajectories")),
        "ioContract": bool(io_contract.get("declared") or _list_values(doc.get("inputEntities")) or str(doc.get("outputEntity") or "").strip()),
        "expectedArtifacts": bool(_list_values(doc.get("expectedArtifacts")) or _list_values(outputs.get("artifacts")) or doc.get("outputCard") or outputs.get("outputCard")),
        "regressionSuite": bool(regression.get("cases") or _list_values(regression.get("benchmarkIds")) or _list_values(regression.get("evalIds")) or latest_regression),
    }
    manifest_ready = checks["activation"] and checks["instructions"] and checks["riskPolicy"] and checks["sourceTrajectory"] and checks["ioContract"]
    publishable_regression = bool(
        regression.get("publishable")
        or str(latest_regression.get("label") or "").lower() == "pass"
        or str(production_gate.get("state") or "").lower() == "publishable"
        or production_gate.get("canPublish")
    )
    publishable = manifest_ready and publishable_regression
    blockers = _list_values(production_gate.get("blockers"))
    if not blockers:
        blockers = [key for key, ready in checks.items() if not ready]
        if manifest_ready and not publishable_regression:
            blockers.append("publishableRegression")
    metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
    return {
        "skillId": str(doc.get("capabilityId") or doc.get("skillId") or ""),
        "name": str(doc.get("name") or ""),
        "version": doc.get("version") or metadata.get("version"),
        "manifestReady": manifest_ready,
        "publishable": publishable,
        "checks": checks,
        "blockers": blockers[:8],
        "versioned": bool(doc.get("version") or doc.get("versionHistory") or package.get("manifestVersion") or metadata.get("version")),
        "progressiveDisclosure": package.get("progressiveDisclosure") if isinstance(package.get("progressiveDisclosure"), dict) else {},
    }


def summarize_skill_packages(skill_docs: list[dict[str, Any]], *, package_limit: int = 50) -> dict[str, Any]:
    packages = [skill_package_readiness(skill) for skill in skill_docs]
    with_io_contract = sum(1 for item in packages if item["checks"]["ioContract"])
    with_expected_artifacts = sum(1 for item in packages if item["checks"]["expectedArtifacts"])
    with_regression_suite = sum(1 for item in packages if item["checks"]["regressionSuite"])
    sample = [
        {
            "skillId": item["skillId"],
            "name": item["name"],
            "manifestReady": item["manifestReady"],
            "ioContract": item["checks"]["ioContract"],
            "regressionSuite": item["checks"]["regressionSuite"],
            "publishable": item["publishable"],
        }
        for item in packages[:5]
    ]
    return {
        "total": len(skill_docs),
        "manifestReady": sum(1 for item in packages if item["manifestReady"]),
        "publishable": sum(1 for item in packages if item["publishable"]),
        "withIoContract": with_io_contract,
        "withExpectedArtifacts": with_expected_artifacts,
        "withRegressionSuite": with_regression_suite,
        "versioned": sum(1 for item in packages if item["versioned"]),
        "blocked": sum(1 for item in packages if item["blockers"]),
        "packages": packages[:package_limit],
        "ioContracts": with_io_contract,
        "expectedArtifacts": with_expected_artifacts,
        "regressionSuites": with_regression_suite,
        "sample": sample,
    }
