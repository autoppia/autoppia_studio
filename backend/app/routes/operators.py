import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    capabilities_collection,
    evals_collection,
    operator_webs_collection,
    operators_collection,
    trajectories_collection,
)

router = APIRouter()


AUTOCINEMA_TASKS = [
    {"name": "Login", "prompt": "Log in to Autocinema with username user1 and password Passw0rd!", "status": "verified"},
    {"name": "Search film", "prompt": "Search for The Matrix in Autocinema", "status": "verified"},
    {"name": "Film detail", "prompt": "Open a film detail page in Autocinema", "status": "verified"},
]

AUTOCINEMA_URL = "http://84.247.180.192:8000"
AUTOCINEMA_RUNTIME = "http://127.0.0.1:5060/act"

AUTOCINEMA_CAPABILITIES = [
    {"name": "login", "taskName": "Login", "description": "Log in to Autocinema with the bundled demo credentials."},
    {"name": "search_film", "taskName": "Search film", "description": "Search for a film by title in Autocinema."},
    {"name": "open_film_detail", "taskName": "Film detail", "description": "Open a film detail page from Autocinema."},
]


class OperatorTask(BaseModel):
    name: str
    prompt: str
    successCriteria: str = ""
    status: str = "draft"
    trajectoryId: str = ""


class OperatorCreateRequest(BaseModel):
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
    tasks: List[OperatorTask] = Field(default_factory=list)


class OperatorBootstrapRequest(BaseModel):
    email: str


