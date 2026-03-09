import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from browserbase import Browserbase
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import profiles_collection

logger = logging.getLogger(__name__)
router = APIRouter()


class ProfileCreateRequest(BaseModel):
    email: str
    name: str


class ProfileUpdateRequest(BaseModel):
    name: str


class ProfileRunResponse(BaseModel):
    liveUrl: str
    sessionId: str


@router.get("/profiles")
async def get_profiles(email: str):
    """Get all profiles for a user."""
    try:
        cursor = profiles_collection.find({"email": email}).sort("createdAt", -1)
        profiles = []
        async for doc in cursor:
            profiles.append({
                "id": str(doc["_id"]),
                "name": doc["name"],
                "contextId": doc["contextId"],
                "createdAt": doc.get("createdAt"),
            })
        return {"profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles")
async def create_profile(body: ProfileCreateRequest):
    """Create a new profile with a BrowserBase context."""
    try:
        bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")

        context_id = ""
        if bb_api_key and bb_project_id:
            bb = Browserbase(api_key=bb_api_key)
            context = bb.contexts.create(project_id=bb_project_id)
            context_id = context.id
            logger.info(f"Created BrowserBase context: {context_id}")

        now = datetime.now(timezone.utc)
        doc = {
            "email": body.email,
            "name": body.name,
            "contextId": context_id,
            "createdAt": now,
        }
        result = await profiles_collection.insert_one(doc)
        return {
            "success": True,
            "profile": {
                "id": str(result.inserted_id),
                "name": body.name,
                "contextId": context_id,
                "createdAt": now,
            },
        }
    except Exception as e:
        logger.error(f"Failed to create profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileUpdateRequest):
    """Update a profile's name."""
    from bson import ObjectId

    try:
        result = await profiles_collection.update_one(
            {"_id": ObjectId(profile_id)},
            {"$set": {"name": body.name}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Active profile sessions: profile_id -> { bb_client, bb_session_id }
_active_profile_sessions: dict = {}


@router.post("/profiles/{profile_id}/run")
async def run_profile(profile_id: str):
    """Launch a BrowserBase session with this profile's context for interactive use."""
    from bson import ObjectId

    try:
        doc = await profiles_collection.find_one({"_id": ObjectId(profile_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")

        context_id = doc.get("contextId", "")
        if not context_id:
            raise HTTPException(status_code=400, detail="Profile has no BrowserBase context")

        bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")
        if not bb_api_key or not bb_project_id:
            raise HTTPException(status_code=500, detail="BrowserBase credentials not configured")

        bb = Browserbase(api_key=bb_api_key)
        session = bb.sessions.create(
            project_id=bb_project_id,
            keep_alive=True,
            api_timeout=900,
            browser_settings={
                "context": {"id": context_id, "persist": True},
                "viewport": {"width": 1280, "height": 720},
            },
        )

        debug_urls = bb.sessions.debug(session.id)
        live_url = debug_urls.debugger_fullscreen_url

        # Track active session so we can release it later
        _active_profile_sessions[profile_id] = {
            "bb_client": bb,
            "bb_session_id": session.id,
        }

        logger.info(f"Profile {profile_id} session started: {session.id}")
        return {"liveUrl": live_url, "sessionId": session.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles/{profile_id}/stop")
async def stop_profile(profile_id: str):
    """Release the BrowserBase session for this profile and wait for context to persist."""
    try:
        active = _active_profile_sessions.pop(profile_id, None)
        if not active:
            return {"success": True, "message": "No active session"}

        bb = active["bb_client"]
        bb_session_id = active["bb_session_id"]
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")

        try:
            bb.sessions.update(
                bb_session_id,
                project_id=bb_project_id,
                status="REQUEST_RELEASE",
            )
            logger.info(f"Profile session release requested: {bb_session_id}")

            # Wait for session to reach COMPLETED status so context is persisted
            for _ in range(15):
                await asyncio.sleep(1)
                try:
                    session_info = bb.sessions.retrieve(bb_session_id)
                    logger.info(f"Session {bb_session_id} status: {session_info.status}")
                    if session_info.status in ("COMPLETED", "ERROR", "TIMED_OUT"):
                        break
                except Exception as e:
                    logger.warning(f"Failed to check session status: {e}")
                    break
        except Exception as e:
            logger.warning(f"Failed to release profile session: {e}")

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """Delete a profile and its BrowserBase context."""
    from bson import ObjectId

    try:
        doc = await profiles_collection.find_one({"_id": ObjectId(profile_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Delete the BrowserBase context
        context_id = doc.get("contextId", "")
        if context_id:
            bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
            if bb_api_key:
                try:
                    bb = Browserbase(api_key=bb_api_key)
                    bb.contexts.delete(context_id)
                    logger.info(f"Deleted BrowserBase context: {context_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete BrowserBase context: {e}")

        await profiles_collection.delete_one({"_id": ObjectId(profile_id)})
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
