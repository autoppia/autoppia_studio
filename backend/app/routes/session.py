import uuid
from datetime import datetime, timezone
from typing import List, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import sessions_collection

router = APIRouter()


class SessionSaveRequest(BaseModel):
    email: str
    socketioPath: str
    prompt: str
    initialUrl: str
    sessionPath: str


class ChatHistoryRequest(BaseModel):
    chatHistory: List[Any]
    lastUrl: str = ""
    actionHistory: List[Any] = []


@router.get("/sessions")
async def get_sessions(email: str):
    """Get user session history sorted by most recent."""
    try:
        cursor = sessions_collection.find({"email": email}).sort("createdAt", -1)
        sessions = []
        async for doc in cursor:
            sessions.append({
                "sessionId": doc.get("sessionId", ""),
                "email": doc["email"],
                "socketioPath": doc.get("socketioPath", ""),
                "prompt": doc["prompt"],
                "initialUrl": doc.get("initialUrl", ""),
                "sessionPath": doc.get("sessionPath", doc.get("historyPath", "")),
                "createdAt": doc.get("createdAt"),
            })
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/save")
async def save_session(body: SessionSaveRequest):
    """Save a new session entry."""
    try:
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        doc = {
            "sessionId": session_id,
            "email": body.email,
            "socketioPath": body.socketioPath,
            "prompt": body.prompt,
            "initialUrl": body.initialUrl,
            "sessionPath": body.sessionPath,
            "createdAt": created_at,
        }
        await sessions_collection.insert_one(doc)
        return {
            "session": {
                "sessionId": session_id,
                "email": body.email,
                "socketioPath": body.socketioPath,
                "prompt": body.prompt,
                "initialUrl": body.initialUrl,
                "sessionPath": body.sessionPath,
                "createdAt": created_at.isoformat(),
            }
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
            }
        }
    except HTTPException:
        raise
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
