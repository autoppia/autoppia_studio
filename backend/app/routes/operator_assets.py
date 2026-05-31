import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import (
    capabilities_collection,
    operator_webs_collection,
    operators_collection,
    trajectories_collection,
)

router = APIRouter()


class OperatorWebCreateRequest(BaseModel):
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
    actions: List[Any] = []
    screenshots: List[str] = []


class CapabilityCreateRequest(BaseModel):
    email: str = ""
    webId: str = ""
    name: str
    description: str = ""
    type: str = "web"
    parameters: List[dict[str, Any]] = []
    trajectoryIds: List[str] = []
    runtime: str = "trajectory_replay_with_recovery"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_operator(operator_id: str) -> dict[str, Any]:
    operator = await operators_collection.find_one({"operatorId": operator_id}, {"_id": 0})
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
    return operator


@router.get("/operators/{operator_id}/webs")
async def list_operator_webs(operator_id: str):
    await _ensure_operator(operator_id)
    cursor = operator_webs_collection.find({"operatorId": operator_id}, {"_id": 0}).sort("createdAt", 1)
    return {"webs": await cursor.to_list(length=200)}


@router.post("/operators/{operator_id}/webs")
async def create_operator_web(operator_id: str, body: OperatorWebCreateRequest):
    operator = await _ensure_operator(operator_id)
    web_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "webId": web_id,
        "operatorId": operator_id,
        "email": body.email or operator.get("email", ""),
        "name": body.name,
        "baseUrl": body.baseUrl,
        "authRequired": body.authRequired,
        "createdAt": now,
        "updatedAt": now,
    }
    await operator_webs_collection.insert_one(doc)
    await operators_collection.update_one(
        {"operatorId": operator_id},
        {"$set": {"updatedAt": now, "websiteUrl": body.baseUrl}},
    )
    doc.pop("_id", None)
    return {"success": True, "web": doc}


@router.get("/operators/{operator_id}/trajectories")
async def list_operator_trajectories(operator_id: str):
    await _ensure_operator(operator_id)
    cursor = trajectories_collection.find({"operatorId": operator_id}, {"_id": 0}).sort("createdAt", -1)
    return {"trajectories": await cursor.to_list(length=500)}


@router.post("/operators/{operator_id}/trajectories")
async def create_operator_trajectory(operator_id: str, body: TrajectoryCreateRequest):
    operator = await _ensure_operator(operator_id)
    trajectory_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "trajectoryId": trajectory_id,
        "operatorId": operator_id,
        "email": body.email or operator.get("email", ""),
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
    await operators_collection.update_one(
        {"operatorId": operator_id},
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
    await trajectories_collection.update_one(
        {"trajectoryId": trajectory_id},
        {"$set": {"status": "approved", "updatedAt": now}},
    )

    capability_name = str(trajectory.get("taskName") or "capability").strip().lower().replace(" ", "_")
    capability = await capabilities_collection.find_one(
        {"operatorId": trajectory.get("operatorId"), "name": capability_name},
        {"_id": 0},
    )
    if capability:
        await capabilities_collection.update_one(
            {"capabilityId": capability["capabilityId"]},
            {
                "$set": {"updatedAt": now},
                "$addToSet": {"trajectoryIds": trajectory_id},
            },
        )
        capability_id = capability["capabilityId"]
    else:
        capability_id = str(uuid.uuid4())
        await capabilities_collection.insert_one(
            {
                "capabilityId": capability_id,
                "operatorId": trajectory.get("operatorId", ""),
                "email": trajectory.get("email", ""),
                "webId": trajectory.get("webId", ""),
                "name": capability_name,
                "description": trajectory.get("prompt", ""),
                "type": "web",
                "parameters": [],
                "trajectoryIds": [trajectory_id],
                "runtime": "trajectory_replay_with_recovery",
                "createdAt": now,
                "updatedAt": now,
            }
        )

    await operators_collection.update_one(
        {"operatorId": trajectory.get("operatorId")},
        {"$set": {"updatedAt": now, "trainingStatus": "verified"}},
    )
    return {"success": True, "capabilityId": capability_id}


@router.post("/trajectories/{trajectory_id}/convert-to-skill")
async def convert_trajectory_to_skill(trajectory_id: str):
    return await approve_trajectory(trajectory_id)


@router.get("/operators/{operator_id}/capabilities")
async def list_operator_capabilities(operator_id: str):
    await _ensure_operator(operator_id)
    cursor = capabilities_collection.find({"operatorId": operator_id}, {"_id": 0}).sort("createdAt", 1)
    return {"capabilities": await cursor.to_list(length=500)}


@router.get("/operators/{operator_id}/skills")
async def list_operator_skills(operator_id: str):
    payload = await list_operator_capabilities(operator_id)
    return {"skills": payload["capabilities"]}


@router.post("/operators/{operator_id}/capabilities")
async def create_operator_capability(operator_id: str, body: CapabilityCreateRequest):
    operator = await _ensure_operator(operator_id)
    capability_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "capabilityId": capability_id,
        "operatorId": operator_id,
        "email": body.email or operator.get("email", ""),
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
    await operators_collection.update_one({"operatorId": operator_id}, {"$set": {"updatedAt": now}})
    doc.pop("_id", None)
    return {"success": True, "capability": doc}


@router.post("/operators/{operator_id}/skills")
async def create_operator_skill(operator_id: str, body: CapabilityCreateRequest):
    payload = await create_operator_capability(operator_id, body)
    return {"success": True, "skill": payload["capability"]}
