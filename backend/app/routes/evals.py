import logging
from datetime import datetime, timezone
from typing import Any, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import (
    agents_collection,
    benchmark_tasks_collection,
    benchmarks_collection,
    eval_runs_collection,
    evals_collection,
)
from app.services.eval_judge import judge_eval_run

logger = logging.getLogger(__name__)
router = APIRouter()


class EvalCreateRequest(BaseModel):
    email: str
    prompt: str
    initialUrl: str = ""


class RunCreateRequest(BaseModel):
    sessionId: str = ""
    agentId: str = ""
    agentName: str = ""


class BenchmarkRunCreateRequest(BaseModel):
    sessionId: str = ""
    agentId: str = ""
    agentName: str = ""


class RunUpdateRequest(BaseModel):
    label: str | None = None
    actions: List[Any] | None = None
    sessionId: str | None = None
    screenshots: List[str] | None = None


class JudgeRunRequest(BaseModel):
    userContext: dict[str, Any] = {}
    apply: bool = True


async def _agent_name(agent_id: str, fallback: str = "") -> str:
    if not agent_id:
        return fallback or "Autoppia Agent"
    doc = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0, "name": 1})
    return str((doc or {}).get("name") or fallback or "Custom Agent")


def _task_to_eval(task: dict[str, Any], benchmark: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    benchmark_doc = benchmark or {}
    return {
        "evalId": task.get("taskId", ""),
        "taskId": task.get("taskId", ""),
        "email": task.get("email", ""),
        "companyId": task.get("companyId", ""),
        "prompt": task.get("prompt", ""),
        "initialUrl": metadata.get("startUrl") or metadata.get("iwaStartUrl") or benchmark_doc.get("websiteUrl") or "",
        "benchmarkId": task.get("benchmarkId", ""),
        "benchmarkName": benchmark_doc.get("name") or task.get("benchmarkName") or "Benchmark",
        "agentId": task.get("agentId", ""),
        "agentName": benchmark_doc.get("agentName", ""),
        "agentTaskName": task.get("taskName") or task.get("name") or "",
        "successCriteria": task.get("successCriteria", ""),
        "status": task.get("status", ""),
        "source": task.get("source", "benchmark_task"),
        "createdAt": task.get("createdAt"),
    }


async def _benchmark_task_eval(eval_id: str) -> dict[str, Any] | None:
    task = await benchmark_tasks_collection.find_one({"taskId": eval_id}, {"_id": 0})
    if not task:
        return None
    benchmark = await benchmarks_collection.find_one({"benchmarkId": task.get("benchmarkId", "")}, {"_id": 0}) or {}
    return _task_to_eval(task, benchmark)


# ── Eval (task) endpoints ──


@router.get("/evals")
async def list_evals(email: str, companyId: str = ""):
    legacy_query: dict[str, Any] = {"email": email}
    if companyId:
        legacy_query["companyId"] = companyId
    cursor = evals_collection.find(legacy_query, {"_id": 0}).sort("createdAt", -1)
    evals = await cursor.to_list(length=500)

    task_query: dict[str, Any] = {"email": email}
    if companyId:
        task_query["companyId"] = companyId
    task_cursor = benchmark_tasks_collection.find(task_query, {"_id": 0}).sort("createdAt", -1)
    tasks = await task_cursor.to_list(length=500)
    benchmark_ids = sorted({str(task.get("benchmarkId") or "") for task in tasks if task.get("benchmarkId")})
    benchmark_docs = {}
    if benchmark_ids:
        docs = await benchmarks_collection.find({"benchmarkId": {"$in": benchmark_ids}}, {"_id": 0}).to_list(length=500)
        benchmark_docs = {doc.get("benchmarkId"): doc for doc in docs}
    task_evals = [_task_to_eval(task, benchmark_docs.get(task.get("benchmarkId"))) for task in tasks]
    return {"evals": [*task_evals, *evals]}


@router.get("/eval-runs")
async def list_all_runs(email: str, companyId: str = ""):
    eval_query: dict[str, Any] = {"email": email}
    if companyId:
        eval_query["companyId"] = companyId
    eval_cursor = evals_collection.find(eval_query, {"_id": 0})
    evals = await eval_cursor.to_list(length=500)
    task_query: dict[str, Any] = {"email": email}
    if companyId:
        task_query["companyId"] = companyId
    tasks = await benchmark_tasks_collection.find(task_query, {"_id": 0}).to_list(length=500)
    benchmark_ids = sorted({str(task.get("benchmarkId") or "") for task in tasks if task.get("benchmarkId")})
    benchmark_docs = {}
    if benchmark_ids:
        docs = await benchmarks_collection.find({"benchmarkId": {"$in": benchmark_ids}}, {"_id": 0}).to_list(length=500)
        benchmark_docs = {doc.get("benchmarkId"): doc for doc in docs}
    task_evals = [_task_to_eval(task, benchmark_docs.get(task.get("benchmarkId"))) for task in tasks]
    evals = [*task_evals, *evals]
    eval_by_id = {ev.get("evalId"): ev for ev in evals}
    if not eval_by_id:
        return {"runs": []}

    run_cursor = eval_runs_collection.find(
        {"evalId": {"$in": list(eval_by_id.keys())}},
        {"_id": 0, "actions": 0},
    ).sort("createdAt", -1)
    runs = await run_cursor.to_list(length=1000)
    for run in runs:
        ev = eval_by_id.get(run.get("evalId"), {})
        run["prompt"] = ev.get("prompt", "")
        run["initialUrl"] = ev.get("initialUrl", "")
        run["benchmarkId"] = ev.get("benchmarkId", ev.get("agentId", ""))
        run["benchmarkName"] = ev.get("benchmarkName", ev.get("agentName", ""))
        run["agentId"] = run.get("agentId", "")
        run["agentName"] = run.get("agentName", "")
        run["agentTaskName"] = ev.get("agentTaskName", "")
    return {"runs": runs}


@router.post("/benchmarks/{benchmark_id}/runs")
async def create_benchmark_run(benchmark_id: str, body: BenchmarkRunCreateRequest):
    eval_cursor = evals_collection.find(
        {
            "$or": [
                {"benchmarkId": benchmark_id},
                {"agentId": benchmark_id},
            ]
        },
        {"_id": 0},
    ).sort("createdAt", 1)
    evals = await eval_cursor.to_list(length=200)
    if not evals:
        task_cursor = benchmark_tasks_collection.find({"benchmarkId": benchmark_id}, {"_id": 0}).sort("createdAt", 1)
        tasks = await task_cursor.to_list(length=200)
        benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0}) or {}
        evals = [_task_to_eval(task, benchmark) for task in tasks]
    if not evals:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    benchmark_run_id = str(uuid4())
    created = []
    now = datetime.now(timezone.utc).isoformat()
    selected_agent_id = str(body.agentId or "")
    selected_agent_name = await _agent_name(selected_agent_id, body.agentName)
    for ev in evals:
        run_id = str(uuid4())
        doc = {
            "runId": run_id,
            "benchmarkRunId": benchmark_run_id,
            "evalId": ev.get("evalId", ""),
            "email": ev.get("email", ""),
            "benchmarkId": ev.get("benchmarkId", ev.get("agentId", "")),
            "benchmarkName": ev.get("benchmarkName", ev.get("agentName", "")),
            "agentId": selected_agent_id,
            "agentName": selected_agent_name,
            "agentTaskName": ev.get("agentTaskName", ""),
            "sessionId": body.sessionId,
            "actions": [],
            "label": "pending",
            "screenshots": [],
            "createdAt": now,
        }
        await eval_runs_collection.insert_one(doc)
        created.append(
            {
                "runId": run_id,
                "evalId": ev.get("evalId", ""),
                "prompt": ev.get("prompt", ""),
                "initialUrl": ev.get("initialUrl", ""),
                "agentTaskName": ev.get("agentTaskName", ""),
            }
        )
    return {"success": True, "benchmarkRunId": benchmark_run_id, "runs": created}


