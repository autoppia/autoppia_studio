import uuid
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import (
    agent_creation_jobs_collection,
    benchmark_tasks_collection,
    harvester_runs_collection,
    connectors_collection,
    agents_collection,
    trajectories_collection,
)
from app.services.agent_harvesters import get_agent_harvester, get_official_agent_harvester, list_agent_harvesters
from app.services.capability_discovery import list_capability_discoverers
from app.services.queue import enqueue_job
from app.services.skills import approve_trajectory_as_skill
from app.services.trajectory_judges import build_trajectory_judge_context, get_trajectory_judge, list_trajectory_judges

router = APIRouter()

SETUP_STEPS = [
    ("validate_connectors", "Validate connectors"),
    ("run_harvester", "Run harvester for these tasks"),
    ("review_trajectories", "Review trajectories"),
    ("approve_trajectories", "Approve successful trajectories"),
    ("build_skills", "Convert approved trajectories into skills"),
    ("run_benchmark", "Run benchmark"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_steps() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "status": "pending",
            "message": "",
            "updatedAt": "",
        }
        for key, label in SETUP_STEPS
    ]


def _set_step(steps: list[dict[str, Any]], key: str, status: str, message: str = "") -> list[dict[str, Any]]:
    now = _now()
    next_steps = []
    for step in steps:
        if step.get("key") == key:
            next_steps.append({**step, "status": status, "message": message, "updatedAt": now})
        else:
            next_steps.append(step)
    return next_steps


