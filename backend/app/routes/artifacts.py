from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.database import artifacts_collection, companies_collection
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope

router = APIRouter()

TEXT_TYPES = {
    "markdown": ("text/markdown; charset=utf-8", ".md"),
    "html": ("text/html; charset=utf-8", ".html"),
    "react": ("text/plain; charset=utf-8", ".jsx"),
    "javascript": ("text/javascript; charset=utf-8", ".js"),
    "typescript": ("text/plain; charset=utf-8", ".ts"),
    "python": ("text/x-python; charset=utf-8", ".py"),
    "svg": ("image/svg+xml; charset=utf-8", ".svg"),
    "mermaid": ("text/plain; charset=utf-8", ".mmd"),
    "csv": ("text/csv; charset=utf-8", ".csv"),
    "json": ("application/json; charset=utf-8", ".json"),
    "text": ("text/plain; charset=utf-8", ".txt"),
    "docx": ("text/markdown; charset=utf-8", ".md"),
    "pdf": ("text/markdown; charset=utf-8", ".md"),
    "pptx": ("text/markdown; charset=utf-8", ".md"),
    "xlsx": ("text/csv; charset=utf-8", ".csv"),
}


class ArtifactCreateRequest(BaseModel):
    email: str
    title: str
    artifactType: str = "markdown"
    description: str = ""
    content: str = ""
    fileName: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactUpdateRequest(BaseModel):
    title: str | None = None
    artifactType: str | None = None
    description: str | None = None
    content: str | None = None
    fileName: str | None = None
    metadata: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _clean_type(value: Any) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "markdown").strip().lower()).strip("-")
    return clean or "markdown"


def _safe_file_name(title: str, artifact_type: str, file_name: str = "") -> str:
    candidate = file_name.strip() or title.strip() or "artifact"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", candidate).strip(".-") or "artifact"
    _, ext = TEXT_TYPES.get(artifact_type, TEXT_TYPES["text"])
    if "." not in stem:
        stem = f"{stem}{ext}"
    return stem[:160]


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    artifact_type = _clean_type(doc.get("artifactType"))
    return {
        "artifactId": doc.get("artifactId", ""),
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "sessionId": doc.get("sessionId", ""),
        "title": doc.get("title", ""),
        "artifactType": artifact_type,
        "description": doc.get("description", ""),
        "content": doc.get("content", ""),
        "fileName": doc.get("fileName") or _safe_file_name(doc.get("title", ""), artifact_type),
        "sourceTool": doc.get("sourceTool", ""),
        "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _ensure_company(company_id: str, scope: RequestScope) -> dict[str, Any]:
    query: dict[str, Any] = {"companyId": company_id}
    if scope.email:
        query["email"] = scope.email
    company = await companies_collection.find_one(query, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def _owned_artifact(artifact_id: str, scope: RequestScope) -> dict[str, Any]:
    query: dict[str, Any] = {"artifactId": artifact_id}
    if scope.email:
        query["email"] = scope.email
    doc = await artifacts_collection.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return doc


@router.get("/companies/{company_id}/artifacts")
async def list_company_artifacts(
    company_id: str,
    email: str = "",
    sessionId: str = "",
    workItemId: str = "",
    skillId: str = "",
    trajectoryId: str = "",
    toolId: str = "",
    scope: RequestScope = Depends(get_request_scope),
):
    scope = coerce_request_scope(scope)
    scoped_email = scope.require_email(email)
    await _ensure_company(company_id, scope)
    query: dict[str, Any] = {"companyId": company_id, "email": scoped_email}
    if sessionId:
        query["sessionId"] = sessionId
    if workItemId:
        query["metadata.workItemId"] = workItemId
    if skillId:
        query["metadata.skillId"] = skillId
    if trajectoryId:
        query["metadata.trajectoryId"] = trajectoryId
    if toolId:
        query["metadata.toolId"] = toolId
    docs = await artifacts_collection.find(
        query,
        {"_id": 0},
    ).sort("updatedAt", -1).to_list(length=500)
    return {"artifacts": [_serialize(doc) for doc in docs]}


@router.post("/companies/{company_id}/artifacts")
async def create_company_artifact(company_id: str, body: ArtifactCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    scoped_email = scope.require_email(body.email)
    await _ensure_company(company_id, scope)
    artifact_type = _clean_type(body.artifactType)
    now = _now()
    doc = {
        "artifactId": str(uuid.uuid4()),
        "companyId": company_id,
        "email": scoped_email,
        "title": _clean_text(body.title, 120) or "Untitled artifact",
        "artifactType": artifact_type,
        "description": _clean_text(body.description, 500),
        "content": body.content or "",
        "fileName": _safe_file_name(body.title, artifact_type, body.fileName),
        "metadata": body.metadata,
        "createdAt": now,
        "updatedAt": now,
    }
    await artifacts_collection.insert_one(doc)
    return {"success": True, "artifact": _serialize(doc)}


@router.patch("/artifacts/{artifact_id}")
async def update_artifact(artifact_id: str, body: ArtifactUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    existing = await _owned_artifact(artifact_id, scope)
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        updates["title"] = _clean_text(updates["title"], 120) or existing.get("title", "Untitled artifact")
    if "artifactType" in updates and updates["artifactType"] is not None:
        updates["artifactType"] = _clean_type(updates["artifactType"])
    if "description" in updates and updates["description"] is not None:
        updates["description"] = _clean_text(updates["description"], 500)
    updates = {key: value for key, value in updates.items() if value is not None}
    artifact_type = updates.get("artifactType") or existing.get("artifactType") or "markdown"
    if "fileName" in updates or "title" in updates or "artifactType" in updates:
        updates["fileName"] = _safe_file_name(
            updates.get("title") or existing.get("title", ""),
            artifact_type,
            updates.get("fileName") or existing.get("fileName", ""),
        )
    updates["updatedAt"] = _now()
    await artifacts_collection.update_one({"artifactId": artifact_id, "email": existing.get("email", "")}, {"$set": updates})
    refreshed = await artifacts_collection.find_one({"artifactId": artifact_id}, {"_id": 0})
    return {"success": True, "artifact": _serialize(refreshed or {**existing, **updates})}


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(artifact_id: str, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    existing = await _owned_artifact(artifact_id, scope)
    result = await artifacts_collection.delete_one({"artifactId": artifact_id, "email": existing.get("email", "")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"success": True}


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, email: str = "", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    if email:
        scope = RequestScope(email=email)
    doc = await _owned_artifact(artifact_id, scope)
    artifact = _serialize(doc)
    media_type, _ = TEXT_TYPES.get(artifact["artifactType"], TEXT_TYPES["text"])
    headers = {"Content-Disposition": f'attachment; filename="{artifact["fileName"]}"'}
    return Response(content=artifact.get("content", ""), media_type=media_type, headers=headers)
