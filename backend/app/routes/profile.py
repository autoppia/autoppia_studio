import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from browserbase import Browserbase
from playwright.async_api import async_playwright
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


# Active profile sessions: profile_id -> { bb_client, bb_session_id, playwright, browser, context }
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

        # Connect via Playwright CDP so we can open new tabs programmatically
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(session.connect_url)
        context = browser.contexts[0] if browser.contexts else None

        # Build tabs list from pages
        tabs = []
        for p in debug_urls.pages:
            tabs.append({
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "favicon_url": p.favicon_url,
                "debugger_fullscreen_url": p.debugger_fullscreen_url,
            })

        # Track active session so we can release it later
        _active_profile_sessions[profile_id] = {
            "bb_client": bb,
            "bb_session_id": session.id,
            "playwright": pw,
            "browser": browser,
            "context": context,
        }

        logger.info(f"Profile {profile_id} session started: {session.id}")
        return {
            "liveUrl": live_url,
            "sessionId": session.id,
            "tabs": tabs,
        }
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

        # Clean up Playwright connection
        pw = active.get("playwright")
        browser = active.get("browser")
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception as e:
            logger.warning(f"Failed to close Playwright: {e}")

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


class NewTabRequest(BaseModel):
    url: Optional[str] = None


@router.post("/profiles/{profile_id}/new-tab")
async def new_tab(profile_id: str, body: NewTabRequest = NewTabRequest()):
    """Open a new tab in the active profile browser session and return updated tabs."""
    active = _active_profile_sessions.get(profile_id)
    if not active:
        raise HTTPException(status_code=400, detail="No active session for this profile")

    bb: Browserbase = active["bb_client"]
    bb_session_id = active["bb_session_id"]
    context = active.get("context")

    try:
        # Open a new page via Playwright
        if context:
            new_page = await context.new_page()
            url = body.url or "about:blank"
            if url and url != "about:blank":
                await new_page.goto(url, timeout=15000)

        # Wait briefly for BrowserBase to register the new page
        await asyncio.sleep(1.0)

        # Re-fetch debug info to get updated pages with debug URLs
        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append({
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "favicon_url": p.favicon_url,
                "debugger_fullscreen_url": p.debugger_fullscreen_url,
            })

        return {
            "tabs": tabs,
            "activeIndex": len(tabs) - 1,
        }
    except Exception as e:
        logger.error(f"Failed to open new tab: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class CloseTabRequest(BaseModel):
    tab_index: int


@router.post("/profiles/{profile_id}/close-tab")
async def close_tab(profile_id: str, body: CloseTabRequest):
    """Close a tab in the active profile browser session and return updated tabs."""
    active = _active_profile_sessions.get(profile_id)
    if not active:
        raise HTTPException(status_code=400, detail="No active session for this profile")

    bb: Browserbase = active["bb_client"]
    bb_session_id = active["bb_session_id"]
    context = active.get("context")

    try:
        if context and 0 <= body.tab_index < len(context.pages):
            page = context.pages[body.tab_index]
            await page.close()

        await asyncio.sleep(0.5)

        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append({
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "favicon_url": p.favicon_url,
                "debugger_fullscreen_url": p.debugger_fullscreen_url,
            })

        active_index = min(body.tab_index, len(tabs) - 1) if tabs else 0
        return {
            "tabs": tabs,
            "activeIndex": active_index,
        }
    except Exception as e:
        logger.error(f"Failed to close tab: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/{profile_id}/tabs")
async def get_profile_tabs(profile_id: str):
    """Get the current tabs for an active profile browser session."""
    active = _active_profile_sessions.get(profile_id)
    if not active:
        raise HTTPException(status_code=400, detail="No active session for this profile")

    bb: Browserbase = active["bb_client"]
    bb_session_id = active["bb_session_id"]

    try:
        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append({
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "favicon_url": p.favicon_url,
                "debugger_fullscreen_url": p.debugger_fullscreen_url,
            })
        return {"tabs": tabs, "activeIndex": 0}
    except Exception as e:
        logger.error(f"Failed to get tabs: {e}", exc_info=True)
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
