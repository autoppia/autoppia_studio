from __future__ import annotations

from typing import Any

from app.services.skill_lifecycle import skill_promotion_status
from app.services.skill_lifecycle import skill_version
from app.services.skill_lifecycle import skill_version_history


SKILL_PACKAGE_HARDENING_ACTIONS = {
    "activation": {
        "area": "capabilities",
        "severity": "medium",
        "action": "Add an activation description that explains when the AgentRuntime should load this skill.",
    },
    "instructions": {
        "area": "capabilities",
        "severity": "high",
        "action": "Add reusable workflow instructions before treating the skill as an operational capability.",
    },
    "riskPolicy": {
        "area": "security",
        "severity": "high",
        "action": "Declare runtime risk policy and approval boundaries for this skill.",
    },
    "sourceTrajectory": {
        "area": "evidence",
        "severity": "high",
        "action": "Attach approved source trajectories so the skill is backed by execution evidence.",
    },
    "ioContract": {
        "area": "interface",
        "severity": "high",
        "action": "Declare typed inputs and outputs for portable skill reuse.",
    },
    "expectedArtifacts": {
        "area": "artifacts",
        "severity": "medium",
        "action": "Declare expected business artifacts or output cards for this skill.",
    },
    "regressionSuite": {
        "area": "evals",
        "severity": "high",
        "action": "Link benchmark tasks or regression cases before promotion.",
    },
    "publishableRegression": {
        "area": "evals",
        "severity": "high",
        "action": "Run or link a passing regression before publishing this skill.",
    },
    "release_status": {
        "area": "release",
        "severity": "medium",
        "action": "Move publishable skills from draft to ready or published once review is complete.",
    },
    "published_not_publishable": {
        "area": "release",
        "severity": "high",
        "action": "Unpublish or remediate published skills that no longer satisfy production gates.",
    },
}


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _skill_package_hardening_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = SKILL_PACKAGE_HARDENING_ACTIONS.get(
            gap,
            {
                "area": "capabilities",
                "severity": "medium",
                "action": "Review skill package hardening before production promotion.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


def skill_package_readiness(doc: dict[str, Any]) -> dict[str, Any]:
    package = doc.get("skillPackage") if isinstance(doc.get("skillPackage"), dict) else {}
    activation = package.get("activation") if isinstance(package.get("activation"), dict) else {}
    policies = package.get("policies") if isinstance(package.get("policies"), dict) else {}
    evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    regression = evidence.get("regressionSuite") if isinstance(evidence.get("regressionSuite"), dict) else {}
    io_contract = package.get("ioContract") if isinstance(package.get("ioContract"), dict) else {}
    outputs = io_contract.get("outputs") if isinstance(io_contract.get("outputs"), dict) else {}
    production_gate = package.get("productionGate") if isinstance(package.get("productionGate"), dict) else {}
    hardening = package.get("hardening") if isinstance(package.get("hardening"), dict) else {}
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
    lifecycle_doc = {
        **doc,
        "promotionStatus": doc.get("promotionStatus") or metadata.get("promotionStatus"),
        "status": doc.get("status") or metadata.get("status"),
        "version": doc.get("version") or metadata.get("version"),
        "versionLabel": doc.get("versionLabel") or metadata.get("versionLabel"),
        "versionHistory": doc.get("versionHistory") if isinstance(doc.get("versionHistory"), list) else evidence.get("versionHistory"),
    }
    promotion_status = skill_promotion_status(lifecycle_doc)
    version = skill_version(lifecycle_doc)
    version_history = skill_version_history(lifecycle_doc, version=version, promotion_status=promotion_status)
    latest_version_event = version_history[-1] if version_history else {}
    release = {
        "promotionStatus": promotion_status,
        "version": version,
        "versionLabel": lifecycle_doc.get("versionLabel") or f"v{version}",
        "published": promotion_status == "published",
        "readyForPublish": publishable and promotion_status in {"ready", "published"},
        "historyCount": len(version_history),
        "latestEvent": latest_version_event,
        "readyAt": doc.get("readyAt") or metadata.get("readyAt"),
        "publishedAt": doc.get("publishedAt") or metadata.get("publishedAt"),
        "archivedAt": doc.get("archivedAt") or metadata.get("archivedAt"),
    }
    return {
        "skillId": str(doc.get("capabilityId") or doc.get("skillId") or ""),
        "name": str(doc.get("name") or ""),
        "version": release["version"],
        "manifestReady": manifest_ready,
        "publishable": publishable,
        "checks": checks,
        "blockers": blockers[:8],
        "versioned": bool(doc.get("version") or doc.get("versionHistory") or package.get("manifestVersion") or metadata.get("version")),
        "release": release,
        "hardening": hardening,
        "progressiveDisclosure": package.get("progressiveDisclosure") if isinstance(package.get("progressiveDisclosure"), dict) else {},
    }


def summarize_skill_packages(skill_docs: list[dict[str, Any]], *, package_limit: int = 50) -> dict[str, Any]:
    packages = [skill_package_readiness(skill) for skill in skill_docs]
    with_io_contract = sum(1 for item in packages if item["checks"]["ioContract"])
    with_expected_artifacts = sum(1 for item in packages if item["checks"]["expectedArtifacts"])
    with_regression_suite = sum(1 for item in packages if item["checks"]["regressionSuite"])
    release_statuses = [str(item["release"].get("promotionStatus") or "draft") for item in packages]
    ready_for_publish = sum(1 for item in packages if item["release"].get("readyForPublish"))
    published = sum(1 for item in packages if item["release"].get("published"))
    with_version_history = sum(1 for item in packages if int(item["release"].get("historyCount") or 0) > 1)
    gap_counts: dict[str, int] = {}
    for item in packages:
        for blocker in item["blockers"]:
            gap_counts[blocker] = gap_counts.get(blocker, 0) + 1
        promotion_status = str(item["release"].get("promotionStatus") or "draft")
        if item["publishable"] and not item["release"].get("readyForPublish"):
            gap_counts["release_status"] = gap_counts.get("release_status", 0) + 1
        if promotion_status == "published" and not item["publishable"]:
            gap_counts["published_not_publishable"] = gap_counts.get("published_not_publishable", 0) + 1
    sample = [
        {
            "skillId": item["skillId"],
            "name": item["name"],
            "version": item["version"],
            "promotionStatus": item["release"]["promotionStatus"],
            "manifestReady": item["manifestReady"],
            "ioContract": item["checks"]["ioContract"],
            "regressionSuite": item["checks"]["regressionSuite"],
            "publishable": item["publishable"],
            "readyForPublish": item["release"]["readyForPublish"],
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
        "releaseStatus": _sorted_counts(release_statuses),
        "releaseReadiness": {
            "readyForPublish": ready_for_publish,
            "published": published,
            "withVersionHistory": with_version_history,
            "draft": release_statuses.count("draft"),
            "ready": release_statuses.count("ready"),
            "archived": release_statuses.count("archived"),
        },
        "packages": packages[:package_limit],
        "ioContracts": with_io_contract,
        "expectedArtifacts": with_expected_artifacts,
        "regressionSuites": with_regression_suite,
        "hardeningPlaybook": _skill_package_hardening_playbook(gap_counts),
        "sample": sample,
    }
