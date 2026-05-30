import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import operators_collection

router = APIRouter()


AUTOCINEMA_TASKS = [
    {"name": "Login", "prompt": "Log in to Autocinema with the provided username and password.", "status": "verified"},
    {"name": "Contact", "prompt": "Open the contact page and send a support message.", "status": "verified"},
    {"name": "Film detail", "prompt": "Open a film detail page.", "status": "verified"},
    {"name": "Search film", "prompt": "Search for a film by title.", "status": "verified"},
    {"name": "Filter films", "prompt": "Filter films by genre.", "status": "verified"},
    {"name": "Logout", "prompt": "Log out of the current account.", "status": "verified"},
    {"name": "Add comment", "prompt": "Add a comment to a film.", "status": "verified"},
    {"name": "Add to watchlist", "prompt": "Add a film to the watchlist.", "status": "verified"},
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
        return {"success": True, "operatorId": operator_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operators/bootstrap/autocinema")
async def bootstrap_autocinema_operator(body: OperatorBootstrapRequest):
    try:
        existing = await operators_collection.find_one(
            {"email": body.email, "name": "Autocinema"}
        )
        if existing:
            return {"success": True, "operatorId": existing.get("operatorId"), "operator": _serialize_operator(existing)}

        now = datetime.now(timezone.utc)
        operator_id = str(uuid.uuid4())
        doc = {
            "operatorId": operator_id,
            "email": body.email,
            "name": "Autocinema",
            "websiteUrl": "http://84.247.180.192:8000",
            "runtimeEndpoint": "http://127.0.0.1:5060/act",
            "runtimeType": "replay",
            "status": "ready",
            "trainingStatus": "verified",
            "harvester": "Automata Operator",
            "tasks": AUTOCINEMA_TASKS,
            "trajectories": [
                {"name": task["name"], "status": "verified", "source": "bundled_autocinema_seed_templates"}
                for task in AUTOCINEMA_TASKS
            ],
            "successCriteria": "IWA benchmark success for the matched Autocinema task.",
            "createdAt": now,
            "updatedAt": now,
        }
        await operators_collection.insert_one(doc)
        return {"success": True, "operatorId": operator_id, "operator": _serialize_operator(doc)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
