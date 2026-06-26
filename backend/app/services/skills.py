from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.database import agents_collection, capabilities_collection, trajectories_collection
from app.services.runtime_policy import serialize_runtime_policy
from app.services.skill_lifecycle import append_skill_version_event
from app.services.skill_lifecycle import skill_lifecycle_fields
from app.services.skill_lifecycle import skill_promotion_status
from app.services.skill_lifecycle import skill_version
from app.services.skill_manifests import skill_package_manifest
from app.services.trajectory_judges import build_trajectory_judge_context, get_trajectory_judge


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def skill_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_")
    return text or "skill"


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _trajectory_actions(trajectory: dict[str, Any]) -> list[Any]:
    for key in ("trajectory", "actions", "steps"):
        value = trajectory.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _action_name(action: Any) -> str:
    if isinstance(action, dict):
        return str(action.get("name") or action.get("tool") or action.get("action") or "")
    return str(action or "")


def _side_effects_for_trajectory(trajectory: dict[str, Any]) -> str:
    action_names = [_action_name(action).lower() for action in _trajectory_actions(trajectory)]
    if any(token in name for name in action_names for token in ("send", "delete", "update", "create", "write", "draft")):
        return "writes"
    return "reads"


def _lineage_for_skill(skill: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectoryIds": _dedupe([*(skill.get("trajectoryIds") or []), trajectory.get("trajectoryId")]),
        "benchmarkIds": _dedupe([skill.get("benchmarkId"), trajectory.get("benchmarkId")]),
        "evalIds": _dedupe([skill.get("evalId"), trajectory.get("evalId"), trajectory.get("taskId")]),
        "connectorIds": _dedupe([*(skill.get("connectorIds") or []), *(trajectory.get("connectorIds") or [])]),
        "toolIds": _dedupe([*(skill.get("toolIds") or []), *(trajectory.get("toolIds") or [])]),
        "sources": _dedupe([skill.get("source"), trajectory.get("source")]),
    }


def _hardening_for_skill(skill: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "activation": bool(str(skill.get("whenToUse") or "").strip()),
        "instructions": bool(str(skill.get("instructions") or "").strip()),
        "riskPolicy": bool(str(skill.get("riskPolicy") or "").strip()),
        "lineage": bool(lineage.get("trajectoryIds")),
        "regression": bool(lineage.get("evalIds") or lineage.get("benchmarkIds")),
        "publishableRegression": False,
        "entities": bool((skill.get("inputEntities") or []) or str(skill.get("outputEntity") or "").strip()),
        "artifacts": bool(skill.get("expectedArtifacts") or skill.get("outputCard")),
    }
    passed = sum(1 for ready in checks.values() if ready)
    return {
        "checks": checks,
        "passedChecks": passed,
        "totalChecks": len(checks),
        "score": round(passed / len(checks), 3),
        "state": "drafting",
    }


def _source_trajectory_evidence(trajectory: dict[str, Any]) -> dict[str, Any]:
    actions = _trajectory_actions(trajectory)
    return {
        "trajectoryId": str(trajectory.get("trajectoryId") or ""),
        "benchmarkId": str(trajectory.get("benchmarkId") or ""),
        "evalId": str(trajectory.get("evalId") or trajectory.get("taskId") or ""),
        "status": str(trajectory.get("status") or ""),
        "source": str(trajectory.get("source") or ""),
        "actionCount": len(actions),
        "toolIds": _dedupe([*(trajectory.get("toolIds") or []), *[_action_name(action) for action in actions]]),
        "connectorIds": _dedupe([*(trajectory.get("connectorIds") or [])]),
    }


async def judge_harvested_trajectory(*, trajectory: dict[str, Any]) -> dict[str, Any]:
    agent_config = await agents_collection.find_one({"agentId": trajectory.get("agentId", "")}, {"_id": 0}) or {}
    return await get_trajectory_judge(agent_config.get("judgeImplementation")).judge(
        build_trajectory_judge_context(trajectory=trajectory, agent_config=agent_config)
    )


