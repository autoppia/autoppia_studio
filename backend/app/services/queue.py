from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from app.database import jobs_collection


WORKER_ID = os.getenv("AUTOMATA_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


async def enqueue_job(
    job_type: str,
    payload: dict[str, Any],
    *,
    run_at: datetime | None = None,
    dedupe_key: str = "",
    max_attempts: int = 3,
) -> dict[str, Any]:
    now = now_utc()
    query = {"dedupeKey": dedupe_key, "status": {"$in": ["queued", "running"]}} if dedupe_key else None
    if query:
        existing = await jobs_collection.find_one(query, {"_id": 0})
        if existing:
            return existing

    doc = {
        "jobId": str(uuid.uuid4()),
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "maxAttempts": max(1, int(max_attempts or 3)),
        "runAt": run_at or now,
        "dedupeKey": dedupe_key,
        "lockedBy": "",
        "leaseUntil": None,
        "lastError": "",
        "createdAt": now,
        "updatedAt": now,
    }
    await jobs_collection.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def claim_next_job(*, worker_id: str = WORKER_ID, lease_seconds: int = 300, job_types: list[str] | None = None) -> dict[str, Any] | None:
    now = now_utc()
    query: dict[str, Any] = {
        "status": "queued",
        "runAt": {"$lte": now},
        "$or": [
            {"leaseUntil": None},
            {"leaseUntil": {"$lte": now}},
            {"leaseUntil": {"$exists": False}},
        ],
    }
    if job_types:
        query["type"] = {"$in": job_types}
    update = {
        "$set": {
            "status": "running",
            "lockedBy": worker_id,
            "leaseUntil": now + timedelta(seconds=max(30, int(lease_seconds or 300))),
            "updatedAt": now,
        },
        "$inc": {"attempts": 1},
    }
    doc = await jobs_collection.find_one_and_update(
        query,
        update,
        projection={"_id": 0},
        sort=[("runAt", 1), ("createdAt", 1)],
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def complete_job(job_id: str, result: dict[str, Any] | None = None) -> None:
    await jobs_collection.update_one(
        {"jobId": job_id},
        {"$set": {"status": "done", "result": result or {}, "leaseUntil": None, "lockedBy": "", "updatedAt": now_utc(), "completedAt": now_utc()}},
    )


async def fail_job(job: dict[str, Any], error: str, *, retry_delay_seconds: int = 60) -> None:
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("maxAttempts") or 3)
    status = "failed" if attempts >= max_attempts else "queued"
    await jobs_collection.update_one(
        {"jobId": job.get("jobId")},
        {
            "$set": {
                "status": status,
                "lastError": str(error),
                "leaseUntil": None,
                "lockedBy": "",
                "runAt": now_utc() + timedelta(seconds=max(1, retry_delay_seconds)) if status == "queued" else job.get("runAt"),
                "updatedAt": now_utc(),
            }
        },
    )
