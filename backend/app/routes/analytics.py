from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.database import sessions_collection

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


def _empty_buckets(range_key: RangeKey, now: datetime) -> list[str]:
    delta = _RANGE_TO_DELTA[range_key]
    if range_key == "24h":
        start = (now - delta).replace(minute=0, second=0, microsecond=0)
        return [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(24)]
    days = delta.days
    start = (now - delta).replace(hour=0, minute=0, second=0, microsecond=0)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)]


@router.get("/analytics")
async def get_analytics(
    email: str,
    range: RangeKey = Query("30d"),
):
    """Aggregate analytics from existing session data.

    Credit/cost fields return None — billing telemetry is not tracked yet.
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - _RANGE_TO_DELTA[range]

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

        return {
            "range": range,
            "credits": {
                "total_usage": 0.0,
                "runway": None,
                "breakdown_by_source": [],
                "usage_over_time": [],
                "available": False,
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
