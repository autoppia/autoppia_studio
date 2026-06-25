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
from app.services.runtime_policy import serialize_runtime_policy
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
    whenToUse: str = ""
    instructions: str = ""
    preconditions: List[str] = Field(default_factory=list)
    expectedArtifacts: List[str] = Field(default_factory=list)
    permissions: dict[str, Any] = Field(default_factory=dict)
    riskPolicy: str = "human_approval_for_writes"
    inputEntities: List[str] = Field(default_factory=list)
    outputEntity: str = ""
    outputCard: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _manual_skill_lineage(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectoryIds": _dedupe(doc.get("trajectoryIds") or []),
        "benchmarkIds": [],
        "evalIds": [],
        "connectorIds": _dedupe(doc.get("connectorIds") or []),
        "toolIds": _dedupe(doc.get("toolIds") or []),
        "sources": _dedupe([doc.get("source")]),
    }


def _manual_skill_hardening(doc: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
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


def _manual_skill_package(doc: dict[str, Any], lineage: dict[str, Any], hardening: dict[str, Any]) -> dict[str, Any]:
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
        "capabilityKind": "skill",
        "skillId": capability_id,
        "agentId": agent_id,
        "email": body.email or agent_config.get("email", ""),
        "companyId": agent_config.get("companyId", ""),
        "webId": body.webId,
        "name": body.name,
        "description": body.description,
        "whenToUse": body.whenToUse or body.description,
        "instructions": body.instructions or body.description,
        "preconditions": _dedupe(body.preconditions),
        "expectedArtifacts": _dedupe(body.expectedArtifacts),
        "permissions": body.permissions,
        "riskPolicy": body.riskPolicy,
        "inputEntities": _dedupe(body.inputEntities),
        "outputEntity": body.outputEntity,
        "outputCard": body.outputCard,
        "type": body.type if body.type in {"web", "api", "hybrid"} else "web",
        "parameters": body.parameters,
        "trajectoryIds": _dedupe(body.trajectoryIds),
        "runtime": body.runtime,
        "status": "ready" if body.trajectoryIds else "draft",
        "promotionStatus": "ready" if body.trajectoryIds else "draft",
        "version": 1,
        "versionLabel": "v1",
        "versionHistory": [
            {
                "version": 1,
                "versionLabel": "v1",
                "promotionStatus": "ready" if body.trajectoryIds else "draft",
                "reason": "manual_skill_created",
                "createdAt": now,
            }
        ],
        "readyAt": now if body.trajectoryIds else "",
        "lastPromotedAt": now if body.trajectoryIds else "",
        "source": "manual_agent_asset",
        "createdAt": now,
        "updatedAt": now,
    }
    lineage = _manual_skill_lineage(doc)
    hardening = _manual_skill_hardening(doc, lineage)
    doc["lineage"] = lineage
    doc["hardeningStatus"] = hardening
    doc["skillPackage"] = _manual_skill_package(doc, lineage, hardening)
    await capabilities_collection.insert_one(doc)
    await agents_collection.update_one({"agentId": agent_id}, {"$set": {"updatedAt": now}})
    doc.pop("_id", None)
    return {"success": True, "capability": doc}


@router.post("/agents/{agent_id}/skills")
async def create_agent_skill(agent_id: str, body: CapabilityCreateRequest):
    payload = await create_agent_capability(agent_id, body)
    return {"success": True, "skill": payload["capability"]}
