from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from app.database import (
    validator_agent_runs_collection,
    validator_evaluations_collection,
    validator_round_tasks_collection,
    validator_rounds_collection,
    validator_task_logs_collection,
)

router = APIRouter(prefix="/api/v1")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round_numbers(validator_round_id: str | None) -> tuple[int | None, int | None]:
    if not validator_round_id:
        return None, None
    match = re.match(r"^validator_round_(\d+)_(\d+)_.*$", validator_round_id)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return json.loads(json.dumps(value, default=str))


async def _request_payload(request: Request) -> Any:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload: dict[str, Any] = {}
        for key, value in form.multi_items():
            if hasattr(value, "read"):
                raw = await value.read()
                payload[key] = {"filename": getattr(value, "filename", key), "size": len(raw)}
                continue
            try:
                payload[key] = json.loads(str(value))
            except Exception:
                payload[key] = str(value)
        return payload
    try:
        return await request.json()
    except Exception:
        return {}


def _response(**data: Any) -> dict[str, Any]:
    return {"success": True, **data}


@router.post("/validator-rounds/auth-check")
async def auth_check(request: Request):
    return _response(
        authenticated=True,
        validator_hotkey=request.headers.get("x-validator-hotkey", ""),
    )


@router.post("/validator-rounds/runtime-config")
async def sync_runtime_config(request: Request):
    payload = _jsonable(await _request_payload(request))
    validator_identity = payload.get("validator_identity") if isinstance(payload, dict) else {}
    hotkey = validator_identity.get("hotkey") if isinstance(validator_identity, dict) else ""
    doc_id = f"runtime_config:{hotkey or 'unknown'}"
    await validator_rounds_collection.update_one(
        {"validator_round_id": doc_id},
        {"$set": {"validator_round_id": doc_id, "kind": "runtime_config", "payload": payload, "updatedAt": _now()}},
        upsert=True,
    )
    return _response(id=doc_id)


@router.post("/validator-rounds/start")
async def start_round(request: Request, force: bool = False):
    payload = _jsonable(await _request_payload(request))
    validator_round = payload.get("validator_round") if isinstance(payload, dict) else {}
    validator_round_id = str((validator_round or {}).get("validator_round_id") or "")
    season_number = (validator_round or {}).get("season_number")
    round_number = (validator_round or {}).get("round_number_in_season")
    if season_number is None or round_number is None:
        parsed_season, parsed_round = _round_numbers(validator_round_id)
        season_number = season_number if season_number is not None else parsed_season
        round_number = round_number if round_number is not None else parsed_round
    doc = {
        "validator_round_id": validator_round_id,
        "season_number": season_number,
        "round_number_in_season": round_number,
        "validator_identity": payload.get("validator_identity") if isinstance(payload, dict) else {},
        "validator_round": validator_round,
        "validator_snapshot": payload.get("validator_snapshot") if isinstance(payload, dict) else {},
        "force": force,
        "status": "started",
        "updatedAt": _now(),
    }
    await validator_rounds_collection.update_one(
        {"validator_round_id": validator_round_id},
        {"$set": doc, "$setOnInsert": {"createdAt": _now()}},
        upsert=True,
    )
    return _response(validator_round_id=validator_round_id)


