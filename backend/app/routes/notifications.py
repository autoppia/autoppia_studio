import uuid
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import eval_runs_collection, harvester_runs_collection, notifications_collection, work_items_collection

router = APIRouter()

NotificationLevel = Literal["info", "success", "warning", "error"]


class NotificationCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    title: str
    message: str = ""
    level: NotificationLevel = "info"
    source: str = "system"
    entityType: str = ""
    entityId: str = ""
    actionUrl: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationCleanupRequest(BaseModel):
    email: str = ""
    companyId: str = ""
    readOlderThanDays: int = 30
    maxPerUser: int = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notification_payload(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "notificationId": doc.get("notificationId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "level": doc.get("level", "info"),
        "source": doc.get("source", "system"),
        "entityType": doc.get("entityType", ""),
        "entityId": doc.get("entityId", ""),
        "actionUrl": doc.get("actionUrl", ""),
        "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
        "read": bool(doc.get("read", False)),
        "createdAt": doc.get("createdAt", ""),
        "readAt": doc.get("readAt", ""),
    }


async def create_notification(
    *,
    email: str,
    company_id: str = "",
    title: str,
    message: str = "",
    level: NotificationLevel = "info",
    source: str = "system",
    entity_type: str = "",
    entity_id: str = "",
    action_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not email or not title.strip():
        return {}
    now = _now()
    doc = {
        "notificationId": str(uuid.uuid4()),
        "email": email,
        "companyId": company_id,
        "title": title.strip(),
        "message": message.strip(),
        "level": level,
        "source": source,
        "entityType": entity_type,
        "entityId": entity_id,
        "actionUrl": action_url,
        "metadata": metadata or {},
        "read": False,
        "createdAt": now,
        "updatedAt": now,
        "readAt": "",
    }
    await notifications_collection.insert_one(doc)
    payload = _notification_payload(doc)
    try:
        from app.sio_app import emit_activity_event

        await emit_activity_event(
            email,
            company_id,
            "notification-created",
            {"notification": payload},
        )
        await emit_activity_event(email, company_id, "activity-updated", {"reason": "notification-created"})
    except Exception:
        pass
    return payload


async def _work_status_counts(email: str, company_id: str = "") -> dict[str, int]:
    base_query: dict[str, Any] = {"email": email}
    if company_id:
        base_query["companyId"] = company_id
    statuses = ["TODO", "RUNNING", "REVIEW", "DONE", "FAILED"]
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = await work_items_collection.count_documents({**base_query, "status": status})
    return counts


async def _count_many(collection, query: dict[str, Any], field: str, values: list[str]) -> int:
    return await collection.count_documents({**query, field: {"$in": values}})


async def _eval_status_counts(base_query: dict[str, Any]) -> dict[str, int]:
    return {
        "pending": await eval_runs_collection.count_documents({**base_query, "label": "pending"}),
        "pass": await eval_runs_collection.count_documents({**base_query, "label": "pass"}),
        "fail": await eval_runs_collection.count_documents({**base_query, "label": "fail"}),
    }


async def _harvester_status_counts(base_query: dict[str, Any]) -> dict[str, int]:
    running = ["running", "harvesting", "pending", "queued"]
    completed = ["completed", "success", "harvested"]
    failed = ["failed", "error", "harvest_failed"]
    return {
        "running": await _count_many(harvester_runs_collection, base_query, "status", running),
        "completed": await _count_many(harvester_runs_collection, base_query, "status", completed),
        "failed": await _count_many(harvester_runs_collection, base_query, "status", failed),
    }


async def cleanup_notifications(
    *,
    email: str = "",
    company_id: str = "",
    read_older_than_days: int = 30,
    max_per_user: int = 500,
) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(read_older_than_days or 30)))).isoformat()
    query: dict[str, Any] = {"read": True, "readAt": {"$lte": cutoff, "$ne": ""}}
    if email:
        query["email"] = email
    if company_id:
        query["companyId"] = company_id
    deleted_old = await notifications_collection.delete_many(query)

    deleted_over_limit = 0
    capped_limit = max(50, min(5000, int(max_per_user or 500)))
    if email:
        scope: dict[str, Any] = {"email": email}
        if company_id:
            scope["companyId"] = company_id
        docs = await notifications_collection.find(scope, {"_id": 0, "notificationId": 1}).sort("createdAt", -1).to_list(length=capped_limit + 500)
        overflow = docs[capped_limit:]
        if overflow:
            ids = [doc.get("notificationId") for doc in overflow if doc.get("notificationId")]
            result = await notifications_collection.delete_many({"notificationId": {"$in": ids}})
            deleted_over_limit = result.deleted_count

    return {"deletedOld": deleted_old.deleted_count, "deletedOverLimit": deleted_over_limit}


@router.post("/notifications")
async def create_notification_route(body: NotificationCreateRequest):
    notification = await create_notification(
        email=body.email,
        company_id=body.companyId,
        title=body.title,
        message=body.message,
        level=body.level,
        source=body.source,
        entity_type=body.entityType,
        entity_id=body.entityId,
        action_url=body.actionUrl,
        metadata=body.metadata,
    )
    if not notification:
        raise HTTPException(status_code=400, detail="email and title are required")
    return {"success": True, "notification": notification}


