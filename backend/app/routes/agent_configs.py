import uuid
import os
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    capabilities_collection,
    evals_collection,
    agent_webs_collection,
    agents_collection,
    trajectories_collection,
)
from app.routes.agent_creation import ensure_agent_creation_job

router = APIRouter()


AUTOCINEMA_TASKS = [
    {"name": "Login", "prompt": "Log in to Autocinema with username user1 and password Passw0rd!", "status": "verified"},
    {"name": "Search film", "prompt": "Search for The Matrix in Autocinema", "status": "verified"},
    {"name": "Film detail", "prompt": "Open a film detail page in Autocinema", "status": "verified"},
]

AUTOCINEMA_URL = "http://84.247.180.192:8000"
AUTOCINEMA_RUNTIME = "http://127.0.0.1:5060/step"
DEFAULT_AGENT_RUNTIME_ENDPOINT = os.getenv("AUTOMATA_DEFAULT_RUNTIME_ENDPOINT", AUTOCINEMA_RUNTIME).strip()
DEFAULT_AGENT_RUNTIME_TYPE = os.getenv("AUTOMATA_DEFAULT_RUNTIME_TYPE", "generalist_with_company_capabilities").strip()
DEFAULT_RUNTIME_PROXY_BASE = os.getenv("AUTOMATA_RUNTIME_PROXY_BASE", "http://127.0.0.1:8080").rstrip("/")

AUTOCINEMA_CAPABILITIES = [
    {"name": "login", "taskName": "Login", "description": "Log in to Autocinema with the bundled demo credentials."},
    {"name": "search_film", "taskName": "Search film", "description": "Search for a film by title in Autocinema."},
    {"name": "open_film_detail", "taskName": "Film detail", "description": "Open a film detail page from Autocinema."},
]


class AgentTask(BaseModel):
    name: str
    prompt: str
    successCriteria: str = ""
    status: str = "draft"
    trajectoryId: str = ""


class AgentConfigCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    name: str
    websiteUrl: str
    authUsername: str = ""
    authPassword: str = ""
    apiSpecUrl: str = ""
    apiAuthHeaderName: str = ""
    apiAuthHeaderValue: str = ""
    successCriteria: str = ""
    tasks: List[AgentTask] = Field(default_factory=list)


class AgentBootstrapRequest(BaseModel):
    email: str


