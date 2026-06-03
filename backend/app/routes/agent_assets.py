import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    agent_creation_jobs_collection,
    capabilities_collection,
    agent_webs_collection,
    agents_collection,
    trajectories_collection,
)
from app.services.skills import approve_trajectory_as_skill

router = APIRouter()


class AgentWebCreateRequest(BaseModel):
    email: str = ""
    name: str
    baseUrl: str
    authRequired: bool = False


class TrajectoryCreateRequest(BaseModel):
    email: str = ""
    webId: str = ""
    taskName: str
    prompt: str
    successCriteria: str = ""
    source: str = "user"
    status: str = "draft"
    actions: List[Any] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)


class CapabilityCreateRequest(BaseModel):
    email: str = ""
    webId: str = ""
    name: str
    description: str = ""
    type: str = "web"
    parameters: List[dict[str, Any]] = Field(default_factory=list)
    trajectoryIds: List[str] = Field(default_factory=list)
    runtime: str = "trajectory_replay_with_recovery"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_agent_config(agent_id: str) -> dict[str, Any]:
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_config


@router.get("/agents/{agent_id}/webs")
async def list_agent_webs(agent_id: str):
    await _ensure_agent_config(agent_id)
    cursor = agent_webs_collection.find({"agentId": agent_id}, {"_id": 0}).sort("createdAt", 1)
    return {"webs": await cursor.to_list(length=200)}


@router.post("/agents/{agent_id}/webs")
async def create_agent_web(agent_id: str, body: AgentWebCreateRequest):
    agent_config = await _ensure_agent_config(agent_id)
    web_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "webId": web_id,
        "agentId": agent_id,
        "email": body.email or agent_config.get("email", ""),
        "name": body.name,
        "baseUrl": body.baseUrl,
        "authRequired": body.authRequired,
        "createdAt": now,
        "updatedAt": now,
    }
    await agent_webs_collection.insert_one(doc)
    await agents_collection.update_one(
        {"agentId": agent_id},
        {"$set": {"updatedAt": now, "websiteUrl": body.baseUrl}},
    )
    doc.pop("_id", None)
    return {"success": True, "web": doc}


@router.get("/agents/{agent_id}/trajectories")
async def list_agent_trajectories(agent_id: str):
    await _ensure_agent_config(agent_id)
    cursor = trajectories_collection.find({"agentId": agent_id}, {"_id": 0}).sort("createdAt", -1)
    return {"trajectories": await cursor.to_list(length=500)}


@router.post("/agents/{agent_id}/trajectories")
async def create_agent_trajectory(agent_id: str, body: TrajectoryCreateRequest):
    agent_config = await _ensure_agent_config(agent_id)
    trajectory_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "trajectoryId": trajectory_id,
        "agentId": agent_id,
        "email": body.email or agent_config.get("email", ""),
        "webId": body.webId,
        "taskName": body.taskName,
        "prompt": body.prompt,
        "successCriteria": body.successCriteria,
        "source": body.source,
        "status": body.status,
        "actions": body.actions,
        "screenshots": body.screenshots,
        "createdAt": now,
        "updatedAt": now,
    }
    await trajectories_collection.insert_one(doc)
    await agents_collection.update_one(
        {"agentId": agent_id},
        {
            "$set": {"updatedAt": now, "trainingStatus": "needs_review"},
            "$push": {"trajectories": {"name": body.taskName, "status": body.status, "source": body.source}},
        },
    )
    doc.pop("_id", None)
    return {"success": True, "trajectory": doc}


@router.post("/trajectories/{trajectory_id}/approve")
async def approve_trajectory(trajectory_id: str):
    trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")

    now = _now()
    capability_id = await approve_trajectory_as_skill(trajectory, judge={"label": "pass", "judge": "human", "confidence": 1.0, "needsHumanReview": False})
    agent_id = str(trajectory.get("agentId") or "")
    pending = await trajectories_collection.count_documents(
        {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}}
    )
    job = await agent_creation_jobs_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if job:
        steps = []
        for step in job.get("steps", []):
            key = step.get("key")
            if key in {"review_trajectories", "approve_trajectories", "build_skills"}:
                steps.append({
                    **step,
                    "status": "done" if pending == 0 else "in_progress",
                    "message": "Approved trajectory converted into a reusable skill." if pending == 0 else f"{pending} trajectories still need review.",
                    "updatedAt": now,
                })
            elif key == "run_benchmark" and pending == 0:
                steps.append({**step, "status": "ready", "message": "Ready to run benchmark against this custom agent.", "updatedAt": now})
            else:
                steps.append(step)
        await agent_creation_jobs_collection.update_one(
            {"jobId": job["jobId"]},
            {
                "$set": {
                    "status": "ready_for_benchmark" if pending == 0 else "awaiting_review",
                    "currentStep": "run_benchmark" if pending == 0 else "review_trajectories",
                    "steps": steps,
                    "updatedAt": now,
                },
                "$push": {"events": {"type": "progress", "message": "Approved trajectory and created/updated skill.", "createdAt": now}},
            },
        )
    return {"success": True, "capabilityId": capability_id}


@router.post("/trajectories/{trajectory_id}/convert-to-skill")
async def convert_trajectory_to_skill(trajectory_id: str):
    return await approve_trajectory(trajectory_id)


@router.get("/agents/{agent_id}/capabilities")
async def list_agent_capabilities(agent_id: str):
    await _ensure_agent_config(agent_id)
    cursor = capabilities_collection.find({"agentId": agent_id}, {"_id": 0}).sort("createdAt", 1)
    return {"capabilities": await cursor.to_list(length=500)}


@router.get("/agents/{agent_id}/skills")
async def list_agent_skills(agent_id: str):
    payload = await list_agent_capabilities(agent_id)
    return {"skills": payload["capabilities"]}


@router.post("/agents/{agent_id}/capabilities")
async def create_agent_capability(agent_id: str, body: CapabilityCreateRequest):
    agent_config = await _ensure_agent_config(agent_id)
    capability_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "capabilityId": capability_id,
        "agentId": agent_id,
        "email": body.email or agent_config.get("email", ""),
        "webId": body.webId,
        "name": body.name,
        "description": body.description,
        "type": body.type if body.type in {"web", "api", "hybrid"} else "web",
        "parameters": body.parameters,
        "trajectoryIds": body.trajectoryIds,
        "runtime": body.runtime,
        "createdAt": now,
        "updatedAt": now,
    }
    await capabilities_collection.insert_one(doc)
    await agents_collection.update_one({"agentId": agent_id}, {"$set": {"updatedAt": now}})
    doc.pop("_id", None)
    return {"success": True, "capability": doc}


@router.post("/agents/{agent_id}/skills")
async def create_agent_skill(agent_id: str, body: CapabilityCreateRequest):
    payload = await create_agent_capability(agent_id, body)
    return {"success": True, "skill": payload["capability"]}
