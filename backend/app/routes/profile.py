import os
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from browserbase import Browserbase
from playwright.async_api import async_playwright
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from bson import ObjectId

from app.database import profiles_collection

logger = logging.getLogger(__name__)
router = APIRouter()


class ProfileCreateRequest(BaseModel):
    email: str
    name: str
    provider: str = ""


class ProfileUpdateRequest(BaseModel):
    name: str


class ProfileRunResponse(BaseModel):
    liveUrl: str
    sessionId: str


class ProfileRunRequest(BaseModel):
    initialUrl: str = "https://www.amazon.com/"
    provider: str = ""


def _local_profile_root() -> Path:
    root = Path(os.getenv("AUTOMATA_LOCAL_PROFILE_DIR", str(Path.home() / ".automata" / "profiles"))).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_context_id(profile_id: str) -> str:
    profile_dir = _local_profile_root() / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    return f"local:{profile_dir / 'storage_state.json'}"


def _local_storage_path(context_id: str) -> Path | None:
    prefix = "local:"
    if not str(context_id or "").startswith(prefix):
        return None
    path = Path(str(context_id)[len(prefix) :]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _requested_provider(value: str = "") -> str:
    provider = (value or os.getenv("AUTOMATA_PROFILE_PROVIDER", "local")).strip().lower()
    if provider not in {"local", "browserbase", "auto"}:
        provider = "local"
    return provider


@router.get("/profiles")
async def get_profiles(email: str):
    """Get all profiles for a user."""
    try:
        cursor = profiles_collection.find({"email": email}).sort("createdAt", -1)
        profiles = []
        async for doc in cursor:
            profiles.append(
                {
                    "id": str(doc["_id"]),
                    "name": doc["name"],
                    "contextId": doc["contextId"],
                    "profileProvider": doc.get("profileProvider", "browserbase" if doc.get("contextId") and not str(doc.get("contextId")).startswith("local:") else "local"),
                    "createdAt": doc.get("createdAt"),
                }
            )
        return {"profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles")
async def create_profile(body: ProfileCreateRequest):
    """Create a new profile with a BrowserBase context."""
    try:
        bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")

        provider = _requested_provider(body.provider)
        use_browserbase = provider in {"browserbase", "auto"} and bool(bb_api_key and bb_project_id)

        context_id = ""
        if use_browserbase:
            bb = Browserbase(api_key=bb_api_key)
            context = bb.contexts.create(project_id=bb_project_id)
            context_id = context.id
            logger.info(f"Created BrowserBase context: {context_id}")

        now = datetime.now(timezone.utc)
        profile_id = ObjectId()
        if not context_id:
            context_id = _local_context_id(str(profile_id))
        doc = {
            "_id": profile_id,
            "email": body.email,
            "name": body.name,
            "contextId": context_id,
            "profileProvider": "browserbase" if use_browserbase else "local",
            "createdAt": now,
        }
        result = await profiles_collection.insert_one(doc)
        return {
            "success": True,
            "profile": {
                "id": str(profile_id),
                "name": body.name,
                "contextId": context_id,
                "profileProvider": "browserbase" if use_browserbase else "local",
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
async def run_profile(profile_id: str, body: ProfileRunRequest = ProfileRunRequest()):
    """Launch a BrowserBase session with this profile's context for interactive use."""
    try:
        doc = await profiles_collection.find_one({"_id": ObjectId(profile_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")

        context_id = doc.get("contextId", "")
        if not context_id:
            raise HTTPException(status_code=400, detail="Profile has no BrowserBase context")

        provider = _requested_provider(body.provider or str(doc.get("profileProvider") or ""))
        local_storage_path = _local_storage_path(context_id)
        if provider == "local" or local_storage_path is not None:
            if local_storage_path is None:
                context_id = _local_context_id(profile_id)
                local_storage_path = _local_storage_path(context_id)
                await profiles_collection.update_one(
                    {"_id": ObjectId(profile_id)},
                    {"$set": {"contextId": context_id, "profileProvider": "local"}},
                )
            pw = await async_playwright().start()
            launch_kwargs = {
                "headless": False,
                "args": ["--start-maximized"],
            }
            channel = os.getenv("AUTOMATA_PROFILE_BROWSER_CHANNEL", "chrome").strip()
            if channel:
                launch_kwargs["channel"] = channel
            try:
                browser = await pw.chromium.launch(**launch_kwargs)
            except Exception as exc:
                logger.warning(f"Failed to launch browser channel {channel!r}, falling back to bundled Chromium: {exc}")
                launch_kwargs.pop("channel", None)
                browser = await pw.chromium.launch(**launch_kwargs)
            storage_state = str(local_storage_path) if local_storage_path.exists() else None
            context = await browser.new_context(viewport={"width": 1440, "height": 900}, storage_state=storage_state)
            page = await context.new_page()
            if body.initialUrl:
                await page.goto(body.initialUrl, timeout=30000)
            _active_profile_sessions[profile_id] = {
                "provider": "local",
                "playwright": pw,
                "browser": browser,
                "context": context,
                "storage_state_path": local_storage_path,
            }
            logger.info(f"Local profile {profile_id} session started with storage state {local_storage_path}")
            return {
                "liveUrl": "",
                "sessionId": f"local:{profile_id}",
                "provider": "local",
                "message": "Local browser window opened. Use /stop to persist storage state.",
                "tabs": [{"id": "0", "url": page.url, "title": "Local browser", "favicon_url": "", "debugger_fullscreen_url": ""}],
            }

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
            tabs.append(
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "favicon_url": p.favicon_url,
                    "debugger_fullscreen_url": p.debugger_fullscreen_url,
                }
            )

        # Track active session so we can release it later
        _active_profile_sessions[profile_id] = {
            "provider": "browserbase",
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

        if active.get("provider") == "local":
            pw = active.get("playwright")
            browser = active.get("browser")
            context = active.get("context")
            storage_state_path = active.get("storage_state_path")
            try:
                if context and storage_state_path:
                    await context.storage_state(path=str(storage_state_path))
                    logger.info(f"Saved local profile storage state: {storage_state_path}")
                if browser:
                    await browser.close()
                if pw:
                    await pw.stop()
            except Exception as e:
                logger.warning(f"Failed to stop local profile session cleanly: {e}")
            return {"success": True, "provider": "local", "storageStatePath": str(storage_state_path or "")}

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

    context = active.get("context")

    try:
        # Open a new page via Playwright
        if context:
            new_page = await context.new_page()
            url = body.url or ""
            if url:
                await new_page.goto(url, timeout=15000)
            else:
                await new_page.set_content("<html><head><title>New Tab</title></head><body></body></html>")

        if active.get("provider") == "local":
            pages = context.pages if context else []
            return {
                "tabs": [
                    {
                        "id": str(index),
                        "url": page.url if not page.is_closed() else "",
                        "title": page.url if not page.is_closed() else "",
                        "favicon_url": "",
                        "debugger_fullscreen_url": "",
                    }
                    for index, page in enumerate(pages)
                ],
                "activeIndex": max(len(pages) - 1, 0),
            }

        bb: Browserbase = active["bb_client"]
        bb_session_id = active["bb_session_id"]

        # Wait briefly for BrowserBase to register the new page
        await asyncio.sleep(1.0)

        # Re-fetch debug info to get updated pages with debug URLs
        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append(
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "favicon_url": p.favicon_url,
                    "debugger_fullscreen_url": p.debugger_fullscreen_url,
                }
            )

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

    context = active.get("context")

    try:
        if context and 0 <= body.tab_index < len(context.pages):
            page = context.pages[body.tab_index]
            await page.close()

        if active.get("provider") == "local":
            pages = context.pages if context else []
            active_index = min(body.tab_index, len(pages) - 1) if pages else 0
            return {
                "tabs": [
                    {
                        "id": str(index),
                        "url": page.url if not page.is_closed() else "",
                        "title": page.url if not page.is_closed() else "",
                        "favicon_url": "",
                        "debugger_fullscreen_url": "",
                    }
                    for index, page in enumerate(pages)
                ],
                "activeIndex": active_index,
            }

        bb: Browserbase = active["bb_client"]
        bb_session_id = active["bb_session_id"]

        await asyncio.sleep(0.5)

        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append(
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "favicon_url": p.favicon_url,
                    "debugger_fullscreen_url": p.debugger_fullscreen_url,
                }
            )

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

    try:
        if active.get("provider") == "local":
            context = active.get("context")
            pages = context.pages if context else []
            return {
                "tabs": [
                    {
                        "id": str(index),
                        "url": page.url if not page.is_closed() else "",
                        "title": page.url if not page.is_closed() else "",
                        "favicon_url": "",
                        "debugger_fullscreen_url": "",
                    }
                    for index, page in enumerate(pages)
                ],
                "activeIndex": 0,
            }

        bb: Browserbase = active["bb_client"]
        bb_session_id = active["bb_session_id"]
        debug_urls = bb.sessions.debug(bb_session_id)
        tabs = []
        for p in debug_urls.pages:
            tabs.append(
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "favicon_url": p.favicon_url,
                    "debugger_fullscreen_url": p.debugger_fullscreen_url,
                }
            )
        return {"tabs": tabs, "activeIndex": 0}
    except Exception as e:
        logger.error(f"Failed to get tabs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """Delete a profile and its BrowserBase context."""
    try:
        doc = await profiles_collection.find_one({"_id": ObjectId(profile_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Delete the BrowserBase context
        context_id = doc.get("contextId", "")
        local_storage_path = _local_storage_path(context_id)
        if local_storage_path is not None:
            try:
                if local_storage_path.exists():
                    local_storage_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete local profile storage state: {e}")
        elif context_id:
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