def _serialize_agent_config(doc: dict[str, Any]) -> dict[str, Any]:
    agent_id = doc.get("agentId", "")
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeEndpoint": doc.get("runtimeEndpoint", ""),
        "runtimeType": doc.get("runtimeType", "replay"),
        "status": doc.get("status", "draft"),
        "trainingStatus": doc.get("trainingStatus", "not_started"),
        "harvester": doc.get("harvester", "Automata Agent"),
        "companyId": doc.get("companyId", ""),
        "runtimeCapabilities": doc.get("runtimeCapabilities", {"browser": True, "apiCalls": True, "knowledge": False, "python": False}),
        "apiSpecUrl": doc.get("apiSpecUrl", ""),
        "apiAuthConfigured": bool(doc.get("apiAuth", {}).get("headerValueConfigured")),
        "tasks": doc.get("tasks", []),
        "trajectories": doc.get("trajectories", []),
        "successCriteria": doc.get("successCriteria", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _ensure_agent_evals(
    *,
    email: str,
    agent_id: str,
    agent_name: str,
    website_url: str,
    tasks: list[dict[str, Any]],
) -> list[str]:
    eval_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    benchmark_id = f"agent-{agent_id}"
    for task in tasks:
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        eval_id = str(uuid.uuid4())
        result = await evals_collection.update_one(
            {
                "email": email,
                "agentId": agent_id,
                "prompt": prompt,
            },
            {
                "$set": {
                    "benchmarkId": benchmark_id,
                    "benchmarkName": f"{agent_name} Benchmark",
                    "initialUrl": website_url,
                },
                "$setOnInsert": {
                    "evalId": eval_id,
                    "email": email,
                    "prompt": prompt,
                    "agentId": agent_id,
                    "agentName": agent_name,
                    "agentTaskName": str(task.get("name") or ""),
                    "createdAt": now,
                }
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            eval_ids.append(eval_id)
        else:
            existing = await evals_collection.find_one(
                {"email": email, "agentId": agent_id, "prompt": prompt},
                {"_id": 0, "evalId": 1},
            )
            if existing and existing.get("evalId"):
                eval_ids.append(str(existing["evalId"]))
    return eval_ids


async def _ensure_autocinema_assets(*, email: str, agent_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    web_id = f"autocinema-{agent_id}"
    await agent_webs_collection.update_one(
        {"webId": web_id},
        {
            "$set": {
                "agentId": agent_id,
                "email": email,
                "name": "Autocinema",
                "baseUrl": AUTOCINEMA_URL,
                "authRequired": True,
                "updatedAt": now,
            },
            "$setOnInsert": {"webId": web_id, "createdAt": now},
        },
        upsert=True,
    )

    trajectory_ids_by_task: dict[str, str] = {}
    for task in AUTOCINEMA_TASKS:
        trajectory_id = f"autocinema-{agent_id}-{task['name'].lower().replace(' ', '-')}"
        trajectory_ids_by_task[task["name"]] = trajectory_id
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory_id},
            {
                "$set": {
                    "agentId": agent_id,
                    "email": email,
                    "webId": web_id,
                    "taskName": task["name"],
                    "prompt": task["prompt"],
                    "successCriteria": "User confirms replay success or IWA reward accepts the task.",
                    "source": "bundled_autocinema_package",
                    "status": "approved",
                    "actions": [],
                    "screenshots": [],
                    "updatedAt": now,
                },
                "$setOnInsert": {"trajectoryId": trajectory_id, "createdAt": now},
            },
            upsert=True,
        )

    for capability in AUTOCINEMA_CAPABILITIES:
        capability_id = f"autocinema-{agent_id}-{capability['name']}"
        await capabilities_collection.update_one(
            {"capabilityId": capability_id},
            {
                "$set": {
                    "agentId": agent_id,
                    "email": email,
                    "webId": web_id,
                    "name": capability["name"],
                    "description": capability["description"],
                    "type": "web",
                    "parameters": [],
                    "trajectoryIds": [trajectory_ids_by_task[capability["taskName"]]],
                    "runtime": "trajectory_replay_with_recovery",
                    "updatedAt": now,
                },
                "$setOnInsert": {"capabilityId": capability_id, "createdAt": now},
            },
            upsert=True,
        )

    return {"webId": web_id, "trajectoryIds": list(trajectory_ids_by_task.values())}


@router.get("/agents")
async def get_agents(email: str, companyId: str = ""):
    try:
        query: dict[str, Any] = {"email": email}
        if companyId:
            query["companyId"] = companyId
        cursor = agents_collection.find(query).sort("createdAt", -1)
        agents = []
        async for doc in cursor:
            agents.append(_serialize_agent_config(doc))
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    try:
        doc = await agents_collection.find_one({"agentId": agent_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent = _serialize_agent_config(doc)
        return {"agent": agent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents")
async def create_agent(body: AgentConfigCreateRequest):
    try:
        now = datetime.now(timezone.utc)
        agent_id = str(uuid.uuid4())
        runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step" if DEFAULT_AGENT_RUNTIME_ENDPOINT else ""
        doc = {
            "agentId": agent_id,
            "email": body.email,
            "companyId": body.companyId,
            "name": body.name,
            "websiteUrl": body.websiteUrl,
            "runtimeEndpoint": runtime_endpoint,
            "baseRuntimeEndpoint": DEFAULT_AGENT_RUNTIME_ENDPOINT,
            "runtimeType": DEFAULT_AGENT_RUNTIME_TYPE if DEFAULT_AGENT_RUNTIME_ENDPOINT else "pending",
            "status": "ready" if DEFAULT_AGENT_RUNTIME_ENDPOINT else "draft",
            "trainingStatus": "needs_trajectories",
            "harvester": "Automata Agent",
            "runtimeCapabilities": {
                "browser": True,
                "apiCalls": True,
                "knowledge": False,
                "python": False,
                "humanApprovalForWrites": True,
            },
            "tasks": [task.model_dump() for task in body.tasks],
            "trajectories": [],
            "successCriteria": body.successCriteria,
            "apiSpecUrl": body.apiSpecUrl.strip(),
            "apiAuth": {
                "headerName": body.apiAuthHeaderName.strip(),
                "headerValueConfigured": bool(body.apiAuthHeaderValue),
            },
            "auth": {
                "hasCredentials": bool(body.authUsername or body.authPassword),
                "username": body.authUsername,
                "passwordConfigured": bool(body.authPassword),
            },
            "createdAt": now,
            "updatedAt": now,
        }
        await agents_collection.insert_one(doc)
        await ensure_agent_creation_job(doc)
        web_id = f"default-{agent_id}"
        await agent_webs_collection.insert_one(
            {
                "webId": web_id,
                "agentId": agent_id,
                "email": body.email,
                "name": body.name,
                "baseUrl": body.websiteUrl,
                "authRequired": bool(body.authUsername or body.authPassword),
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
            }
        )
        for task in body.tasks:
            if not task.prompt.strip():
                continue
            trajectory_id = str(uuid.uuid4())
            await trajectories_collection.insert_one(
                {
                    "trajectoryId": trajectory_id,
                    "agentId": agent_id,
                    "email": body.email,
                    "webId": web_id,
                    "taskName": task.name,
                    "prompt": task.prompt,
                    "successCriteria": task.successCriteria,
                    "source": "user_prompt",
                    "status": "needs_harvest",
                    "actions": [],
                    "screenshots": [],
                    "createdAt": now.isoformat(),
                    "updatedAt": now.isoformat(),
                }
            )
        eval_ids = await _ensure_agent_evals(
            email=body.email,
            agent_id=agent_id,
            agent_name=body.name,
            website_url=body.websiteUrl,
            tasks=[task.model_dump() for task in body.tasks],
        )
        return {"success": True, "agentId": agent_id, "agentConfigId": agent_id, "evalIds": eval_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/bootstrap/autocinema")
async def bootstrap_autocinema_agent(body: AgentBootstrapRequest):
    try:
        existing = await agents_collection.find_one(
            {"email": body.email, "name": "Autocinema"}
        )
        if existing:
            updates = {
                "websiteUrl": AUTOCINEMA_URL,
                "runtimeEndpoint": AUTOCINEMA_RUNTIME,
                "runtimeType": "standard_replay_recovery",
                "status": "ready",
                "trainingStatus": "verified",
                "harvester": "Automata Agent",
                "runtimeCapabilities": {
                    "browser": True,
                    "apiCalls": True,
                    "knowledge": False,
                    "python": False,
                    "humanApprovalForWrites": True,
                },
                "apiSpecUrl": "",
                "apiAuth": {"headerName": "", "headerValueConfigured": False},
                "tasks": AUTOCINEMA_TASKS,
                "trajectories": [
                    {"name": task["name"], "status": "verified", "source": "bundled_autocinema_package"}
                    for task in AUTOCINEMA_TASKS
                ],
                "successCriteria": "IWA benchmark success for the matched Autocinema task.",
                "updatedAt": datetime.now(timezone.utc),
            }
            await agents_collection.update_one(
                {"agentId": existing.get("agentId")},
                {"$set": updates},
            )
            refreshed = await agents_collection.find_one({"agentId": existing.get("agentId")})
            eval_ids = await _ensure_agent_evals(
                email=body.email,
                agent_id=str(existing.get("agentId") or ""),
                agent_name="Autocinema",
                website_url=AUTOCINEMA_URL,
                tasks=AUTOCINEMA_TASKS,
            )
            assets = await _ensure_autocinema_assets(
                email=body.email,
                agent_id=str(existing.get("agentId") or ""),
            )
            return {
                "success": True,
                "agentId": existing.get("agentId"),
                "agentConfigId": existing.get("agentId"),
                "agent": _serialize_agent_config(refreshed or existing),
                "evalIds": eval_ids,
                "assets": assets,
            }

        now = datetime.now(timezone.utc)
        agent_id = str(uuid.uuid4())
        doc = {
            "agentId": agent_id,
            "email": body.email,
            "name": "Autocinema",
            "websiteUrl": AUTOCINEMA_URL,
            "runtimeEndpoint": AUTOCINEMA_RUNTIME,
            "runtimeType": "standard_replay_recovery",
            "status": "ready",
            "trainingStatus": "verified",
            "harvester": "Automata Agent",
            "companyId": "",
            "runtimeCapabilities": {
                "browser": True,
                "apiCalls": True,
                "knowledge": False,
                "python": False,
                "humanApprovalForWrites": True,
            },
            "apiSpecUrl": "",
            "apiAuth": {"headerName": "", "headerValueConfigured": False},
            "tasks": AUTOCINEMA_TASKS,
            "trajectories": [
                {"name": task["name"], "status": "verified", "source": "bundled_autocinema_package"}
                for task in AUTOCINEMA_TASKS
            ],
            "successCriteria": "IWA benchmark success for the matched Autocinema task.",
            "createdAt": now,
            "updatedAt": now,
        }
        await agents_collection.insert_one(doc)
        eval_ids = await _ensure_agent_evals(
            email=body.email,
            agent_id=agent_id,
            agent_name="Autocinema",
            website_url=AUTOCINEMA_URL,
            tasks=AUTOCINEMA_TASKS,
        )
        assets = await _ensure_autocinema_assets(email=body.email, agent_id=agent_id)
        return {
            "success": True,
            "agentId": agent_id,
            "agentConfigId": agent_id,
            "agent": _serialize_agent_config(doc),
            "evalIds": eval_ids,
            "assets": assets,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
