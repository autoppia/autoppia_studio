import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.database import approvals_collection, artifacts_collection, session_documents_collection, sessions_collection
from app.routes.knowledge import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, create_knowledge_document_record

router = APIRouter()

SESSION_DOCUMENT_STORAGE_DIR = Path(os.getenv("SESSION_DOCUMENT_STORAGE_DIR", Path.home() / ".automata" / "session_documents"))

ARTIFACT_TEXT_TYPES = {
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
}


def _safe_filename(value: str) -> str:
    name = Path(value or "document").name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(name).stem).strip("-") or "document"
    suffix = Path(name).suffix.lower()
    return f"{stem[:80]}{suffix}"


def _serialize_session_document(doc: dict) -> dict:
    return {
        "documentId": doc.get("documentId", ""),
        "sessionId": doc.get("sessionId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "filename": doc.get("filename", ""),
        "contentType": doc.get("contentType", ""),
        "size": doc.get("size", 0),
        "status": doc.get("status", "uploaded"),
        "source": doc.get("source", "session_upload"),
        "knowledgeDocumentId": doc.get("knowledgeDocumentId", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _clean_artifact_type(value: Any) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "markdown").strip().lower()).strip("-")
    return clean or "markdown"


def _artifact_file_name(title: str, artifact_type: str, file_name: str = "") -> str:
    candidate = Path(str(file_name or title or "artifact")).name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", candidate).strip(".-") or "artifact"
    _, ext = ARTIFACT_TEXT_TYPES.get(artifact_type, ARTIFACT_TEXT_TYPES["text"])
    if "." not in stem:
        stem = f"{stem}{ext}"
    return stem[:160]


def _serialize_session_artifact(doc: dict) -> dict:
    artifact_type = _clean_artifact_type(doc.get("artifactType") or doc.get("kind"))
    content_type, _ = ARTIFACT_TEXT_TYPES.get(artifact_type, ARTIFACT_TEXT_TYPES["text"])
    return {
        "artifactId": doc.get("artifactId", ""),
        "sessionId": doc.get("sessionId", ""),
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name") or doc.get("title") or "Artifact",
        "title": doc.get("title") or doc.get("name") or "Artifact",
        "artifactType": artifact_type,
        "kind": artifact_type,
        "content": doc.get("content", ""),
        "contentType": doc.get("contentType") or content_type,
        "fileName": doc.get("fileName") or _artifact_file_name(doc.get("title") or doc.get("name") or "Artifact", artifact_type),
        "url": doc.get("url", ""),
        "sourceTool": doc.get("sourceTool", ""),
        "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _pretty_session_action(action: str) -> str:
    if not action:
        return "Waiting for task"
    if action == "skill.use":
        return "Using skill"
    if action.startswith("browser.") or action.startswith("user."):
        normalized = action.replace("browser.", "").replace("user.", "")
        return " ".join(word[:1].upper() + word[1:] for word in normalized.split("_") if word)
    return action


def _session_action_timestamp(entry: dict[str, Any]) -> str:
    for key in ("emittedAt", "createdAt", "timestamp", "at"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _serialize_session_summary(doc: dict) -> dict:
    action_history = doc.get("actionHistory") if isinstance(doc.get("actionHistory"), list) else []
    chat_history = doc.get("chatHistory") if isinstance(doc.get("chatHistory"), list) else []
    runtime_state = doc.get("runtimeState") if isinstance(doc.get("runtimeState"), dict) else {}
    approved_calls = runtime_state.get("approvedConnectorToolCalls") if isinstance(runtime_state.get("approvedConnectorToolCalls"), list) else []
    browser_action_count = sum(
        1 for item in action_history
        if isinstance(item, dict) and str(item.get("action") or "").startswith("browser.")
    )
    connector_action_count = sum(
        1
        for item in action_history
        if isinstance(item, dict)
        and not str(item.get("action") or "").startswith(("browser.", "router.", "runtime.", "user."))
        and str(item.get("action") or "") not in {"skill.use", "Initialize", "Continue", ""}
    )
    has_browser_activity = browser_action_count > 0
    has_connector_activity = connector_action_count > 0
    source_kind = str(runtime_state.get("sourceKind") or "")
    work_item_id = str(runtime_state.get("workItemId") or "")
    run_id = str(runtime_state.get("runId") or "")
    credits_spent = float(runtime_state.get("creditsSpent") or 0.0)
    runtime_kind = "hybrid" if has_browser_activity and has_connector_activity else "browser" if has_browser_activity else "api"
    latest_action = ""
    latest_activity_at = ""
    for item in reversed(action_history):
        if isinstance(item, dict):
            if not latest_activity_at:
                latest_activity_at = _session_action_timestamp(item)
            latest_action = str(item.get("action") or "")
            if latest_action:
                break
    return {
        "sessionId": doc.get("sessionId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "prompt": doc.get("prompt", ""),
        "initialUrl": doc.get("initialUrl", ""),
        "lastUrl": doc.get("lastUrl", ""),
        "createdAt": doc.get("createdAt"),
        "provider": doc.get("provider", "autoppia"),
        "agentId": doc.get("agentId", ""),
        "agentName": doc.get("agentName", ""),
        "runtimeState": runtime_state,
        "actionCount": len(action_history),
        "chatCount": len(chat_history),
        "runtimeKind": runtime_kind,
        "browserActionCount": browser_action_count,
        "connectorActionCount": connector_action_count,
        "hasBrowserActivity": has_browser_activity,
        "hasConnectorActivity": has_connector_activity,
        "matchedSkillId": str(runtime_state.get("matchedSkillId") or ""),
        "matchedSkillName": str(runtime_state.get("matchedSkillName") or runtime_state.get("matchedSkill") or ""),
        "approvedConnectorToolCalls": approved_calls,
        "approvedConnectorToolCallCount": len(approved_calls),
        "pendingConnectorApproval": str(runtime_state.get("pendingConnectorApproval") or ""),
        "sourceKind": source_kind,
        "workItemId": work_item_id,
        "runId": run_id,
        "creditsSpent": credits_spent,
        "latestAction": latest_action,
        "latestActivityLabel": _pretty_session_action(latest_action),
        "latestActivityAt": latest_activity_at,
    }


async def _ensure_session_access(session_id: str, email: str) -> dict:
    session = await sessions_collection.find_one({"sessionId": session_id}, {"_id": 0})
    if session and session.get("email") and session.get("email") != email:
        raise HTTPException(status_code=403, detail="Session belongs to another user")
    return session or {}


class SessionSaveRequest(BaseModel):
    sessionId: str
    email: str
    companyId: str = ""
    prompt: str
    initialUrl: str = ""
    chatHistory: List[Any] = Field(default_factory=list)
    lastUrl: str = ""
    actionHistory: List[Any] = Field(default_factory=list)
    runtimeState: dict[str, Any] = Field(default_factory=dict)
    contextId: str = ""
    provider: str = "autoppia"
    agentId: str = ""
    agentName: str = ""


class ChatHistoryRequest(BaseModel):
    chatHistory: List[Any]
    lastUrl: str = ""
    actionHistory: List[Any] = Field(default_factory=list)
    runtimeState: dict[str, Any] = Field(default_factory=dict)


class PromoteSessionDocumentRequest(BaseModel):
    email: str
    companyId: str
    source: str = "session_document"


class SessionArtifactCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    title: str = "Artifact"
    artifactType: str = "markdown"
    content: str = ""
    fileName: str = ""
    sourceTool: str = "artifacts.create"
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/sessions")
async def get_sessions(email: str, companyId: str = ""):
    """Get user session history sorted by most recent."""
    try:
        query = {"email": email}
        if companyId:
            query["companyId"] = companyId
        cursor = sessions_collection.find(query).sort("createdAt", -1)
        sessions = []
        async for doc in cursor:
            summary = _serialize_session_summary(doc)
            session_id = summary.get("sessionId", "")
            artifact_query = {"sessionId": session_id, "email": email}
            pending_approval_query = {"sessionId": session_id, "email": email, "status": "pending"}
            summary["artifactCount"] = await artifacts_collection.count_documents(artifact_query)
            summary["pendingApprovalCount"] = await approvals_collection.count_documents(pending_approval_query)
            sessions.append(summary)
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/save")
async def save_session(body: SessionSaveRequest):
    """Create or update a session entry (upsert by sessionId)."""
    try:
        now = datetime.now(timezone.utc)
        update_fields = {
            "email": body.email,
            "companyId": body.companyId,
            "prompt": body.prompt,
            "initialUrl": body.initialUrl,
            "chatHistory": body.chatHistory,
        }
        if body.lastUrl:
            update_fields["lastUrl"] = body.lastUrl
        if body.actionHistory:
            update_fields["actionHistory"] = body.actionHistory
        update_fields["runtimeState"] = body.runtimeState
        if body.contextId:
            update_fields["contextId"] = body.contextId
        if body.provider:
            update_fields["provider"] = body.provider
        if body.agentId:
            update_fields["agentId"] = body.agentId
        if body.agentName:
            update_fields["agentName"] = body.agentName

        result = await sessions_collection.update_one(
            {"sessionId": body.sessionId},
            {
                "$set": update_fields,
                "$setOnInsert": {"sessionId": body.sessionId, "createdAt": now},
            },
            upsert=True,
        )
        return {
            "success": True,
            "created": result.upserted_id is not None,
            "sessionId": body.sessionId,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, email: str = "", companyId: str = ""):
    """Get a single session by its ID, including chat history."""
    try:
        doc = await sessions_collection.find_one({"sessionId": session_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Session not found")
        if email and doc.get("email") and doc.get("email") != email:
            raise HTTPException(status_code=403, detail="Session belongs to another user")
        if companyId and doc.get("companyId", "") != companyId:
            raise HTTPException(status_code=404, detail="Session not found")
        summary = _serialize_session_summary(doc)
        scoped_email = email or str(doc.get("email") or "")
        artifact_query = {"sessionId": session_id, "email": scoped_email}
        pending_approval_query = {"sessionId": session_id, "email": scoped_email, "status": "pending"}
        return {
            "session": {
                **summary,
                "socketioPath": doc.get("socketioPath", ""),
                "sessionPath": doc.get("sessionPath", ""),
                "chatHistory": doc.get("chatHistory", []),
                "actionHistory": doc.get("actionHistory", []),
                "contextId": doc.get("contextId", ""),
                "artifactCount": await artifacts_collection.count_documents(artifact_query),
                "pendingApprovalCount": await approvals_collection.count_documents(pending_approval_query),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/documents")
async def list_session_documents(session_id: str, email: str):
    await _ensure_session_access(session_id, email)
    cursor = session_documents_collection.find({"sessionId": session_id, "email": email}, {"_id": 0, "storagePath": 0}).sort("createdAt", -1)
    return {"documents": [_serialize_session_document(doc) async for doc in cursor]}


@router.get("/sessions/{session_id}/artifacts")
async def list_session_artifacts(session_id: str, email: str):
    await _ensure_session_access(session_id, email)
    cursor = artifacts_collection.find({"sessionId": session_id, "email": email}, {"_id": 0}).sort("createdAt", -1)
    return {"artifacts": [_serialize_session_artifact(doc) async for doc in cursor]}


@router.post("/sessions/{session_id}/artifacts")
async def create_session_artifact(session_id: str, body: SessionArtifactCreateRequest):
    await _ensure_session_access(session_id, body.email)
    artifact_type = _clean_artifact_type(body.artifactType)
    now = datetime.now(timezone.utc).isoformat()
    title = re.sub(r"\s+", " ", str(body.title or "Artifact").strip())[:160] or "Artifact"
    doc = {
        "artifactId": str(uuid.uuid4()),
        "sessionId": session_id,
        "companyId": body.companyId,
        "email": body.email,
        "title": title,
        "name": title,
        "artifactType": artifact_type,
        "kind": artifact_type,
        "content": body.content or "",
        "contentType": ARTIFACT_TEXT_TYPES.get(artifact_type, ARTIFACT_TEXT_TYPES["text"])[0],
        "fileName": _artifact_file_name(title, artifact_type, body.fileName),
        "sourceTool": body.sourceTool or "artifacts.create",
        "metadata": body.metadata,
        "createdAt": now,
        "updatedAt": now,
    }
    await artifacts_collection.insert_one(dict(doc))
    return {"success": True, "artifact": _serialize_session_artifact(doc)}


@router.get("/sessions/{session_id}/artifacts/{artifact_id}/download")
async def download_session_artifact(session_id: str, artifact_id: str, email: str):
    await _ensure_session_access(session_id, email)
    doc = await artifacts_collection.find_one({"sessionId": session_id, "artifactId": artifact_id, "email": email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session artifact not found")
    artifact = _serialize_session_artifact(doc)
    if artifact.get("url"):
        raise HTTPException(status_code=400, detail="Remote artifact should be opened from its URL")
    headers = {"Content-Disposition": f'attachment; filename="{artifact["fileName"]}"'}
    return Response(content=artifact.get("content", ""), media_type=artifact.get("contentType") or "text/plain; charset=utf-8", headers=headers)


@router.post("/sessions/{session_id}/documents")
async def upload_session_document(
    session_id: str,
    email: str = Form(...),
    companyId: str = Form(""),
    source: str = Form("session_upload"),
    file: UploadFile = File(...),
):
    await _ensure_session_access(session_id, email)
    filename = _safe_filename(file.filename or "document")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")

    now = datetime.now(timezone.utc).isoformat()
    document_id = str(uuid.uuid4())
    session_dir = SESSION_DOCUMENT_STORAGE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    storage_path = session_dir / f"{document_id}-{filename}"
    storage_path.write_bytes(content)

    doc = {
        "documentId": document_id,
        "sessionId": session_id,
        "email": email,
        "companyId": companyId,
        "filename": filename,
        "contentType": file.content_type or "application/octet-stream",
        "size": len(content),
        "status": "uploaded",
        "source": source or "session_upload",
        "storagePath": str(storage_path),
        "createdAt": now,
        "updatedAt": now,
    }
    await session_documents_collection.insert_one(dict(doc))
    return {"success": True, "document": _serialize_session_document(doc)}


@router.get("/sessions/{session_id}/documents/{document_id}/download")
async def download_session_document(session_id: str, document_id: str, email: str):
    await _ensure_session_access(session_id, email)
    doc = await session_documents_collection.find_one({"sessionId": session_id, "documentId": document_id, "email": email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session document not found")
    storage_path = Path(str(doc.get("storagePath") or ""))
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(status_code=404, detail="Stored session document file not found")
    return FileResponse(
        path=str(storage_path),
        media_type=doc.get("contentType") or "application/octet-stream",
        filename=doc.get("filename") or storage_path.name,
    )


@router.post("/sessions/{session_id}/documents/{document_id}/promote-to-knowledge")
async def promote_session_document_to_knowledge(session_id: str, document_id: str, body: PromoteSessionDocumentRequest):
    await _ensure_session_access(session_id, body.email)
    doc = await session_documents_collection.find_one({"sessionId": session_id, "documentId": document_id, "email": body.email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session document not found")
    storage_path = Path(str(doc.get("storagePath") or ""))
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(status_code=404, detail="Stored session document file not found")

    knowledge_doc = await create_knowledge_document_record(
        email=body.email,
        company_id=body.companyId,
        filename=doc.get("filename") or "document",
        content=storage_path.read_bytes(),
        content_type=doc.get("contentType") or "application/octet-stream",
        source=body.source or "session_document",
        metadata={"sessionId": session_id, "sessionDocumentId": document_id},
    )
    now = datetime.now(timezone.utc).isoformat()
    await session_documents_collection.update_one(
        {"sessionId": session_id, "documentId": document_id},
        {"$set": {"status": "promoted", "knowledgeDocumentId": knowledge_doc.get("documentId", ""), "updatedAt": now}},
    )
    return {
        "success": True,
        "document": _serialize_session_document({**doc, "status": "promoted", "knowledgeDocumentId": knowledge_doc.get("documentId", ""), "updatedAt": now}),
        "knowledgeDocument": {
            "documentId": knowledge_doc.get("documentId", ""),
            "filename": knowledge_doc.get("filename", ""),
            "size": knowledge_doc.get("size", 0),
        },
    }


@router.delete("/sessions/{session_id}/documents/{document_id}")
async def delete_session_document(session_id: str, document_id: str, email: str):
    await _ensure_session_access(session_id, email)
    doc = await session_documents_collection.find_one({"sessionId": session_id, "documentId": document_id, "email": email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session document not found")
    storage_path = doc.get("storagePath")
    if storage_path:
        try:
            Path(storage_path).unlink(missing_ok=True)
        except OSError:
            pass
    await session_documents_collection.delete_one({"sessionId": session_id, "documentId": document_id})
    return {"success": True}


@router.delete("/sessions/all")
async def delete_all_sessions(email: str):
    """Delete all sessions for a user."""
    try:
        result = await sessions_collection.delete_many({"email": email})
        return {"success": True, "deleted": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}/history")
async def save_chat_history(session_id: str, body: ChatHistoryRequest):
    """Save chat history for a session."""
    try:
        update_fields: dict = {"chatHistory": body.chatHistory}
        if body.lastUrl:
            update_fields["lastUrl"] = body.lastUrl
        if body.actionHistory:
            update_fields["actionHistory"] = body.actionHistory
        update_fields["runtimeState"] = body.runtimeState

        result = await sessions_collection.update_one(
            {"sessionId": session_id},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
