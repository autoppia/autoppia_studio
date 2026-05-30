import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import evals_collection, operators_collection

router = APIRouter()


AUTOCINEMA_TASKS = [
    {"name": "Login", "prompt": "Log in to Autocinema with username user1 and password Passw0rd!", "status": "verified"},
    {"name": "Search film", "prompt": "Search for The Matrix in Autocinema", "status": "verified"},
    {"name": "Film detail", "prompt": "Open a film detail page in Autocinema", "status": "verified"},
]


class OperatorTask(BaseModel):
    name: str
    prompt: str
    successCriteria: str = ""
    status: str = "draft"
    trajectoryId: str = ""


class OperatorCreateRequest(BaseModel):
    email: str
    name: str
    websiteUrl: str
    authUsername: str = ""
    authPassword: str = ""
    successCriteria: str = ""
    tasks: List[OperatorTask] = []


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
                "$setOnInsert": {
                    "evalId": eval_id,
                    "email": email,
                    "prompt": prompt,
                    "initialUrl": website_url,
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


@router.get("/operators")
async def get_operators(email: str):
    try:
        cursor = operators_collection.find({"email": email}).sort("createdAt", -1)
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
            "name": body.name,
            "websiteUrl": body.websiteUrl,
            "runtimeEndpoint": "",
            "runtimeType": "pending",
            "status": "draft",
            "trainingStatus": "needs_trajectories",
            "harvester": "Automata Operator",
            "tasks": [task.model_dump() for task in body.tasks],
            "trajectories": [],
            "successCriteria": body.successCriteria,
            "auth": {
                "hasCredentials": bool(body.authUsername or body.authPassword),
                "username": body.authUsername,
                "passwordConfigured": bool(body.authPassword),
            },
            "createdAt": now,
            "updatedAt": now,
        }
        await operators_collection.insert_one(doc)
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
                "websiteUrl": "http://84.247.180.192:8000",
                "runtimeEndpoint": "http://127.0.0.1:5060/act",
                "runtimeType": "standard_replay_recovery",
                "status": "ready",
                "trainingStatus": "verified",
                "harvester": "Automata Operator",
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
                website_url="http://84.247.180.192:8000",
                tasks=AUTOCINEMA_TASKS,
            )
            return {
                "success": True,
                "operatorId": existing.get("operatorId"),
                "operator": _serialize_operator(refreshed or existing),
                "evalIds": eval_ids,
            }

        now = datetime.now(timezone.utc)
        operator_id = str(uuid.uuid4())
        doc = {
            "operatorId": operator_id,
            "email": body.email,
            "name": "Autocinema",
            "websiteUrl": "http://84.247.180.192:8000",
            "runtimeEndpoint": "http://127.0.0.1:5060/act",
            "runtimeType": "standard_replay_recovery",
            "status": "ready",
            "trainingStatus": "verified",
            "harvester": "Automata Operator",
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
            website_url="http://84.247.180.192:8000",
            tasks=AUTOCINEMA_TASKS,
        )
        return {"success": True, "operatorId": operator_id, "operator": _serialize_operator(doc), "evalIds": eval_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
