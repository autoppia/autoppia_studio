from __future__ import annotations

from typing import Any

from app.services.runtime_policy import serialize_runtime_policy


def dedupe_manual_skill_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def manual_skill_lineage(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectoryIds": dedupe_manual_skill_values(doc.get("trajectoryIds") or []),
        "benchmarkIds": [],
        "evalIds": [],
        "connectorIds": dedupe_manual_skill_values(doc.get("connectorIds") or []),
        "toolIds": dedupe_manual_skill_values(doc.get("toolIds") or []),
        "sources": dedupe_manual_skill_values([doc.get("source")]),
    }


def manual_skill_hardening(doc: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "activation": bool(str(doc.get("whenToUse") or "").strip()),
        "instructions": bool(str(doc.get("instructions") or "").strip()),
        "riskPolicy": bool(str(doc.get("riskPolicy") or "").strip()),
        "lineage": bool(lineage.get("trajectoryIds")),
        "regression": False,
        "publishableRegression": False,
        "entities": bool(doc.get("inputEntities") or str(doc.get("outputEntity") or "").strip()),
        "artifacts": bool(doc.get("expectedArtifacts") or doc.get("outputCard")),
    }
    passed = sum(1 for ready in checks.values() if ready)
    return {
        "checks": checks,
        "passedChecks": passed,
        "totalChecks": len(checks),
        "score": round(passed / len(checks), 3),
        "state": "drafting",
    }


def manual_skill_package(doc: dict[str, Any], lineage: dict[str, Any], hardening: dict[str, Any]) -> dict[str, Any]:
    io_contract = {
        "inputs": {
            "entities": doc.get("inputEntities", []),
            "preconditions": doc.get("preconditions", []),
        },
        "outputs": {
            "entity": doc.get("outputEntity", ""),
            "artifacts": doc.get("expectedArtifacts", []),
            "outputCard": doc.get("outputCard", {}),
        },
        "declared": bool(doc.get("inputEntities") or doc.get("preconditions") or doc.get("outputEntity") or doc.get("expectedArtifacts") or doc.get("outputCard")),
    }
    return {
        "format": "autoppia.agent_skill",
        "manifestVersion": 1,
        "packageId": doc.get("capabilityId", ""),
        "metadata": {
            "name": doc.get("name", ""),
            "description": doc.get("description", ""),
            "version": doc.get("version", 1),
            "versionLabel": doc.get("versionLabel", "v1"),
            "promotionStatus": doc.get("promotionStatus", "ready"),
            "source": doc.get("source", ""),
            "createdAt": doc.get("createdAt"),
            "updatedAt": doc.get("updatedAt"),
        },
        "activation": {
            "description": doc.get("whenToUse", ""),
            "preconditions": doc.get("preconditions", []),
        },
        "interface": {
            "inputEntities": doc.get("inputEntities", []),
            "outputEntity": doc.get("outputEntity", ""),
            "expectedArtifacts": doc.get("expectedArtifacts", []),
            "outputCard": doc.get("outputCard", {}),
            "ioContract": io_contract,
        },
        "ioContract": io_contract,
        "execution": {
            "instructions": doc.get("instructions", ""),
            "connectorIds": lineage.get("connectorIds", []),
            "toolIds": lineage.get("toolIds", []),
            "trajectoryIds": lineage.get("trajectoryIds", []),
            "runtimeRequirements": doc.get("runtimeRequirements", []),
            "runtime": doc.get("runtime", ""),
        },
        "policies": {
            "riskPolicy": doc.get("riskPolicy", ""),
            "permissions": doc.get("permissions", {}),
            "runtimePolicy": serialize_runtime_policy(doc),
        },
        "evidence": {
            "lineage": lineage,
            "latestRegression": None,
            "hardeningStatus": hardening,
            "versionHistory": doc.get("versionHistory", []),
            "regressionSuite": {
                "benchmarkIds": [],
                "evalIds": [],
                "publishable": False,
            },
        },
        "progressiveDisclosure": {
            "summaryFields": ["metadata", "activation", "interface", "ioContract", "policies"],
            "fullFields": ["execution", "evidence"],
        },
    }


def attach_manual_skill_assets(doc: dict[str, Any]) -> dict[str, Any]:
    lineage = manual_skill_lineage(doc)
    hardening = manual_skill_hardening(doc, lineage)
    return {
        **doc,
        "lineage": lineage,
        "hardeningStatus": hardening,
        "skillPackage": manual_skill_package(doc, lineage, hardening),
    }
