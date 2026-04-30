import logging
from datetime import datetime, timezone
from typing import Any, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import evals_collection, eval_runs_collection

logger = logging.getLogger(__name__)
router = APIRouter()


class EvalCreateRequest(BaseModel):
    email: str
    prompt: str
    initialUrl: str = ""


class RunCreateRequest(BaseModel):
    sessionId: str = ""


class RunUpdateRequest(BaseModel):
    label: str | None = None
    actions: List[Any] | None = None
    sessionId: str | None = None
    screenshots: List[str] | None = None


# ── Eval (task) endpoints ──


@router.get("/evals")
async def list_evals(email: str):
    cursor = evals_collection.find(
        {"email": email},
        {"_id": 0},
    ).sort("createdAt", -1)
    evals = await cursor.to_list(length=500)
    return {"evals": evals}


@router.get("/evals/{eval_id}")
async def get_eval(eval_id: str):
    doc = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Eval not found")
    return {"eval": doc}


@router.post("/evals")
async def create_eval(body: EvalCreateRequest):
    eval_id = str(uuid4())
    doc = {
        "evalId": eval_id,
        "email": body.email,
        "prompt": body.prompt,
        "initialUrl": body.initialUrl,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await evals_collection.insert_one(doc)
    return {"success": True, "evalId": eval_id}


@router.delete("/evals/{eval_id}")
async def delete_eval(eval_id: str):
    result = await evals_collection.delete_one({"evalId": eval_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Eval not found")
    # Also delete all runs for this eval
    await eval_runs_collection.delete_many({"evalId": eval_id})
    return {"success": True}


# ── Eval run endpoints ──


@router.get("/evals/{eval_id}/runs")
async def list_runs(eval_id: str):
    cursor = eval_runs_collection.find(
        {"evalId": eval_id},
        {"_id": 0, "actions": 0},
    ).sort("createdAt", -1)
    runs = await cursor.to_list(length=500)
    return {"runs": runs}


@router.post("/evals/{eval_id}/runs")
async def create_run(eval_id: str, body: RunCreateRequest):
    # Verify eval exists
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 1})
    if not ev:
        raise HTTPException(status_code=404, detail="Eval not found")

    run_id = str(uuid4())
    doc = {
        "runId": run_id,
        "evalId": eval_id,
        "sessionId": body.sessionId,
        "actions": [],
        "label": "pending",
        "screenshots": [],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await eval_runs_collection.insert_one(doc)
    return {"success": True, "runId": run_id}


@router.get("/evals/{eval_id}/runs/{run_id}")
async def get_run(eval_id: str, run_id: str):
    doc = await eval_runs_collection.find_one({"runId": run_id, "evalId": eval_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": doc}


@router.put("/evals/{eval_id}/runs/{run_id}")
async def update_run(eval_id: str, run_id: str, body: RunUpdateRequest):
    update = {}
    if body.label is not None:
        if body.label not in ("pass", "fail", "pending"):
            raise HTTPException(status_code=400, detail="Label must be 'pass', 'fail', or 'pending'")
        update["label"] = body.label
    if body.actions is not None:
        update["actions"] = body.actions
    if body.sessionId is not None:
        update["sessionId"] = body.sessionId
    if body.screenshots is not None:
        update["screenshots"] = body.screenshots

    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")

    result = await eval_runs_collection.update_one({"runId": run_id, "evalId": eval_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True}


@router.delete("/evals/{eval_id}/runs/{run_id}")
async def delete_run(eval_id: str, run_id: str):
    result = await eval_runs_collection.delete_one({"runId": run_id, "evalId": eval_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True}
