from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.database import agents_collection, capabilities_collection, trajectories_collection
from app.services.trajectory_judges import build_trajectory_judge_context, get_trajectory_judge


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def skill_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_")
    return text or "skill"


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
    await capabilities_collection.update_one(
        {"capabilityId": capability_id},
        {
            "$set": {
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
                "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}},
                "connectorIds": trajectory.get("connectorIds", []),
                "toolIds": trajectory.get("toolIds", []),
                "runtimeRequirements": trajectory.get("runtimeRequirements", []),
                "inputEntities": trajectory.get("inputEntities", []),
                "outputEntity": trajectory.get("outputEntity", ""),
                "outputCard": trajectory.get("outputCard", {}),
                "sideEffects": "writes"
                if any(
                    "send" in str((tool.get("name") or tool.get("action") or tool) if isinstance(tool, dict) else tool).lower()
                    for tool in (trajectory.get("trajectory") or trajectory.get("actions") or [])
                )
                else "reads",
                "riskLevel": "medium",
                "riskPolicy": "human_approval_for_writes",
                "runtime": "trajectory_replay_with_recovery",
                "status": "approved",
                "source": trajectory.get("source") or "approved_trajectory",
                "harvesterType": trajectory.get("harvester", {}).get("adapter", "")
                if isinstance(trajectory.get("harvester"), dict)
                else trajectory.get("harvesterType", ""),
                "harvesterRunId": trajectory.get("harvesterRunId", ""),
                "discovererName": metadata.get("discoveredBy", ""),
                "discovererVersion": metadata.get("discovererVersion", ""),
                "judge": judge or {},
                "updatedAt": now,
            },
            "$addToSet": {"trajectoryIds": trajectory_id},
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
    )
    await agents_collection.update_one({"agentId": agent_id}, {"$set": {"updatedAt": now, "trainingStatus": "verified"}})
    return capability_id