def _serialize_operator(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "operatorId": doc.get("operatorId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeEndpoint": doc.get("runtimeEndpoint", ""),
        "runtimeType": doc.get("runtimeType", "replay"),
        "status": doc.get("status", "draft"),
        "trainingStatus": doc.get("trainingStatus", "not_started"),
        "harvester": doc.get("harvester", "Automata Operator"),
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


async def _ensure_operator_evals(
    *,
    email: str,
    operator_id: str,
    operator_name: str,
    website_url: str,
    tasks: list[dict[str, Any]],
) -> list[str]:
    eval_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    benchmark_id = f"operator-{operator_id}"
    for task in tasks:
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        eval_id = str(uuid.uuid4())
        result = await evals_collection.update_one(
            {
                "email": email,
                "operatorId": operator_id,
                "prompt": prompt,
            },
            {
                "$set": {
                    "benchmarkId": benchmark_id,
                    "benchmarkName": f"{operator_name} Benchmark",
                    "initialUrl": website_url,
                },
                "$setOnInsert": {
                    "evalId": eval_id,
                    "email": email,
                    "prompt": prompt,
                    "operatorId": operator_id,
                    "operatorName": operator_name,
                    "operatorTaskName": str(task.get("name") or ""),
                    "createdAt": now,
                }
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            eval_ids.append(eval_id)
        else:
            existing = await evals_collection.find_one(
                {"email": email, "operatorId": operator_id, "prompt": prompt},
                {"_id": 0, "evalId": 1},
            )
            if existing and existing.get("evalId"):
                eval_ids.append(str(existing["evalId"]))
    return eval_ids


async def _ensure_autocinema_assets(*, email: str, operator_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    web_id = f"autocinema-{operator_id}"
    await operator_webs_collection.update_one(
        {"webId": web_id},
        {
            "$set": {
                "operatorId": operator_id,
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
        trajectory_id = f"autocinema-{operator_id}-{task['name'].lower().replace(' ', '-')}"
        trajectory_ids_by_task[task["name"]] = trajectory_id
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory_id},
            {
                "$set": {
                    "operatorId": operator_id,
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
        capability_id = f"autocinema-{operator_id}-{capability['name']}"
        await capabilities_collection.update_one(
            {"capabilityId": capability_id},
            {
                "$set": {
                    "operatorId": operator_id,
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


@router.get("/operators")
async def get_operators(email: str, companyId: str = ""):
    try:
        query: dict[str, Any] = {"email": email}
        if companyId:
            query["companyId"] = companyId
        cursor = operators_collection.find(query).sort("createdAt", -1)
        operators = []
        async for doc in cursor:
            operators.append(_serialize_operator(doc))
        return {"operators": operators}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operators/{operator_id}")
async def get_operator(operator_id: str):
    try:
        doc = await operators_collection.find_one({"operatorId": operator_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Operator not found")
        return {"operator": _serialize_operator(doc)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operators")
async def create_operator(body: OperatorCreateRequest):
    try:
        now = datetime.now(timezone.utc)
        operator_id = str(uuid.uuid4())
        doc = {
            "operatorId": operator_id,
            "email": body.email,
            "companyId": body.companyId,
            "name": body.name,
            "websiteUrl": body.websiteUrl,
            "runtimeEndpoint": "",
            "runtimeType": "pending",
            "status": "draft",
            "trainingStatus": "needs_trajectories",
            "harvester": "Automata Operator",
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
        await operators_collection.insert_one(doc)
        web_id = f"default-{operator_id}"
        await operator_webs_collection.insert_one(
            {
                "webId": web_id,
                "operatorId": operator_id,
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
                    "operatorId": operator_id,
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
        eval_ids = await _ensure_operator_evals(
            email=body.email,
            operator_id=operator_id,
            operator_name=body.name,
            website_url=body.websiteUrl,
            tasks=[task.model_dump() for task in body.tasks],
        )
        return {"success": True, "operatorId": operator_id, "evalIds": eval_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operators/bootstrap/autocinema")
async def bootstrap_autocinema_operator(body: OperatorBootstrapRequest):
    try:
        existing = await operators_collection.find_one(
            {"email": body.email, "name": "Autocinema"}
        )
        if existing:
            updates = {
                "websiteUrl": AUTOCINEMA_URL,
                "runtimeEndpoint": AUTOCINEMA_RUNTIME,
                "runtimeType": "standard_replay_recovery",
                "status": "ready",
                "trainingStatus": "verified",
                "harvester": "Automata Operator",
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
            await operators_collection.update_one(
                {"operatorId": existing.get("operatorId")},
                {"$set": updates},
            )
            refreshed = await operators_collection.find_one({"operatorId": existing.get("operatorId")})
            eval_ids = await _ensure_operator_evals(
                email=body.email,
                operator_id=str(existing.get("operatorId") or ""),
                operator_name="Autocinema",
                website_url=AUTOCINEMA_URL,
                tasks=AUTOCINEMA_TASKS,
            )
            assets = await _ensure_autocinema_assets(
                email=body.email,
                operator_id=str(existing.get("operatorId") or ""),
            )
            return {
                "success": True,
                "operatorId": existing.get("operatorId"),
                "operator": _serialize_operator(refreshed or existing),
                "evalIds": eval_ids,
                "assets": assets,
            }

        now = datetime.now(timezone.utc)
        operator_id = str(uuid.uuid4())
        doc = {
            "operatorId": operator_id,
            "email": body.email,
            "name": "Autocinema",
            "websiteUrl": AUTOCINEMA_URL,
            "runtimeEndpoint": AUTOCINEMA_RUNTIME,
            "runtimeType": "standard_replay_recovery",
            "status": "ready",
            "trainingStatus": "verified",
            "harvester": "Automata Operator",
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
        await operators_collection.insert_one(doc)
        eval_ids = await _ensure_operator_evals(
            email=body.email,
            operator_id=operator_id,
            operator_name="Autocinema",
            website_url=AUTOCINEMA_URL,
            tasks=AUTOCINEMA_TASKS,
        )
        assets = await _ensure_autocinema_assets(email=body.email, operator_id=operator_id)
        return {
            "success": True,
            "operatorId": operator_id,
            "operator": _serialize_operator(doc),
            "evalIds": eval_ids,
            "assets": assets,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