@router.post("/validator-rounds/{validator_round_id}/tasks")
async def set_tasks(validator_round_id: str, request: Request, force: bool = False):
    payload = _jsonable(await _request_payload(request))
    tasks = payload.get("tasks") if isinstance(payload, dict) else []
    if not isinstance(tasks, list):
        tasks = []
    now = _now()
    await validator_rounds_collection.update_one(
        {"validator_round_id": validator_round_id},
        {"$set": {"validator_round_id": validator_round_id, "tasks_count": len(tasks), "forceTasks": force, "updatedAt": now}, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or task.get("id") or "")
        await validator_round_tasks_collection.update_one(
            {"validator_round_id": validator_round_id, "task_id": task_id},
            {"$set": {"validator_round_id": validator_round_id, "task_id": task_id, "payload": task, "updatedAt": now}, "$setOnInsert": {"createdAt": now}},
            upsert=True,
        )
    return _response(validator_round_id=validator_round_id, tasks=len(tasks))


@router.post("/validator-rounds/{validator_round_id}/agent-runs/start")
async def start_agent_run(validator_round_id: str, request: Request, force: bool = False):
    payload = _jsonable(await _request_payload(request))
    agent_run = payload.get("agent_run") if isinstance(payload, dict) else {}
    agent_run_id = str((agent_run or {}).get("agent_run_id") or "")
    now = _now()
    await validator_agent_runs_collection.update_one(
        {"agent_run_id": agent_run_id},
        {
            "$set": {
                "validator_round_id": validator_round_id,
                "agent_run_id": agent_run_id,
                "agent_run": agent_run,
                "miner_identity": payload.get("miner_identity") if isinstance(payload, dict) else {},
                "miner_snapshot": payload.get("miner_snapshot") if isinstance(payload, dict) else {},
                "force": force,
                "status": "started",
                "updatedAt": now,
            },
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
    )
    return _response(validator_round_id=validator_round_id, agent_run_id=agent_run_id)


async def _store_evaluation(validator_round_id: str, agent_run_id: str, payload: dict[str, Any]) -> str:
    evaluation = payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else {}
    evaluation_result = payload.get("evaluation_result") if isinstance(payload.get("evaluation_result"), dict) else {}
    task_solution = payload.get("task_solution") if isinstance(payload.get("task_solution"), dict) else {}
    evaluation_id = str(evaluation.get("evaluation_id") or evaluation_result.get("evaluation_id") or "")
    task_solution_id = str(task_solution.get("solution_id") or evaluation.get("task_solution_id") or evaluation_result.get("task_solution_id") or "")
    key = evaluation_id or task_solution_id or f"{validator_round_id}:{agent_run_id}:{_now()}"
    await validator_evaluations_collection.update_one(
        {"evaluation_key": key},
        {
            "$set": {
                "evaluation_key": key,
                "evaluation_id": evaluation_id,
                "task_solution_id": task_solution_id,
                "validator_round_id": validator_round_id,
                "agent_run_id": agent_run_id,
                "payload": payload,
                "updatedAt": _now(),
            },
            "$setOnInsert": {"createdAt": _now()},
        },
        upsert=True,
    )
    return key


@router.post("/validator-rounds/{validator_round_id}/agent-runs/{agent_run_id}/evaluations")
async def add_evaluation(validator_round_id: str, agent_run_id: str, request: Request):
    payload = _jsonable(await _request_payload(request))
    key = await _store_evaluation(validator_round_id, agent_run_id, payload if isinstance(payload, dict) else {"payload": payload})
    return _response(validator_round_id=validator_round_id, agent_run_id=agent_run_id, evaluation_key=key)


@router.post("/validator-rounds/{validator_round_id}/agent-runs/{agent_run_id}/evaluations/batch")
async def add_evaluations_batch(validator_round_id: str, agent_run_id: str, request: Request):
    payload = _jsonable(await _request_payload(request))
    evaluations = payload if isinstance(payload, list) else payload.get("evaluations", []) if isinstance(payload, dict) else []
    if not isinstance(evaluations, list):
        evaluations = []
    keys = []
    for evaluation_payload in evaluations:
        if isinstance(evaluation_payload, dict):
            keys.append(await _store_evaluation(validator_round_id, agent_run_id, evaluation_payload))
    created = len(keys)
    return _response(
        validator_round_id=validator_round_id,
        agent_run_id=agent_run_id,
        created=created,
        evaluations_created=created,
        message=f"Batch evaluations processed: {created} created",
        evaluation_keys=keys,
    )


@router.post("/validator-rounds/{validator_round_id}/finish")
async def finish_round(validator_round_id: str, request: Request):
    payload = _jsonable(await _request_payload(request))
    await validator_rounds_collection.update_one(
        {"validator_round_id": validator_round_id},
        {"$set": {"finish": payload, "status": "finished", "updatedAt": _now()}, "$setOnInsert": {"createdAt": _now()}},
        upsert=True,
    )
    return _response(validator_round_id=validator_round_id, status="finished")


@router.post("/validator-rounds/{validator_round_id}/round-log")
async def upload_round_log(validator_round_id: str, request: Request):
    payload = _jsonable(await _request_payload(request))
    content = payload.get("content", "") if isinstance(payload, dict) else ""
    object_key = f"validator-rounds/{validator_round_id}/round.log"
    await validator_rounds_collection.update_one(
        {"validator_round_id": validator_round_id},
        {"$set": {"roundLog": {"objectKey": object_key, "size": len(str(content))}, "updatedAt": _now()}, "$setOnInsert": {"createdAt": _now()}},
        upsert=True,
    )
    return _response(data={"objectKey": object_key, "url": f"local://{object_key}"})


@router.post("/task-logs")
async def upload_task_log(request: Request):
    payload = _jsonable(await _request_payload(request))
    validator_round_id = str(payload.get("validator_round_id") or "") if isinstance(payload, dict) else ""
    task_id = str(payload.get("task_id") or "") if isinstance(payload, dict) else ""
    object_key = f"task-logs/{validator_round_id or 'unknown'}/{task_id or 'unknown'}.json"
    await validator_task_logs_collection.insert_one(
        {"validator_round_id": validator_round_id, "task_id": task_id, "payload": payload, "objectKey": object_key, "createdAt": _now()}
    )
    return _response(data={"objectKey": object_key, "url": f"local://{object_key}"})


@router.post("/evaluations/{evaluation_id}/gif")
async def upload_evaluation_gif(evaluation_id: str, request: Request):
    form = await request.form()
    size = 0
    filename = f"{evaluation_id}.gif"
    for _key, value in form.multi_items():
        if hasattr(value, "read"):
            raw = await value.read()
            size += len(raw)
            filename = getattr(value, "filename", filename) or filename
    object_key = f"evaluation-gifs/{evaluation_id}/{filename}"
    await validator_evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {"$set": {"gif": {"objectKey": object_key, "size": size}, "updatedAt": _now()}},
        upsert=True,
    )
    return _response(data={"gifUrl": f"local://{object_key}", "objectKey": object_key})