async def approve_trajectory_as_skill(trajectory: dict[str, Any], *, judge: dict[str, Any] | None = None) -> str:
    now = now_iso()
    trajectory_id = str(trajectory.get("trajectoryId") or "")
    agent_id = str(trajectory.get("agentId") or "")
    task_name = str(trajectory.get("taskName") or trajectory.get("name") or "Skill").strip()
    slug = skill_slug(task_name)
    capability_id = f"{agent_id}:{slug}" if agent_id else str(trajectory_id or slug)

    await trajectories_collection.update_one(
        {"trajectoryId": trajectory_id},
        {"$set": {"status": "approved", "judge": judge or {}, "updatedAt": now}},
    )

    agent = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0}) or {}
    existing = await capabilities_collection.find_one(
        {
            "$or": [
                {"capabilityId": capability_id},
                {"agentId": agent_id, "toolName": f"skill.{slug}"},
                {"agentId": agent_id, "name": task_name},
            ]
        },
        {"_id": 0},
    )
    capability_id = str((existing or {}).get("capabilityId") or capability_id)
    metadata = trajectory.get("metadata") if isinstance(trajectory.get("metadata"), dict) else {}
    trajectory_ids = _dedupe([*((existing or {}).get("trajectoryIds") or []), trajectory_id])
    existing_doc = existing or {}
    version = skill_version(existing_doc)
    version_label = str(existing_doc.get("versionLabel") or f"v{version}")
    side_effects = _side_effects_for_trajectory(trajectory)
    skill_doc = {
        **existing_doc,
        "capabilityId": capability_id,
        "capabilityKind": "skill",
        "skillId": capability_id,
        "agentId": agent_id,
        "companyId": trajectory.get("companyId") or agent.get("companyId", ""),
        "email": trajectory.get("email") or agent.get("email", ""),
        "webId": trajectory.get("webId", ""),
        "name": task_name,
        "toolName": f"skill.{slug}",
        "description": trajectory.get("prompt", ""),
        "whenToUse": trajectory.get("prompt", ""),
        "instructions": trajectory.get("prompt", ""),
        "preconditions": existing_doc.get("preconditions", []),
        "expectedArtifacts": existing_doc.get("expectedArtifacts", []),
        "inputSchema": existing_doc.get("inputSchema") or {"type": "object", "properties": {"instruction": {"type": "string"}}},
        "connectorIds": _dedupe([*(existing_doc.get("connectorIds") or []), *(trajectory.get("connectorIds") or [])]),
        "toolIds": _dedupe([*(existing_doc.get("toolIds") or []), *(trajectory.get("toolIds") or [])]),
        "trajectoryIds": trajectory_ids,
        "runtimeRequirements": _dedupe([*(existing_doc.get("runtimeRequirements") or []), *(trajectory.get("runtimeRequirements") or [])]),
        "benchmarkId": existing_doc.get("benchmarkId") or trajectory.get("benchmarkId", ""),
        "evalId": existing_doc.get("evalId") or trajectory.get("evalId") or trajectory.get("taskId") or "",
        "inputEntities": existing_doc.get("inputEntities") or trajectory.get("inputEntities", []),
        "outputEntity": existing_doc.get("outputEntity") or trajectory.get("outputEntity", ""),
        "outputCard": existing_doc.get("outputCard") or trajectory.get("outputCard", {}),
        "sideEffects": side_effects,
        "riskLevel": existing_doc.get("riskLevel") or ("medium" if side_effects != "reads" else "low"),
        "riskPolicy": existing_doc.get("riskPolicy") or "human_approval_for_writes",
        "permissions": existing_doc.get("permissions") or {"approval": "always" if side_effects != "reads" else "auto"},
        "runtime": existing_doc.get("runtime") or "trajectory_replay_with_recovery",
        "status": "ready",
        "promotionStatus": "ready",
        "source": trajectory.get("source") or "approved_trajectory",
        "harvesterType": trajectory.get("harvester", {}).get("adapter", "")
        if isinstance(trajectory.get("harvester"), dict)
        else trajectory.get("harvesterType", ""),
        "harvesterRunId": trajectory.get("harvesterRunId", ""),
        "discovererName": metadata.get("discoveredBy", ""),
        "discovererVersion": metadata.get("discovererVersion", ""),
        "judge": judge or {},
        "version": version,
        "versionLabel": version_label,
        "readyAt": existing_doc.get("readyAt") or now,
        "lastPromotedAt": existing_doc.get("lastPromotedAt") or "",
        "createdAt": existing_doc.get("createdAt") or now,
        "updatedAt": now,
    }
    skill_doc.update(skill_lifecycle_fields(previous=existing_doc, next_doc=skill_doc, now=now))
    lineage = _lineage_for_skill(skill_doc, trajectory)
    hardening = _hardening_for_skill(skill_doc, lineage)
    version_history = append_skill_version_event(
        existing_doc,
        skill_doc,
        now=now,
        reason="trajectory_approved",
    )
    skill_doc["lineage"] = lineage
    skill_doc["hardeningStatus"] = hardening
    skill_doc["versionHistory"] = version_history
    skill_doc["skillPackage"] = skill_package_manifest(
        skill_doc,
        version=version,
        promotion_status=skill_promotion_status(skill_doc),
        runtime_policy=serialize_runtime_policy(skill_doc),
        lineage=lineage,
        hardening=hardening,
        latest_regression=None,
        source_trajectories=[_source_trajectory_evidence(trajectory)],
        regression_cases=[],
        version_history=version_history,
    )
    await capabilities_collection.update_one(
        {"capabilityId": capability_id},
        {"$set": skill_doc},
        upsert=True,
    )
    await agents_collection.update_one({"agentId": agent_id}, {"$set": {"updatedAt": now, "trainingStatus": "verified"}})
    return capability_id