@router.get("/notifications")
async def list_notifications(email: str, companyId: str = "", unreadOnly: bool = False, limit: int = 30):
    query: dict[str, Any] = {"email": email}
    if companyId:
        query["companyId"] = companyId
    if unreadOnly:
        query["read"] = False
    capped_limit = max(1, min(100, int(limit or 30)))
    docs = await notifications_collection.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=capped_limit)
    unread_query = {"email": email, "read": False}
    if companyId:
        unread_query["companyId"] = companyId
    unread_count = await notifications_collection.count_documents(unread_query)
    return {"notifications": [_notification_payload(doc) for doc in docs], "unreadCount": unread_count}


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    result = await notifications_collection.update_one(
        {"notificationId": notification_id},
        {"$set": {"read": True, "readAt": _now(), "updatedAt": _now()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    doc = await notifications_collection.find_one({"notificationId": notification_id}, {"_id": 0})
    return {"success": True, "notification": _notification_payload(doc or {})}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(email: str, companyId: str = ""):
    query: dict[str, Any] = {"email": email, "read": False}
    if companyId:
        query["companyId"] = companyId
    result = await notifications_collection.update_many(
        query,
        {"$set": {"read": True, "readAt": _now(), "updatedAt": _now()}},
    )
    return {"success": True, "modifiedCount": result.modified_count}


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str):
    result = await notifications_collection.delete_one({"notificationId": notification_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.delete("/notifications")
async def clear_notifications(email: str, companyId: str = "", readOnly: bool = True):
    query: dict[str, Any] = {"email": email}
    if companyId:
        query["companyId"] = companyId
    if readOnly:
        query["read"] = True
    result = await notifications_collection.delete_many(query)
    return {"success": True, "deletedCount": result.deleted_count}


@router.post("/notifications/cleanup")
async def cleanup_notifications_route(body: NotificationCleanupRequest):
    result = await cleanup_notifications(
        email=body.email,
        company_id=body.companyId,
        read_older_than_days=body.readOlderThanDays,
        max_per_user=body.maxPerUser,
    )
    return {"success": True, **result}


async def notification_cleanup_loop() -> None:
    interval_seconds = max(3600, int(os.getenv("AUTOMATA_NOTIFICATION_CLEANUP_INTERVAL_SECONDS", "86400") or "86400"))
    days = max(1, int(os.getenv("AUTOMATA_NOTIFICATION_RETENTION_DAYS", "30") or "30"))
    max_per_user = max(50, int(os.getenv("AUTOMATA_NOTIFICATION_MAX_PER_USER", "500") or "500"))
    while True:
        try:
            await cleanup_notifications(read_older_than_days=days, max_per_user=max_per_user)
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


@router.get("/activity-summary")
async def activity_summary(email: str, companyId: str = ""):
    base_query: dict[str, Any] = {"email": email}
    if companyId:
        base_query["companyId"] = companyId
    now = _now()
    counts = await _work_status_counts(email, companyId)
    eval_counts = await _eval_status_counts(base_query)
    harvester_counts = await _harvester_status_counts(base_query)
    scheduled_due = await work_items_collection.count_documents(
        {**base_query, "triggerType": "scheduled", "status": {"$ne": "RUNNING"}, "nextRunAt": {"$lte": now, "$ne": ""}}
    )
    scheduled_upcoming = await work_items_collection.count_documents(
        {**base_query, "triggerType": "scheduled", "nextRunAt": {"$gt": now}}
    )
    running_docs = await work_items_collection.find(
        {**base_query, "status": "RUNNING"},
        {"_id": 0, "workItemId": 1, "title": 1, "agentName": 1, "runTarget": 1, "startedAt": 1, "lastRunId": 1},
    ).sort("startedAt", -1).to_list(length=8)
    recent_notifications = await notifications_collection.find(
        {**base_query},
        {"_id": 0},
    ).sort("createdAt", -1).to_list(length=5)
    unread_count = await notifications_collection.count_documents({**base_query, "read": False})

    active_sessions = 0
    try:
        from app.sio_app import active_session_count

        active_sessions = active_session_count(email, companyId)
    except Exception:
        active_sessions = 0

    return {
        "status": {
            "runningTasks": counts.get("RUNNING", 0),
            "queuedTasks": counts.get("TODO", 0),
            "reviewTasks": counts.get("REVIEW", 0),
            "doneTasks": counts.get("DONE", 0),
            "failedTasks": counts.get("FAILED", 0),
            "scheduledDue": scheduled_due,
            "scheduledUpcoming": scheduled_upcoming,
            "activeSessions": active_sessions,
            "evalRunsPending": eval_counts["pending"],
            "evalRunsPassed": eval_counts["pass"],
            "evalRunsFailed": eval_counts["fail"],
            "harvestersRunning": harvester_counts["running"],
            "harvestersCompleted": harvester_counts["completed"],
            "harvestersFailed": harvester_counts["failed"],
        },
        "running": [
            {
                "workItemId": doc.get("workItemId", ""),
                "title": doc.get("title", ""),
                "agentName": doc.get("agentName", ""),
                "runTarget": doc.get("runTarget", "selected"),
                "startedAt": doc.get("startedAt", ""),
                "lastRunId": doc.get("lastRunId", ""),
            }
            for doc in running_docs
        ],
        "notifications": {
            "unreadCount": unread_count,
            "recent": [_notification_payload(doc) for doc in recent_notifications],
        },
    }
