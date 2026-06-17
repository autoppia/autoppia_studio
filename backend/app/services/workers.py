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
from app.services.queue import claim_next_job, complete_job, fail_job

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
