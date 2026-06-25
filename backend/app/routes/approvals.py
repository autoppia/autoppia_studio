from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import approvals_collection, work_items_collection
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.services.approvals import resolve_approval, serialize_approval
from app.services.queue import enqueue_job

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    email: str = ""
    reason: str = ""


def _query_scope(
    email: str,
    company_id: str = "",
    status: str = "",
    session_id: str = "",
    work_item_id: str = "",
    skill_id: str = "",
    trajectory_id: str = "",
    tool_id: str = "",
) -> dict[str, Any]:
    query: dict[str, Any] = {"email": email}
    if company_id:
        query["companyId"] = company_id
    if status:
        query["status"] = status
    or_filters: list[dict[str, Any]] = []
    if session_id:
        or_filters.extend([
            {"sessionId": session_id},
            {"metadata.sessionId": session_id},
        ])
    if work_item_id:
        or_filters.append({"metadata.workItemId": work_item_id})
    if skill_id:
        or_filters.append({"metadata.skillId": skill_id})
    if trajectory_id:
        or_filters.append({"metadata.trajectoryId": trajectory_id})
    if tool_id:
        or_filters.append({"metadata.toolId": tool_id})
    if or_filters:
        query["$or"] = or_filters
    return query


def _exclude_runtime_session_approvals(query: dict[str, Any]) -> dict[str, Any]:
    runtime_exclusion = {
        "$or": [
            {"metadata.sourceKind": {"$in": ["work", "async", "scheduled"]}},
            {"metadata.workItemId": {"$exists": True, "$nin": ["", None]}},
        ],
    }
    if "$or" in query:
        base = {key: value for key, value in query.items() if key != "$or"}
        return {
            **base,
            "$and": [
                {"$or": query["$or"]},
                runtime_exclusion,
            ],
        }
    return {
        **query,
        **runtime_exclusion,
    }


async def _owned_approval(approval_id: str, scope: RequestScope) -> dict[str, Any]:
    query: dict[str, Any] = {"approvalId": approval_id}
    if scope.email:
        query["email"] = scope.email
    doc = await approvals_collection.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Approval not found")
    return doc


@router.get("/approvals")
async def list_approvals(
    email: str = "",
    companyId: str = "",
    sessionId: str = "",
    workItemId: str = "",
    skillId: str = "",
    trajectoryId: str = "",
    toolId: str = "",
    status: str = "pending",
    includeRuntime: bool = False,
    scope: RequestScope = Depends(get_request_scope),
):
    scope = coerce_request_scope(scope)
    scoped_email = scope.require_email(email)
    clean_status = status if status in {"pending", "approved", "rejected", "expired", ""} else "pending"
    query = _query_scope(scoped_email, companyId, clean_status, sessionId, workItemId, skillId, trajectoryId, toolId)
    if not includeRuntime:
        query = _exclude_runtime_session_approvals(query)
    docs = await approvals_collection.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=500)
    return {"approvals": [serialize_approval(doc) for doc in docs]}


@router.post("/approvals/{approval_id}/approve")
async def approve_approval(
    approval_id: str,
    body: ApprovalDecisionRequest = ApprovalDecisionRequest(),
    scope: RequestScope = Depends(get_request_scope),
):
    scope = coerce_request_scope(scope)
    existing = await _owned_approval(approval_id, scope)
    decided_by = scope.require_email(body.email or str(existing.get("email") or ""))
    approval = await resolve_approval(approval_id, decided_by=decided_by, status="approved", reason=body.reason)
    resume = await _resume_work_item_for_approval(approval)
    metadata = approval.get("metadata") if isinstance(approval.get("metadata"), dict) else {}
    state_patch = metadata.get("statePatch") if isinstance(metadata.get("statePatch"), dict) else {"approvedConnectorToolCalls": [approval.get("approvalKey", "")]}
    session_id = str(metadata.get("sessionId") or "")
    return {
        "success": True,
        "approval": approval,
        "statePatch": state_patch,
        "resume": resume,
        "sessionResume": {
            "required": bool(session_id and not resume.get("started")),
            "sessionId": session_id,
            "runtimeStatePatch": state_patch,
            "socketEvent": "continue-task",
        },
    }


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: str,
    body: ApprovalDecisionRequest = ApprovalDecisionRequest(),
    scope: RequestScope = Depends(get_request_scope),
):
    scope = coerce_request_scope(scope)
    existing = await _owned_approval(approval_id, scope)
    decided_by = scope.require_email(body.email or str(existing.get("email") or ""))
    approval = await resolve_approval(approval_id, decided_by=decided_by, status="rejected", reason=body.reason)
    await _mark_work_item_rejected(approval)
    return {"success": True, "approval": approval}


async def _resume_work_item_for_approval(approval: dict[str, Any]) -> dict[str, Any]:
    metadata = approval.get("metadata") if isinstance(approval.get("metadata"), dict) else {}
    work_item_id = str(metadata.get("workItemId") or "")
    if not work_item_id:
        return {"started": False}

    item = await work_items_collection.find_one({"workItemId": work_item_id}, {"_id": 0})
    if not item:
        return {"started": False, "reason": "work_item_not_found"}
    pending = item.get("pendingApproval") if isinstance(item.get("pendingApproval"), dict) else {}
    if pending.get("approvalId") and pending.get("approvalId") != approval.get("approvalId"):
        return {"started": False, "reason": "work_item_waiting_on_different_approval"}

    run_id = str(uuid.uuid4())
    metadata = approval.get("metadata") if isinstance(approval.get("metadata"), dict) else {}
    await work_items_collection.update_one(
        {"workItemId": work_item_id},
        {
            "$set": {
                "status": "RUNNING",
                "lastRunId": run_id,
                "pendingApproval": {
                    **pending,
                    "approvalId": approval.get("approvalId", ""),
                    "approvalKey": approval.get("approvalKey", ""),
                    "statePatch": pending.get("statePatch") or metadata.get("statePatch", {}),
                    "status": "approved",
                    "resumedRunId": run_id,
                    "updatedAt": approval.get("updatedAt", ""),
                },
                "startedAt": approval.get("updatedAt", ""),
                "updatedAt": approval.get("updatedAt", ""),
            }
        },
    )

    await enqueue_job("work_run", {"workItemId": work_item_id, "runId": run_id}, dedupe_key=f"work_run:{work_item_id}:{run_id}")
    return {"started": True, "workItemId": work_item_id, "runId": run_id}


async def _mark_work_item_rejected(approval: dict[str, Any]) -> None:
    metadata = approval.get("metadata") if isinstance(approval.get("metadata"), dict) else {}
    work_item_id = str(metadata.get("workItemId") or "")
    if not work_item_id:
        return
    await work_items_collection.update_one(
        {"workItemId": work_item_id},
        {
            "$set": {
                "status": "REVIEW",
                "pendingApproval.status": "rejected",
                "pendingApproval.updatedAt": approval.get("updatedAt", ""),
                "updatedAt": approval.get("updatedAt", ""),
            }
        },
    )
