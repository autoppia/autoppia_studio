from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.database import approvals_collection
from app.routes.notifications import create_notification
from app.services.credentials import redact_secrets
from app.services.observability import record_runtime_event


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_approval_key(name: str, index: int, arguments: dict[str, Any]) -> str:
    payload = json.dumps(redact_secrets(arguments), sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{name}:{index}:{payload}".encode("utf-8")).hexdigest()[:20]
    return f"{name}:{index}:{digest}"


def serialize_approval(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    proposed_action = doc.get("proposedAction") if isinstance(doc.get("proposedAction"), dict) else {}
    tool_name = str(proposed_action.get("name") or metadata.get("toolName") or "")
    work_item_id = str(metadata.get("workItemId") or "")
    session_id = str(metadata.get("sessionId") or "")
    source_kind = str(metadata.get("sourceKind") or ("work" if work_item_id else "session" if session_id else "runtime"))
    audit_trail = doc.get("auditTrail") if isinstance(doc.get("auditTrail"), list) else []
    if not audit_trail:
        audit_trail = [
            {
                "event": "requested",
                "at": doc.get("createdAt", ""),
                "by": doc.get("email", ""),
                "reason": "",
            }
        ]
        if doc.get("decidedAt") or doc.get("decidedBy"):
            audit_trail.append(
                {
                    "event": doc.get("status", ""),
                    "at": doc.get("decidedAt", "") or doc.get("updatedAt", ""),
                    "by": doc.get("decidedBy", ""),
                    "reason": doc.get("decisionReason", ""),
                }
            )
    return {
        "approvalId": doc.get("approvalId", ""),
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "agentId": doc.get("agentId", ""),
        "runId": doc.get("runId", ""),
        "workItemId": work_item_id,
        "sessionId": session_id,
        "sourceKind": source_kind,
        "approvalKey": doc.get("approvalKey", ""),
        "toolName": tool_name,
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "proposedAction": proposed_action,
        "entityRef": doc.get("entityRef") if isinstance(doc.get("entityRef"), dict) else {},
        "status": doc.get("status", "pending"),
        "decidedBy": doc.get("decidedBy", ""),
        "decisionReason": doc.get("decisionReason", ""),
        "createdAt": doc.get("createdAt", ""),
        "updatedAt": doc.get("updatedAt", ""),
        "expiresAt": doc.get("expiresAt", ""),
        "decidedAt": doc.get("decidedAt", ""),
        "metadata": metadata,
        "auditTrail": audit_trail,
    }


async def create_pending_approval(
    *,
    email: str,
    company_id: str,
    agent_id: str,
    approval_key: str,
    proposed_action: dict[str, Any],
    title: str,
    message: str,
    run_id: str = "",
    entity_ref: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    expires_in_hours: int = 168,
) -> dict[str, Any]:
    metadata = metadata or {}
    existing_query: dict[str, Any] = {
        "companyId": company_id,
        "agentId": agent_id,
        "approvalKey": approval_key,
        "status": "pending",
    }
    session_id = str(metadata.get("sessionId") or "")
    work_item_id = str(metadata.get("workItemId") or "")
    run_id = str(run_id or metadata.get("runId") or "")
    if session_id:
        existing_query["metadata.sessionId"] = session_id
    elif work_item_id:
        existing_query["metadata.workItemId"] = work_item_id
    elif run_id:
        existing_query["runId"] = run_id
    existing = await approvals_collection.find_one(existing_query, {"_id": 0})
    if existing:
        return serialize_approval(existing)

    now = now_iso()
    doc = {
        "approvalId": str(uuid.uuid4()),
        "companyId": company_id,
        "email": email,
        "agentId": agent_id,
        "runId": run_id,
        "approvalKey": approval_key,
        "title": title.strip() or "Approval required",
        "message": message.strip(),
        "proposedAction": redact_secrets(proposed_action),
        "entityRef": entity_ref or {},
        "status": "pending",
        "decidedBy": "",
        "decisionReason": "",
        "createdAt": now,
        "updatedAt": now,
        "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=max(1, expires_in_hours))).isoformat(),
        "decidedAt": "",
        "metadata": metadata,
        "auditTrail": [
            {
                "event": "requested",
                "at": now,
                "by": email,
                "reason": "",
            }
        ],
    }
    await approvals_collection.insert_one(doc)

    await create_notification(
        email=email,
        company_id=company_id,
        title=doc["title"],
        message=doc["message"],
        level="warning",
        source="approval",
        entity_type="approval",
        entity_id=doc["approvalId"],
        action_url="/approvals",
        metadata={"approvalId": doc["approvalId"], "approvalKey": approval_key},
    )
    await record_runtime_event(
        agent_id=agent_id,
        company_id=company_id,
        event_type="approval.requested",
        tool_name=str((proposed_action or {}).get("name") or ""),
        status="pending",
        payload={"approvalKey": approval_key, "proposedAction": proposed_action},
        result={"approvalId": doc["approvalId"]},
    )
    return serialize_approval(doc)


async def resolve_approval(
    approval_id: str,
    *,
    decided_by: str = "",
    status: str,
    reason: str = "",
) -> dict[str, Any]:
    if status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="status must be approved or rejected")
    existing = await approvals_collection.find_one({"approvalId": approval_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Approval not found")
    if existing.get("status") != "pending":
        return serialize_approval(existing)

    now = now_iso()
    updates = {
        "status": status,
        "decidedBy": decided_by,
        "decisionReason": reason.strip(),
        "decidedAt": now,
        "updatedAt": now,
    }
    audit_event = {
        "event": status,
        "at": now,
        "by": decided_by,
        "reason": reason.strip(),
    }
    await approvals_collection.update_one({"approvalId": approval_id}, {"$set": updates})
    await approvals_collection.update_one(
        {"approvalId": approval_id},
        {
            "$push": {"auditTrail": audit_event}
        },
    )
    existing_audit_trail = existing.get("auditTrail") if isinstance(existing.get("auditTrail"), list) else []
    resolved = {**existing, **updates, "auditTrail": [*existing_audit_trail, audit_event]}
    await record_runtime_event(
        agent_id=str(existing.get("agentId") or ""),
        company_id=str(existing.get("companyId") or ""),
        event_type=f"approval.{status}",
        tool_name=str((existing.get("proposedAction") or {}).get("name") or ""),
        status=status,
        payload={"approvalKey": existing.get("approvalKey"), "reason": reason},
        result={"approvalId": approval_id},
    )
    return serialize_approval(resolved)
