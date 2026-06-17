from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.database import sessions_collection, tool_runs_collection, usage_events_collection

router = APIRouter()

RangeKey = Literal["24h", "7d", "30d", "90d"]

_RANGE_TO_DELTA = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def _bucket_key(dt: datetime, range_key: RangeKey) -> str:
    if range_key == "24h":
        return dt.strftime("%Y-%m-%dT%H:00")
    return dt.strftime("%Y-%m-%d")


def _range_start(range_key: RangeKey, now: datetime) -> datetime:
    if range_key == "24h":
        return now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    days = _RANGE_TO_DELTA[range_key].days
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)


def _empty_buckets(range_key: RangeKey, now: datetime) -> list[str]:
    start = _range_start(range_key, now)
    if range_key == "24h":
        return [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(24)]
    days = _RANGE_TO_DELTA[range_key].days
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


@router.get("/analytics")
async def get_analytics(
    email: str,
    range: RangeKey = Query("30d"),
):
    """Aggregate session analytics and recorded usage telemetry."""
    try:
        now = datetime.now(timezone.utc)
        cutoff = _range_start(range, now)

        cursor = sessions_collection.find(
            {"email": email, "createdAt": {"$gte": cutoff}},
            {"createdAt": 1, "actionHistory": 1, "_id": 0},
        )

        total = 0
        with_no_tasks = 0
        total_tasks = 0
        bucket_counts: dict[str, dict[str, int]] = {}

        async for doc in cursor:
            total += 1
            actions = doc.get("actionHistory") or []
            task_count = len(actions)
            total_tasks += task_count

            created = doc.get("createdAt")
            if isinstance(created, datetime):
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                key = _bucket_key(created, range)
                slot = bucket_counts.setdefault(key, {"with_tasks": 0, "no_tasks": 0})
                if task_count == 0:
                    slot["no_tasks"] += 1
                    with_no_tasks += 1
                else:
                    slot["with_tasks"] += 1
            elif task_count == 0:
                with_no_tasks += 1

        avg_tasks = (total_tasks / total) if total > 0 else 0.0

        usage_cursor = usage_events_collection.find(
            {"email": email, "createdAt": {"$gte": cutoff}},
            {"createdAt": 1, "credits": 1, "source": 1, "kind": 1, "_id": 0},
        )
        total_usage = 0.0
        usage_by_source: dict[str, float] = {}
        usage_by_bucket: dict[str, float] = {}
        async for doc in usage_cursor:
            try:
                credits = float(doc.get("credits") or 0.0)
            except (TypeError, ValueError):
                credits = 0.0
            total_usage += credits
            source = str(doc.get("source") or doc.get("kind") or "unknown")
            usage_by_source[source] = usage_by_source.get(source, 0.0) + credits
            created = _coerce_datetime(doc.get("createdAt"))
            if created:
                key = _bucket_key(created, range)
                usage_by_bucket[key] = usage_by_bucket.get(key, 0.0) + credits

        over_time = []
        for key in _empty_buckets(range, now):
            slot = bucket_counts.get(key, {"with_tasks": 0, "no_tasks": 0})
            over_time.append(
                {
                    "bucket": key,
                    "with_tasks": slot["with_tasks"],
                    "no_tasks": slot["no_tasks"],
                }
            )
        usage_over_time = [
            {"bucket": key, "usage": round(usage_by_bucket.get(key, 0.0), 6)}
            for key in _empty_buckets(range, now)
        ]
        breakdown = [
            {"source": source, "usage": round(usage, 6)}
            for source, usage in sorted(usage_by_source.items(), key=lambda item: item[1], reverse=True)
        ]

        return {
            "range": range,
            "credits": {
                "total_usage": round(total_usage, 6),
                "runway": None,
                "breakdown_by_source": breakdown,
                "usage_over_time": usage_over_time,
                "available": True,
            },
            "sessions": {
                "total": total,
                "with_no_tasks": with_no_tasks,
                "avg_tasks_per_session": round(avg_tasks, 2),
                "avg_duration_seconds": None,
                "free_tier": total,
                "over_time": over_time,
                "available": True,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/runtime-events")
async def list_agent_runtime_events(agent_id: str, limit: int = Query(100, ge=1, le=500)):
    cursor = tool_runs_collection.find({"agentId": agent_id}, {"_id": 0}).sort("createdAt", -1).limit(limit)
    return {"events": await cursor.to_list(length=limit)}