@router.get("/evals/{eval_id}")
async def get_eval(eval_id: str):
    doc = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not doc:
        doc = await _benchmark_task_eval(eval_id)
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
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not ev:
        ev = await _benchmark_task_eval(eval_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Eval not found")

    run_id = str(uuid4())
    selected_agent_id = str(body.agentId or "")
    selected_agent_name = await _agent_name(selected_agent_id, body.agentName)
    doc = {
        "runId": run_id,
        "evalId": eval_id,
        "benchmarkRunId": "",
        "email": ev.get("email", ""),
        "benchmarkId": ev.get("benchmarkId", ev.get("agentId", "")),
        "benchmarkName": ev.get("benchmarkName", ev.get("agentName", "")),
        "agentId": selected_agent_id,
        "agentName": selected_agent_name,
        "agentTaskName": ev.get("agentTaskName", ""),
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


@router.post("/evals/{eval_id}/runs/{run_id}/judge")
async def judge_run(eval_id: str, run_id: str, body: JudgeRunRequest):
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not ev:
        ev = await _benchmark_task_eval(eval_id)
    run = await eval_runs_collection.find_one({"runId": run_id, "evalId": eval_id}, {"_id": 0})
    if not ev or not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    judgement = await judge_eval_run(run=run, eval_doc=ev, user_context=body.userContext)
    if body.apply:
        await eval_runs_collection.update_one(
            {"runId": run_id, "evalId": eval_id},
            {"$set": {"label": judgement["label"], "judge": judgement}},
        )
    return {"success": True, "judgement": judgement}


@router.delete("/evals/{eval_id}/runs/{run_id}")
async def delete_run(eval_id: str, run_id: str):
    result = await eval_runs_collection.delete_one({"runId": run_id, "evalId": eval_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True}
