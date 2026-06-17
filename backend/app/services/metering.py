from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import usage_events_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def default_credits_for_kind(kind: str) -> float:
    if kind == "agent_step":
        return _env_float("AUTOMATA_CREDITS_PER_AGENT_STEP", 0.05)
    if kind == "tool_call":
        return _env_float("AUTOMATA_CREDITS_PER_TOOL_CALL", 0.02)
    if kind == "browser_action":
        return _env_float("AUTOMATA_CREDITS_PER_BROWSER_ACTION", 0.01)
    return _env_float("AUTOMATA_CREDITS_PER_EVENT", 0.0)


async def record_usage(
    *,
    email: str = "",
    company_id: str = "",
    agent_id: str = "",
    run_id: str = "",
    kind: str,
    units: float = 1.0,
    credits: float | None = None,
    source: str = "",
    model: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_units = max(0.0, float(units or 0.0))
    unit_credits = default_credits_for_kind(kind) if credits is None else max(0.0, float(credits or 0.0))
    doc = {
        "usageEventId": str(uuid.uuid4()),
        "email": email,
        "companyId": company_id,
        "agentId": agent_id,
        "runId": run_id,
        "kind": kind,
        "source": source or kind,
        "model": model,
        "units": safe_units,
        "credits": round(unit_credits * safe_units, 8),
        "metadata": metadata or {},
        "createdAt": _now(),
    }
    await usage_events_collection.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def run_credits_spent(run_id: str) -> float:
    if not run_id:
        return 0.0
    total = 0.0
    cursor = usage_events_collection.find({"runId": run_id}, {"credits": 1, "_id": 0})
    async for doc in cursor:
        try:
            total += float(doc.get("credits") or 0.0)
        except (TypeError, ValueError):
            continue
    return round(total, 8)
