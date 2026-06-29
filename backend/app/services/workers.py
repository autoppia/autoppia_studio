from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database import worker_locks_collection
from app.services.queue import claim_next_job, complete_job, enqueue_job, fail_job

logger = logging.getLogger(__name__)
WORKER_OWNER_ID = os.getenv("AUTOMATA_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def acquire_worker_lease(lock_id: str, *, ttl_seconds: int = 90) -> bool:
    now = _now()
    expires_at = now + timedelta(seconds=max(10, ttl_seconds))
    try:
        doc = await worker_locks_collection.find_one_and_update(
            {
                "lockId": lock_id,
                "$or": [
                    {"expiresAt": {"$lte": now}},
                    {"ownerId": WORKER_OWNER_ID},
                    {"expiresAt": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "lockId": lock_id,
                    "ownerId": WORKER_OWNER_ID,
                    "expiresAt": expires_at,
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        doc = await worker_locks_collection.find_one({"lockId": lock_id}, {"_id": 0})
    return bool(doc and doc.get("ownerId") == WORKER_OWNER_ID)


async def leased_loop(
    *,
    lock_id: str,
    interval_seconds: int,
    ttl_seconds: int,
    tick: Callable[[], Awaitable[object]],
) -> None:
    while True:
        try:
            if await acquire_worker_lease(lock_id, ttl_seconds=ttl_seconds):
                await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker loop failed", extra={"lockId": lock_id, "ownerId": WORKER_OWNER_ID})
        await asyncio.sleep(interval_seconds)


async def scheduled_work_worker_loop() -> None:
    from app.routes.work_items import run_due_scheduled_work_items_once

    await leased_loop(
        lock_id="scheduled_work",
        interval_seconds=60,
        ttl_seconds=90,
        tick=run_due_scheduled_work_items_once,
    )


async def notification_cleanup_worker_loop() -> None:
    from app.routes.notifications import cleanup_notifications

    interval_seconds = max(3600, int(os.getenv("AUTOMATA_NOTIFICATION_CLEANUP_INTERVAL_SECONDS", "86400") or "86400"))
    days = max(1, int(os.getenv("AUTOMATA_NOTIFICATION_RETENTION_DAYS", "30") or "30"))
    max_per_user = max(50, int(os.getenv("AUTOMATA_NOTIFICATION_MAX_PER_USER", "500") or "500"))

    async def tick() -> object:
        return await cleanup_notifications(read_older_than_days=days, max_per_user=max_per_user)

    await leased_loop(
        lock_id="notification_cleanup",
        interval_seconds=interval_seconds,
        ttl_seconds=max(3600, min(interval_seconds * 2, 172800)),
        tick=tick,
    )


async def _enqueue_company_knowledge_index_jobs(company_harvest: dict) -> list[dict]:
    dev_summary = company_harvest.get("devSummary") if isinstance(company_harvest.get("devSummary"), dict) else {}
    document_ids = [str(item) for item in dev_summary.get("knowledgeDocumentIds") or [] if item]
    jobs = []
    for document_id in document_ids:
        jobs.append(
            await enqueue_job(
                "knowledge_index",
                {"documentId": document_id},
                dedupe_key=f"knowledge_index:{document_id}",
                max_attempts=3,
            )
        )
    return jobs


def _company_harvest_allows_task_autosolve(company_harvest: dict) -> bool:
    next_action = company_harvest.get("nextAction") if isinstance(company_harvest.get("nextAction"), dict) else {}
    if str(next_action.get("kind") or "") == "implement_connectors":
        return False
    if str(company_harvest.get("status") or "") == "needs_user_input":
        return False
    return True


async def execute_job(job: dict) -> dict:
    job_type = str(job.get("type") or "")
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    if job_type == "work_run":
        from app.routes.work_items import _run_work_item

        await _run_work_item(str(payload.get("workItemId") or ""), str(payload.get("runId") or ""))
        return {"ok": True}
    if job_type == "knowledge_index":
        from app.database import knowledge_documents_collection
        from app.services.knowledge_index import index_knowledge_document

        document_id = str(payload.get("documentId") or "")
        doc = await knowledge_documents_collection.find_one({"documentId": document_id}, {"_id": 0})
        if not doc:
            raise RuntimeError("Knowledge document not found")
        result = await index_knowledge_document(doc)
        await knowledge_documents_collection.update_one(
            {"documentId": document_id},
            {"$set": {"status": "indexed", "index": result, "indexError": "", "updatedAt": datetime.now(timezone.utc).isoformat()}},
        )
        return result
    if job_type == "agent_harvest":
        from app.routes.agent_creation import _run_harvester_background

        await _run_harvester_background(
            agent_id=str(payload.get("agentId") or ""),
            job_id=str(payload.get("jobId") or ""),
            harvester_run_id=str(payload.get("harvesterRunId") or ""),
            harvester_name=str(payload.get("harvesterName") or "autoppia_harvester"),
        )
        return {"ok": True}
    if job_type == "company_harvest":
        from app.services.company_harvester import process_company_harvest_run, record_company_harvest_results

        result = await process_company_harvest_run(str(payload.get("runId") or ""))
        knowledge_index_jobs = []
        if payload.get("autoIndexKnowledge", True):
            knowledge_index_jobs = await _enqueue_company_knowledge_index_jobs(result)
        task_harvest = None
        promotion = None
        agent_build = None
        benchmark_id = str((result.get("normalSummary") or {}).get("benchmarkId") or (result.get("nextAction") or {}).get("benchmarkId") or "")
        autosolve_blocked = payload.get("autoSolveTasks") and not _company_harvest_allows_task_autosolve(result)
        downstream_blocked = False
        if payload.get("autoSolveTasks") and not autosolve_blocked:
            from app.services.task_harvester import harvest_benchmark_tasks, task_harvest_has_implementation_gaps

            if benchmark_id:
                task_harvest = await harvest_benchmark_tasks(benchmark_id, harvester_name=str(payload.get("harvesterName") or ""))
                downstream_blocked = task_harvest_has_implementation_gaps(task_harvest)
                if payload.get("autoPromoteSkills") and not downstream_blocked:
                    from app.services.task_harvester import judge_and_promote_benchmark_trajectories

                    promotion = await judge_and_promote_benchmark_trajectories(
                        benchmark_id,
                        judge_name=str(payload.get("judgeName") or "rules"),
                    )
        if payload.get("buildAgents") and not downstream_blocked:
            from app.services.agent_builder import build_company_agents

            agent_build = await build_company_agents(
                email=str(result.get("email") or payload.get("email") or ""),
                company_id=str(result.get("companyId") or payload.get("companyId") or ""),
                company_name=str(payload.get("companyName") or ""),
                benchmark_id=benchmark_id,
                runtime_kinds=[str(item) for item in payload.get("runtimeKinds") or [] if item],
                runtime_profiles=payload.get("runtimeProfiles") if isinstance(payload.get("runtimeProfiles"), dict) else {},
            )
        company_harvest = await record_company_harvest_results(
            str(payload.get("runId") or ""),
            knowledge_index_jobs=knowledge_index_jobs,
            task_harvest=task_harvest,
            promotion=promotion,
            agent_build=agent_build,
        )
        response = {"companyHarvest": company_harvest, "knowledgeIndexJobs": knowledge_index_jobs}
        blocked_actions = []
        if autosolve_blocked:
            blocked_actions.append(
                {
                    "kind": "auto_solve_tasks",
                    "reason": "company_harvest_next_action_requires_connector_implementation",
                    "nextAction": result.get("nextAction") if isinstance(result.get("nextAction"), dict) else {},
                }
            )
        if downstream_blocked:
            blocked_actions.append(
                {
                    "kind": "auto_promote_or_build_agents",
                    "reason": "task_harvest_requires_connector_implementation",
                    "benchmarkId": benchmark_id,
                }
            )
        if blocked_actions:
            response["blockedActions"] = blocked_actions
        if task_harvest is not None:
            response["taskHarvest"] = task_harvest
        if promotion is not None:
            response["promotion"] = promotion
        if agent_build is not None:
            response["agentBuild"] = agent_build
        return response
    if job_type == "task_harvest":
        from app.services.task_harvester import harvest_benchmark_tasks, harvest_task, judge_and_promote_benchmark_trajectories, task_harvest_has_implementation_gaps

        task_id = str(payload.get("taskId") or "")
        if task_id:
            harvest = await harvest_task(task_id, harvester_name=str(payload.get("harvesterName") or ""))
            if payload.get("promoteSkills"):
                if task_harvest_has_implementation_gaps(harvest):
                    return {
                        "harvest": harvest,
                        "blockedActions": [
                            {
                                "kind": "promote_or_build_agents",
                                "reason": "task_harvest_requires_connector_implementation",
                                "benchmarkId": str(harvest.get("benchmarkId") or payload.get("benchmarkId") or ""),
                            }
                        ],
                    }
                promotion = await judge_and_promote_benchmark_trajectories(
                    str(harvest.get("benchmarkId") or payload.get("benchmarkId") or ""),
                    task_ids=[task_id],
                    judge_name=str(payload.get("judgeName") or "rules"),
                    limit=int(payload.get("limit") or 25),
                )
                response = {"harvest": harvest, "promotion": promotion}
                if payload.get("buildAgents"):
                    from app.services.agent_builder import build_company_agents

                    response["agentBuild"] = await build_company_agents(
                        email=str(payload.get("email") or ""),
                        company_id=str(payload.get("companyId") or ""),
                        company_name=str(payload.get("companyName") or ""),
                        benchmark_id=str(harvest.get("benchmarkId") or payload.get("benchmarkId") or ""),
                        runtime_kinds=[str(item) for item in payload.get("runtimeKinds") or [] if item],
                        runtime_profiles=payload.get("runtimeProfiles") if isinstance(payload.get("runtimeProfiles"), dict) else {},
                    )
                return response
            return harvest
        harvest = await harvest_benchmark_tasks(
            str(payload.get("benchmarkId") or ""),
            harvester_name=str(payload.get("harvesterName") or ""),
            task_ids=[str(item) for item in payload.get("taskIds") or [] if item],
            limit=int(payload.get("limit") or 25),
        )
        if payload.get("promoteSkills"):
            if task_harvest_has_implementation_gaps(harvest):
                return {
                    "harvest": harvest,
                    "blockedActions": [
                        {
                            "kind": "promote_or_build_agents",
                            "reason": "task_harvest_requires_connector_implementation",
                            "benchmarkId": str(payload.get("benchmarkId") or ""),
                        }
                    ],
                }
            promotion = await judge_and_promote_benchmark_trajectories(
                str(payload.get("benchmarkId") or ""),
                task_ids=[str(item) for item in payload.get("taskIds") or [] if item],
                judge_name=str(payload.get("judgeName") or "rules"),
                limit=int(payload.get("limit") or 25),
            )
            response = {"harvest": harvest, "promotion": promotion}
            if payload.get("buildAgents"):
                from app.services.agent_builder import build_company_agents

                response["agentBuild"] = await build_company_agents(
                    email=str(payload.get("email") or ""),
                    company_id=str(payload.get("companyId") or ""),
                    company_name=str(payload.get("companyName") or ""),
                    benchmark_id=str(payload.get("benchmarkId") or ""),
                    runtime_kinds=[str(item) for item in payload.get("runtimeKinds") or [] if item],
                    runtime_profiles=payload.get("runtimeProfiles") if isinstance(payload.get("runtimeProfiles"), dict) else {},
                )
            return response
        return harvest
    if job_type == "agent_build":
        from app.services.agent_builder import build_company_agents

        return await build_company_agents(
            email=str(payload.get("email") or ""),
            company_id=str(payload.get("companyId") or ""),
            company_name=str(payload.get("companyName") or ""),
            benchmark_id=str(payload.get("benchmarkId") or ""),
            runtime_kinds=[str(item) for item in payload.get("runtimeKinds") or [] if item],
            runtime_profiles=payload.get("runtimeProfiles") if isinstance(payload.get("runtimeProfiles"), dict) else {},
        )
    if job_type == "assistant_memory_rebuild":
        from app.assistant.memory import rebuild_assistant_memory

        return await rebuild_assistant_memory(
            email=str(payload.get("email") or ""),
            company_id=str(payload.get("companyId") or ""),
            limit=int(payload.get("limit") or 200),
        )
    raise RuntimeError(f"Unknown job type: {job_type}")


async def run_one_job() -> bool:
    job = await claim_next_job()
    if not job:
        return False
    try:
        result = await execute_job(job)
        await complete_job(str(job.get("jobId") or ""), result)
        return True
    except Exception as exc:
        if str(job.get("type") or "") == "knowledge_index":
            try:
                from app.database import knowledge_documents_collection

                payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
                await knowledge_documents_collection.update_one(
                    {"documentId": str(payload.get("documentId") or "")},
                    {"$set": {"status": "index_failed", "indexError": str(exc), "updatedAt": datetime.now(timezone.utc).isoformat()}},
                )
            except Exception:
                logger.exception("Failed to mark knowledge document index failure", extra={"jobId": job.get("jobId")})
        await fail_job(job, str(exc))
        logger.exception("Job failed", extra={"jobId": job.get("jobId"), "type": job.get("type")})
        return True


async def job_worker_loop() -> None:
    interval_seconds = max(1, int(os.getenv("AUTOMATA_JOB_WORKER_INTERVAL_SECONDS", "2") or "2"))
    while True:
        worked = False
        try:
            worked = await run_one_job()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Job worker loop failed")
        await asyncio.sleep(0 if worked else interval_seconds)
