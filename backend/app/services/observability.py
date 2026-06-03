from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import tool_runs_collection
from app.services.credentials import redact_secrets


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_runtime_event(
    *,
    agent_id: str,
    company_id: str = "",
    event_type: str,
    step_index: int | None = None,
    tool_name: str = "",
    status: str = "ok",
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    now = now_iso()
    doc = {
        "runId": str(uuid.uuid4()),
        "agentId": agent_id,
        "companyId": company_id,
        "eventType": event_type,
        "stepIndex": step_index,
        "toolName": tool_name,
        "status": status,
        "payload": redact_secrets(payload or {}),
        "result": redact_secrets(result or {}),
        "error": error,
        "createdAt": now,
    }
    await tool_runs_collection.insert_one(doc)
    doc.pop("_id", None)
    return doc
