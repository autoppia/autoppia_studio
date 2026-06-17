import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.database import session_documents_collection, sessions_collection
from app.routes.knowledge import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, create_knowledge_document_record

router = APIRouter()

SESSION_DOCUMENT_STORAGE_DIR = Path(os.getenv("SESSION_DOCUMENT_STORAGE_DIR", Path.home() / ".automata" / "session_documents"))


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


async def _ensure_session_access(session_id: str, email: str) -> dict:
    session = await sessions_collection.find_one({"sessionId": session_id}, {"_id": 0})
    if session and session.get("email") and session.get("email") != email:
        raise HTTPException(status_code=403, detail="Session belongs to another user")
    return session or {}


class SessionSaveRequest(BaseModel):
    sessionId: str
    email: str
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


@router.get("/sessions")
async def get_sessions(email: str):
    """Get user session history sorted by most recent."""
    try:
        cursor = sessions_collection.find({"email": email}).sort("createdAt", -1)
        sessions = []
        async for doc in cursor:
            sessions.append(
                {
                    "sessionId": doc.get("sessionId", ""),
                    "email": doc["email"],
                    "prompt": doc["prompt"],
                    "initialUrl": doc.get("initialUrl", ""),
                    "createdAt": doc.get("createdAt"),
                }
            )
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
async def get_session(session_id: str):
    """Get a single session by its ID, including chat history."""
    try:
        doc = await sessions_collection.find_one({"sessionId": session_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session": {
                "sessionId": doc.get("sessionId", ""),
                "email": doc["email"],
                "socketioPath": doc.get("socketioPath", ""),
                "prompt": doc["prompt"],
                "initialUrl": doc.get("initialUrl", ""),
                "sessionPath": doc.get("sessionPath", ""),
                "createdAt": doc.get("createdAt"),
                "chatHistory": doc.get("chatHistory", []),
                "lastUrl": doc.get("lastUrl", ""),
                "actionHistory": doc.get("actionHistory", []),
                "runtimeState": doc.get("runtimeState", {}),
                "contextId": doc.get("contextId", ""),
                "provider": doc.get("provider", "autoppia"),
                "agentId": doc.get("agentId", ""),
                "agentName": doc.get("agentName", ""),
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
