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