async def ensure_agent_creation_job(agent_config: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(agent_config.get("agentId") or "")
    if not agent_id:
        raise HTTPException(status_code=400, detail="Agent id is required")
    existing = await agent_creation_jobs_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if existing:
        return existing
    now = _now()
    job = {
        "jobId": str(uuid.uuid4()),
        "agentId": agent_id,
        "companyId": agent_config.get("companyId", ""),
        "email": agent_config.get("email", ""),
        "status": "draft",
        "currentStep": "validate_connectors",
        "steps": _new_steps(),
        "events": [
            {
                "type": "created",
                "message": "Agent creation setup job created.",
                "createdAt": now,
            }
        ],
        "createdAt": now,
        "updatedAt": now,
    }
    await agent_creation_jobs_collection.insert_one(job)
    job.pop("_id", None)
    return job


async def _agent_config(agent_id: str) -> dict[str, Any]:
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_config


async def _update_job(job_id: str, update: dict[str, Any], event: str | None = None) -> dict[str, Any]:
    now = _now()
    update["updatedAt"] = now
    mutation: dict[str, Any] = {"$set": update}
    if event:
        mutation["$push"] = {"events": {"type": "progress", "message": event, "createdAt": now}}
    await agent_creation_jobs_collection.update_one({"jobId": job_id}, mutation)
    return await agent_creation_jobs_collection.find_one({"jobId": job_id}, {"_id": 0}) or {}


async def validate_agent_creation(agent_id: str) -> dict[str, Any]:
    agent_config = await _agent_config(agent_id)
    job = await ensure_agent_creation_job(agent_config)
    steps = list(job.get("steps") or _new_steps())
    company_id = str(agent_config.get("companyId") or "")
    connectors = []
    if company_id:
        cursor = connectors_collection.find({"companyId": company_id}, {"_id": 0})
        connectors = await cursor.to_list(length=500)
    blocking = [
        connector
        for connector in connectors
        if connector.get("status") in {"needs_auth", "not_connected"}
        and connector.get("type") not in {"web", "knowledge"}
    ]
    if blocking:
        names = ", ".join(str(item.get("name") or "Connector") for item in blocking)
        steps = _set_step(
            steps,
            "validate_connectors",
            "ready",
            f"Some connector-backed tasks need credentials before execution: {names}. Web/knowledge tasks can still be harvested.",
        )
    else:
        steps = _set_step(steps, "validate_connectors", "done", "Connectors are ready enough to start harvesting.")

    steps = _set_step(steps, "run_harvester", "ready", "Ready to start the Automata Harvester.")
    await agents_collection.update_one(
        {"agentId": agent_id},
        {"$set": {"trainingStatus": "ready_for_harvest", "status": "training", "updatedAt": _now()}},
    )
    return await _update_job(
        job["jobId"],
        {"status": "ready_for_harvest", "currentStep": "run_harvester", "steps": steps},
        f"Connector validation passed with pending credentials: {names}" if blocking else "Connector validation passed.",
    )


async def start_harvester(agent_id: str) -> dict[str, Any]:
    agent_config = await _agent_config(agent_id)
    job = await ensure_agent_creation_job(agent_config)
    if job.get("status") in {"draft", "needs_credentials"}:
        job = await validate_agent_creation(agent_id)
    if job.get("status") == "needs_credentials":
        return job

    steps = list(job.get("steps") or _new_steps())
    harvester = get_official_agent_harvester()
    steps = _set_step(steps, "run_harvester", "in_progress", f"{harvester.name} requested for pending tasks.")
    run_id = str(uuid.uuid4())
    await harvester_runs_collection.insert_one(
        {
            "harvesterRunId": run_id,
            "jobId": job["jobId"],
            "runKind": "agent_creation",
            "agentId": agent_id,
            "companyId": agent_config.get("companyId", ""),
            "email": agent_config.get("email", ""),
            "harvesterType": harvester.name,
            "status": "queued",
            "logs": [f"{harvester.name} queued."],
            "errors": [],
            "createdAt": _now(),
            "updatedAt": _now(),
        }
    )
    task_queue_update = {
        "$set": {
            "status": "harvester_pending",
            "updatedAt": _now(),
            "harvester": {
                "adapter": harvester.name,
                "status": "queued",
                "message": f"{harvester.name} harvester is queued.",
            },
        }
    }
    await benchmark_tasks_collection.update_many(
        {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft"]}},
        task_queue_update,
    )
    await trajectories_collection.update_many(
        {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft"]}},
        {
            "$set": {
                "status": "harvester_pending",
                "source": "automata_harvester",
                "updatedAt": _now(),
                "harvester": {
                    "adapter": harvester.name,
                    "status": "queued",
                    "message": f"{harvester.name} harvester is queued.",
                },
            }
        },
    )
    steps = _set_step(
        steps,
        "run_harvester",
        "in_progress",
        f"{harvester.name} harvester is running in the background.",
    )
    steps = _set_step(steps, "review_trajectories", "pending", "Waiting for successful harvested trajectories.")
    await agents_collection.update_one(
        {"agentId": agent_id},
        {"$set": {"trainingStatus": "harvesting", "status": "training", "updatedAt": _now()}},
    )
    updated_job = await _update_job(
        job["jobId"],
        {"status": "harvesting", "currentStep": "run_harvester", "steps": steps},
        f"Automata Harvester started with {harvester.name}.",
    )
    await enqueue_job(
        "agent_harvest",
        {
            "agentId": agent_id,
            "jobId": job["jobId"],
            "harvesterRunId": run_id,
            "harvesterName": harvester.name,
        },
        dedupe_key=f"agent_harvest:{agent_id}:{run_id}",
        max_attempts=1,
    )
    return updated_job


async def _run_harvester_background(*, agent_id: str, job_id: str, harvester_run_id: str, harvester_name: str) -> None:
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent_config:
        return
    now = _now()
    try:
        await harvester_runs_collection.update_one(
            {"harvesterRunId": harvester_run_id},
            {"$set": {"status": "running", "startedAt": now, "updatedAt": now}, "$push": {"logs": f"{harvester_name} started."}},
        )
        result = await get_agent_harvester(harvester_name).harvest(agent_config)
        auto_promoted = await _auto_promote_harvested_trajectories(agent_id)
        remaining = await trajectories_collection.count_documents(
            {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending", "harvesting"]}}
        )
        harvested = await trajectories_collection.count_documents({"agentId": agent_id, "status": "harvested"})
        approved = await trajectories_collection.count_documents({"agentId": agent_id, "status": "approved"})
        job = await agent_creation_jobs_collection.find_one({"jobId": job_id}, {"_id": 0}) or {}
        steps = []
        for step in job.get("steps", _new_steps()):
            key = step.get("key")
            if key == "run_harvester":
                status = "done" if harvested or approved else "blocked"
                message = f"Harvested {harvested + approved} trajectory candidates." if harvested or approved else "No successful trajectory candidates yet."
                steps.append({**step, "status": status, "message": message, "updatedAt": now})
            elif key == "review_trajectories" and harvested:
                steps.append({**step, "status": "ready", "message": "Review harvested trajectories that LLMJudge could not approve automatically.", "updatedAt": now})
            elif key in {"review_trajectories", "approve_trajectories", "build_skills"} and approved and not harvested:
                steps.append({**step, "status": "done", "message": f"LLMJudge approved {auto_promoted} trajectories and built skills.", "updatedAt": now})
            elif key == "run_benchmark" and approved and not harvested:
                steps.append({**step, "status": "ready", "message": "Ready to run benchmark against this agent.", "updatedAt": now})
            else:
                steps.append(step)
        status = "awaiting_review" if harvested else "ready_for_benchmark" if approved else "harvest_failed"
        await agent_creation_jobs_collection.update_one(
            {"jobId": job_id},
            {
                "$set": {
                    "status": status,
                    "currentStep": "review_trajectories" if harvested else "run_benchmark" if approved else "run_harvester",
                    "steps": steps,
                    "updatedAt": _now(),
                },
                "$push": {"events": {"type": "progress", "message": f"Harvester finished: {result['count']} tasks processed, {harvested} awaiting review, {auto_promoted} auto-approved, {remaining} remaining.", "createdAt": _now()}},
            },
        )
        await agents_collection.update_one(
            {"agentId": agent_id},
            {"$set": {"trainingStatus": status, "status": "training", "updatedAt": _now()}},
        )
        await harvester_runs_collection.update_one(
            {"harvesterRunId": harvester_run_id},
            {
                "$set": {
                    "status": "completed" if harvested or approved else "failed",
                    "completedAt": _now(),
                    "updatedAt": _now(),
                    "generatedTrajectories": harvested + approved,
                    "discoveredTools": 0,
                    "generatedSkills": auto_promoted,
                },
                "$push": {"logs": f"Finished: {result.get('count', 0)} tasks processed, {harvested} harvested, {auto_promoted} auto-approved."},
            },
        )
    except Exception as exc:
        job = await agent_creation_jobs_collection.find_one({"jobId": job_id}, {"_id": 0}) or {}
        steps = _set_step(list(job.get("steps") or _new_steps()), "run_harvester", "blocked", str(exc))
        await agent_creation_jobs_collection.update_one(
            {"jobId": job_id},
            {
                "$set": {"status": "harvest_failed", "currentStep": "run_harvester", "steps": steps, "updatedAt": _now()},
                "$push": {"events": {"type": "error", "message": f"Harvester failed: {exc}", "createdAt": _now()}},
            },
        )


async def _auto_promote_harvested_trajectories(agent_id: str, judge_name: str | None = None) -> int:
    enabled = os.getenv("AUTOMATA_AUTO_APPROVE_HARVESTED_SKILLS", os.getenv("AUTOMATA_AUTO_APPROVE_HARVESTED", "true"))
    if enabled.lower() not in {"1", "true", "yes"}:
        return 0
    min_confidence = float(os.getenv("AUTOMATA_AUTO_APPROVE_MIN_CONFIDENCE", "0.75"))
    promoted = 0
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0}) or {}
    judge = get_trajectory_judge(judge_name or agent_config.get("judgeImplementation"))
    cursor = trajectories_collection.find({"agentId": agent_id, "status": "harvested"}, {"_id": 0})
    trajectories = await cursor.to_list(length=100)
    for trajectory in trajectories:
        judgement = await judge.judge(build_trajectory_judge_context(trajectory=trajectory, agent_config=agent_config))
        needs_review = judgement.get("label") != "pass" or float(judgement.get("confidence") or 0) < min_confidence
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory["trajectoryId"]},
            {"$set": {"judge": judgement, "needsHumanReview": needs_review, "updatedAt": _now()}},
        )
        if not needs_review:
            await approve_trajectory_as_skill(trajectory, judge=judgement)
            promoted += 1
    return promoted


@router.get("/agents/{agent_id}/creation-job")
async def get_agent_creation_job(agent_id: str):
    agent_config = await _agent_config(agent_id)
    job = await ensure_agent_creation_job(agent_config)
    return {"job": job}


@router.get("/agent-harvesters")
async def list_available_agent_harvesters():
    return {"harvesters": list_agent_harvesters()}


@router.get("/capability-discoverers")
async def list_available_capability_discoverers():
    return {"discoverers": list_capability_discoverers()}


@router.get("/trajectory-judges")
async def list_available_trajectory_judges():
    return {"judges": list_trajectory_judges()}


@router.post("/agents/{agent_id}/creation-job/validate")
async def validate_agent_creation_job(agent_id: str):
    return {"job": await validate_agent_creation(agent_id)}


@router.post("/agents/{agent_id}/creation-job/harvest")
async def run_agent_creation_harvester(agent_id: str):
    return {"job": await start_harvester(agent_id)}
