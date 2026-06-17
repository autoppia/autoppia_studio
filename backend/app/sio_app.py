import asyncio
import json
import logging
import time
import socketio
from pathlib import Path

from agent.autoppia_agent import AutoppiaAgent, _execute_tool_call
from agent.browser_executor import BrowserExecutor
from app.database import agents_collection, artifacts_collection

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*", ping_timeout=120, ping_interval=25)
socket_app = None  # Will be set in main.py after FastAPI app is created

sessions = {}
keepalive_tasks = {}  # sid -> asyncio.Task for browser keep-alive pings
running_tasks = {}  # sid -> asyncio.Task for the currently running _perform_task
session_metadata = {}  # sid -> {email, companyId}; populated by activity subscription or task payloads

home_dir = Path.home()
storage_state_dir = home_dir / ".automata" / "storage_states"
storage_state_dir.mkdir(parents=True, exist_ok=True)


async def _agent_base_url_for_agent(agent_id: str) -> str:
    if not agent_id:
        return ""
    agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0, "runtimeEndpoint": 1, "status": 1})
    if not agent_config:
        raise ValueError("Selected agent was not found.")
    endpoint = str(agent_config.get("runtimeEndpoint") or "").strip()
    if not endpoint:
        raise ValueError("Selected agent is not deployed yet.")
    return endpoint


@sio.on("connect")
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")


def _activity_room(email: str, company_id: str = "") -> str:
    return f"activity:{email}:{company_id or '_'}"


def active_session_count(email: str = "", company_id: str = "") -> int:
    if not email:
        return len(sessions)
    count = 0
    for sid, metadata in session_metadata.items():
        if metadata.get("email") != email:
            continue
        if company_id and metadata.get("companyId", "") != company_id:
            continue
        if sid in sessions or sid in running_tasks:
            count += 1
    return count


async def emit_activity_event(email: str, company_id: str = "", event: str = "activity-updated", payload: dict | None = None) -> None:
    if not email:
        return
    await sio.emit(event, payload or {}, room=_activity_room(email, company_id))


async def _remember_activity_context(sid: str, data: dict | None) -> None:
    if not isinstance(data, dict):
        return
    email = str(data.get("email") or data.get("userEmail") or "").strip()
    company_id = str(data.get("companyId") or data.get("company_id") or "").strip()
    session_id = str(data.get("session_id") or data.get("sessionId") or "").strip()
    agent_id = str(data.get("agent_id") or data.get("agentId") or "").strip()
    if not email:
        return
    previous = session_metadata.get(sid, {})
    if previous.get("email"):
        await sio.leave_room(sid, _activity_room(previous["email"], previous.get("companyId", "")))
    session_metadata[sid] = {
        **previous,
        "email": email,
        "companyId": company_id or previous.get("companyId", ""),
        "sessionId": session_id or previous.get("sessionId", ""),
        "agentId": agent_id or previous.get("agentId", ""),
    }
    await sio.enter_room(sid, _activity_room(email, company_id))


def _artifact_context(sid: str, data: dict | None = None) -> dict:
    metadata = session_metadata.get(sid, {})
    data = data if isinstance(data, dict) else {}
    return {
        "sessionId": str(data.get("session_id") or data.get("sessionId") or metadata.get("sessionId") or sid),
        "email": str(data.get("email") or data.get("userEmail") or metadata.get("email") or ""),
        "companyId": str(data.get("companyId") or data.get("company_id") or metadata.get("companyId") or ""),
        "agentId": str(data.get("agent_id") or data.get("agentId") or metadata.get("agentId") or ""),
        "agentName": str(data.get("agentName") or data.get("agent_name") or metadata.get("agentName") or ""),
    }


async def _persist_session_artifacts(sid: str, artifacts: list[dict] | None) -> list[dict]:
    context = _artifact_context(sid)
    persisted: list[dict] = []
    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            continue
        doc = {
            **artifact,
            "artifactId": str(artifact.get("artifactId") or ""),
            "sessionId": str(artifact.get("sessionId") or context["sessionId"]),
            "email": str(artifact.get("email") or context["email"]),
            "companyId": str(artifact.get("companyId") or context["companyId"]),
            "agentId": str(artifact.get("agentId") or context["agentId"]),
            "agentName": str(artifact.get("agentName") or context["agentName"]),
        }
        if not doc["artifactId"] or not doc["sessionId"] or not doc["email"]:
            persisted.append(doc)
            continue
        existing = await artifacts_collection.find_one({"artifactId": doc["artifactId"]}, {"_id": 0})
        if not existing:
            await artifacts_collection.insert_one(dict(doc))
        persisted.append(doc)
    return persisted


@sio.on("subscribe-activity")
async def subscribe_activity(sid, data):
    await _remember_activity_context(sid, data)
    metadata = session_metadata.get(sid, {})
    await sio.emit(
        "activity-subscribed",
        {"email": metadata.get("email", ""), "companyId": metadata.get("companyId", "")},
        to=sid,
    )


@sio.on("start-task")
async def start_task(sid, data):
    await _remember_activity_context(sid, data)
    task = data.get("task")
    initial_url = data.get("initial_url")
    context_id = data.get("context_id", "")
    agent_id = data.get("agent_id", "")
    browser_mode = data.get("browser_mode", "")
    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return

    logger.info(f"Starting task: {task}, Initial URL: {initial_url}, Context ID: {context_id}, Agent ID: {agent_id}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        # Notify frontend of initial navigation before browser launches
        await sio.emit(
            "action",
            {
                "action": "browser.navigate",
                "reasoning": f"Navigating to {initial_url}..." if initial_url else "Initializing browser...",
                "previous_success": True,
            },
            to=sid,
        )

        agent_config = AutoppiaAgent()
        if hasattr(agent_config, "set_artifact_context"):
            agent_config.set_artifact_context(_artifact_context(sid, data))
        agent_base_url = await _agent_base_url_for_agent(agent_id)
        await agent_config.initialize(
            task,
            initial_url,
            storage_state_path,
            context_id=context_id,
            agent_base_url=agent_base_url,
            browser_mode=browser_mode,
        )

        sessions[sid] = agent_config

        # Send the Browserbase live URL to the frontend for iframe embedding
        live_url = agent_config.get_live_url()
        if live_url:
            await sio.emit("live_url", {"url": live_url}, to=sid)

        # Send initial tabs list
        await _emit_tabs(sid, agent_config)
        await _emit_initial_screenshot(sid, agent_config)

        running_tasks[sid] = asyncio.create_task(_perform_task(sid))
    except Exception as e:
        logger.error(f"Error in start_task: {e}", exc_info=True)
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.on("continue-task")
async def continue_task(sid, data):
    await _remember_activity_context(sid, data)
    task = data.get("task")
    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return

    logger.info(f"Continuing task: {task}")

    agent_config = sessions.get(sid)
    if not agent_config:
        await sio.emit("error", {"message": "No existing session for this sid"}, to=sid)
        return

    await agent_config.add_new_task(task, preserve_history=True)
    if hasattr(agent_config, "set_artifact_context"):
        agent_config.set_artifact_context(_artifact_context(sid, data))
    running_tasks[sid] = asyncio.create_task(_perform_task(sid))


@sio.on("resume-task")
async def resume_task(sid, data):
    await _remember_activity_context(sid, data)
    task = data.get("task")
    last_url = data.get("lastUrl")
    action_history = data.get("actionHistory", [])
    context_id = data.get("context_id", "")
    agent_id = data.get("agent_id", "")
    runtime_state = data.get("runtimeState") if isinstance(data.get("runtimeState"), dict) else {}

    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return
    if not last_url:
        await sio.emit("error", {"message": "No lastUrl provided for resume"}, to=sid)
        return

    logger.info(
        f"Resuming task: {task}, Last URL: {last_url}, History steps: {len(action_history)}, "
        f"Context ID: {context_id}, Agent ID: {agent_id}"
    )

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        # Notify frontend of navigation before browser launches
        await sio.emit(
            "action",
            {
                "action": "browser.navigate",
                "reasoning": f"Resuming session at {last_url}...",
                "previous_success": True,
            },
            to=sid,
        )

        agent_config = AutoppiaAgent()
        if hasattr(agent_config, "set_artifact_context"):
            agent_config.set_artifact_context(_artifact_context(sid, data))
        agent_base_url = await _agent_base_url_for_agent(agent_id) if agent_id else ""

        # Initialize with the saved lastUrl as the starting URL
        await agent_config.initialize(
            task,
            last_url,
            storage_state_path,
            context_id=context_id,
            agent_base_url=agent_base_url,
            browser_mode=data.get("browser_mode", ""),
        )

        # Pre-load action history so CUA has context of previous actions
        if action_history:
            agent_config.history = action_history
            agent_config.step_index = len(action_history)
        if runtime_state:
            agent_config._state = runtime_state

        sessions[sid] = agent_config

        live_url = agent_config.get_live_url()
        if live_url:
            await sio.emit("live_url", {"url": live_url}, to=sid)

        await _emit_tabs(sid, agent_config)
        await _emit_initial_screenshot(sid, agent_config)

        running_tasks[sid] = asyncio.create_task(_perform_task(sid))
    except Exception as e:
        logger.error(f"Error in resume_task: {e}", exc_info=True)
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.on("stop-task")
async def stop_task(sid, data=None):
    """Stop the running CUA agent but keep the browser session alive."""
    logger.info(f"Stopping task for {sid}")

    # Cancel the running task
    task = running_tasks.pop(sid, None)
    if task:
        task.cancel()

    agent_config = sessions.get(sid)
    result = {
        "content": "Task stopped by user",
        "success": False,
    }
    if agent_config:
        try:
            result["lastUrl"] = agent_config.browser_executor.get_current_url()
        except Exception:
            pass
        result["actionHistory"] = getattr(agent_config, "history", [])
        result["screenshots"] = getattr(agent_config, "screenshots", [])
        result["runtimeState"] = getattr(agent_config, "_state", {})
        result["artifacts"] = await _persist_session_artifacts(sid, result.get("artifacts") or getattr(agent_config, "artifacts", []))

        # Start keep-alive to keep browser session open
        old_ka = keepalive_tasks.pop(sid, None)
        if old_ka:
            old_ka.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop(sid))

    await sio.emit("result", result, to=sid)


@sio.on("play-actions")
async def play_actions(sid, data):
    """Execute a list of recorded actions directly without the AI agent."""
    actions = data.get("actions", [])
    initial_url = data.get("initial_url", "")
    context_id = data.get("context_id", "")
    action_delay = data.get("delay", 1.0)

    if not actions:
        await sio.emit("error", {"message": "No actions provided"}, to=sid)
        return

    logger.info(f"Playing {len(actions)} actions, initial URL: {initial_url}, Context ID: {context_id}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        # Notify frontend of initial navigation
        await sio.emit(
            "action",
            {
                "action": "browser.navigate",
                "reasoning": f"Navigating to {initial_url}...",
                "previous_success": True,
            },
            to=sid,
        )

        agent_config = AutoppiaAgent()
        if hasattr(agent_config, "set_artifact_context"):
            agent_config.set_artifact_context(_artifact_context(sid, data))
        await agent_config.initialize("Skill playback", initial_url, storage_state_path, context_id=context_id, browser_mode=data.get("browser_mode", ""))
        sessions[sid] = agent_config

        live_url = agent_config.get_live_url()
        if live_url:
            await sio.emit("live_url", {"url": live_url}, to=sid)

        await _emit_tabs(sid, agent_config)
        await _emit_initial_screenshot(sid, agent_config)

        # Wire up tab-change callback so frontend updates tab bar on navigation
        async def on_tab_change_play():
            await _emit_tabs(sid, agent_config)

        agent_config.browser_executor.set_on_tab_change(on_tab_change_play)

        page = agent_config.browser_executor.page
        history = []
        previous_success = True

        for i, action_entry in enumerate(actions):
            action_name = action_entry.get("action", "")
            args = action_entry.get("args", {})

            if not action_name or action_name in ("browser.screenshot", "browser.done"):
                continue

            # Skip the first navigate if it matches our initial_url (already navigated)
            if i == 0 and action_name == "browser.navigate" and args.get("url") == initial_url:
                continue

            # Emit action event before execution
            await sio.emit(
                "action",
                {
                    "action": action_name,
                    "reasoning": f"Step {i + 1}: executing {action_name}",
                    "previous_success": previous_success,
                },
                to=sid,
            )

            tool_call = {"name": action_name, "arguments": args}
            try:
                await _execute_tool_call(page, tool_call)
                previous_success = True
                history.append({"step_index": i, "tool_call": tool_call})
            except Exception as e:
                logger.error(f"Error executing {action_name}: {e}")
                previous_success = False
                history.append({"step_index": i, "tool_call": tool_call, "error": str(e)})

            # Wait between actions
            await asyncio.sleep(action_delay)

        # Emit final result
        result = {
            "content": "Skill playback completed",
            "success": previous_success,
        }
        try:
            result["lastUrl"] = agent_config.browser_executor.get_current_url()
        except Exception:
            pass
        result["actionHistory"] = history
        result["screenshots"] = getattr(agent_config, "screenshots", [])
        result["runtimeState"] = getattr(agent_config, "_state", {})
        result["artifacts"] = await _persist_session_artifacts(sid, result.get("artifacts") or getattr(agent_config, "artifacts", []))

        await sio.emit("result", result, to=sid)

        # Start keep-alive
        old_task = keepalive_tasks.pop(sid, None)
        if old_task:
            old_task.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop(sid))

    except Exception as e:
        logger.error(f"Error in play_actions: {e}", exc_info=True)
        await sio.emit("error", {"message": str(e)}, to=sid)


RECORDER_SCRIPT = """
(function() {
  if (window.__recorder_installed) return;
  window.__recorder_installed = true;

  function cssSelector(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    var parts = [];
    while (el && el !== document.body && el !== document.documentElement) {
      var sel = el.tagName.toLowerCase();
      if (el.id) { parts.unshift('#' + CSS.escape(el.id)); break; }
      if (el.className && typeof el.className === 'string') {
        var cls = el.className.trim().split(/\\s+/).filter(function(c) {
          return c && !c.startsWith('hover') && !c.startsWith('focus') && c.length < 40;
        }).slice(0, 2);
        if (cls.length) sel += '.' + cls.map(function(c) { return CSS.escape(c); }).join('.');
      }
      var parent = el.parentElement;
      if (parent) {
        var siblings = Array.from(parent.children).filter(function(c) { return c.tagName === el.tagName; });
        if (siblings.length > 1) sel += ':nth-of-type(' + (siblings.indexOf(el) + 1) + ')';
      }
      parts.unshift(sel);
      el = el.parentElement;
    }
    return parts.join(' > ');
  }

  var CLICKABLE = 'a, button, [role="button"], [role="tab"], [role="menuitem"], [role="option"], [role="link"], [type="submit"], [type="checkbox"], [type="radio"], summary';

  function isTextInput(el) {
    if (el.tagName === 'TEXTAREA' || el.isContentEditable) return true;
    if (el.tagName === 'INPUT') {
      var t = (el.type || 'text').toLowerCase();
      return ['text','password','email','search','tel','url','number'].indexOf(t) !== -1;
    }
    return false;
  }

  var dirtyFields = {};

  // Click: only record when landing on a recognized interactive element
  document.addEventListener('click', function(e) {
    var el = e.target;
    // Skip text inputs — typing handles those
    if (isTextInput(el)) return;
    // Find the nearest clickable ancestor
    var target = el.closest(CLICKABLE);
    if (!target) return;  // Not a meaningful click — skip
    window.__recordAction(JSON.stringify({
      action: 'browser.click',
      args: { css_selector: cssSelector(target) }
    }));
  }, true);

  // Track typing — mark dirty, emit on blur or Enter
  document.addEventListener('input', function(e) {
    var el = e.target;
    if (isTextInput(el)) {
      dirtyFields[cssSelector(el)] = el;
    }
  }, true);

  // Emit text input on blur (user finished typing and left the field)
  document.addEventListener('focusout', function(e) {
    var el = e.target;
    if (!isTextInput(el)) return;
    var selector = cssSelector(el);
    if (!dirtyFields[selector]) return;
    delete dirtyFields[selector];
    var value = el.value || el.textContent || '';
    if (!value) return;
    window.__recordAction(JSON.stringify({
      action: 'browser.input',
      args: { css_selector: selector, text: value }
    }));
  }, true);

  // Dropdown / select changes
  document.addEventListener('change', function(e) {
    var el = e.target;
    if (el.tagName === 'SELECT') {
      var label = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
      window.__recordAction(JSON.stringify({
        action: 'browser.select_dropdown',
        args: { css_selector: cssSelector(el), label: label }
      }));
    }
  }, true);

  // Enter key — flush pending input then record Enter
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var el = e.target;
      if (isTextInput(el)) {
        var selector = cssSelector(el);
        if (dirtyFields[selector]) {
          delete dirtyFields[selector];
          var value = el.value || el.textContent || '';
          if (value) {
            window.__recordAction(JSON.stringify({
              action: 'browser.input',
              args: { css_selector: selector, text: value }
            }));
          }
        }
      }
      if (!el.matches('textarea')) {
        window.__recordAction(JSON.stringify({
          action: 'browser.send_keys',
          args: { keys: 'Enter' }
        }));
      }
    }
  }, true);
})();
"""

# Store recorded actions per sid
recording_actions = {}


@sio.on("start-record")
async def start_record(sid, data):
    initial_url = data.get("initial_url", "")
    context_id = data.get("context_id", "")

    logger.info(f"Starting recording for {sid}, initial URL: {initial_url}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        await sio.emit(
            "action",
            {
                "action": "browser.navigate",
                "reasoning": f"Opening {initial_url}...",
                "previous_success": True,
            },
            to=sid,
        )

        be = BrowserExecutor()
        await be.initialize(initial_url=initial_url, storage_state_path=storage_state_path, context_id=context_id, browser_mode=data.get("browser_mode", ""))

        sessions[sid] = {"browser_executor": be, "recording": True}
        recording_actions[sid] = []

        live_url = be.get_live_url()
        if live_url:
            await sio.emit("live_url", {"url": live_url}, to=sid)

        # Emit initial tabs
        tabs = be.get_tabs()
        active_index = be.get_active_page_index()
        if tabs:
            await sio.emit("tabs", {"tabs": tabs, "activeIndex": active_index}, to=sid)

        # Add the initial navigate as the first action (only if a URL was provided)
        if initial_url:
            recording_actions[sid].append({"action": "browser.navigate", "args": {"url": initial_url}})
            await sio.emit(
                "recorded-action",
                {
                    "action": "browser.navigate",
                    "args": {"url": initial_url},
                    "index": 0,
                },
                to=sid,
            )

        # Use raw CDP to inject recorder — Playwright's expose_function/add_init_script
        # don't work reliably over remote CDP connections (Browserbase).
        page = be.page
        cdp = await page.context.new_cdp_session(page)

        # Enable required CDP domains
        await cdp.send("Runtime.enable")
        await cdp.send("Page.enable")

        # Register a JS binding via CDP — this survives navigations
        await cdp.send("Runtime.addBinding", {"name": "__recordAction"})

        # Inject recorder script on every new document load via CDP
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": RECORDER_SCRIPT})

        # Also run on the current page immediately
        await cdp.send("Runtime.evaluate", {"expression": RECORDER_SCRIPT})

        # Deduplication: track timestamp of last click
        last_click_time = {"t": 0}

        def _is_duplicate(action_data, actions):
            """Skip if identical to the last recorded action."""
            if not actions:
                return False
            last = actions[-1]
            return last.get("action") == action_data.get("action") and last.get("args") == action_data.get("args")

        # Listen for binding calls from the injected script
        async def on_binding_called(params):
            if params.get("name") != "__recordAction":
                return
            try:
                action_data = json.loads(params.get("payload", "{}"))
                actions = recording_actions.get(sid, [])
                # Skip consecutive duplicates
                if _is_duplicate(action_data, actions):
                    return
                if action_data.get("action") == "browser.click":
                    last_click_time["t"] = time.monotonic()
                actions.append(action_data)
                await sio.emit(
                    "recorded-action",
                    {
                        **action_data,
                        "index": len(actions) - 1,
                    },
                    to=sid,
                )
                logger.info(f"Recorded action #{len(actions)}: {action_data.get('action')}")
            except Exception as e:
                logger.error(f"Error processing recorded action: {e}")

        cdp.on("Runtime.bindingCalled", lambda params: asyncio.create_task(on_binding_called(params)))

        # Store CDP session so it doesn't get GC'd
        sessions[sid]["cdp"] = cdp

        # Track navigations via Playwright events — but suppress navigates
        # caused by a recent click (the click already captures the intent)
        async def on_frame_navigated(frame):
            try:
                p = frame.page
                if frame != p.main_frame:
                    return
                url = p.url
                # Skip about:blank and browser-internal URLs
                if not url or url == "about:blank" or url.startswith("chrome"):
                    return

                # Update tab titles/URLs on every main-frame navigation
                await asyncio.sleep(0.5)
                await emit_record_tabs()

                actions = recording_actions.get(sid, [])
                # Skip if same URL as last navigate
                if actions and actions[-1].get("action") == "browser.navigate" and actions[-1].get("args", {}).get("url") == url:
                    return
                # Suppress navigate if a click happened within the last 2s (click caused it)
                if time.monotonic() - last_click_time["t"] < 2.0:
                    return
                nav_action = {"action": "browser.navigate", "args": {"url": url}}
                actions.append(nav_action)
                await sio.emit("recorded-action", {**nav_action, "index": len(actions) - 1}, to=sid)
            except Exception:
                pass

        page.on("framenavigated", lambda frame: asyncio.create_task(on_frame_navigated(frame)))

        # Helper: emit current tabs list to frontend
        async def emit_record_tabs():
            try:
                tab_list = be.get_tabs()
                active_idx = be.get_active_page_index()
                if tab_list:
                    await sio.emit("tabs", {"tabs": tab_list, "activeIndex": active_idx}, to=sid)
            except Exception as e:
                logger.warning(f"Failed to emit record tabs: {e}")

        # Handle new tabs opened by user interaction
        async def on_new_page_record(new_page):
            be.page = new_page
            # Set up CDP recorder for the new page too
            try:
                new_cdp = await new_page.context.new_cdp_session(new_page)
                await new_cdp.send("Runtime.enable")
                await new_cdp.send("Page.enable")
                await new_cdp.send("Runtime.addBinding", {"name": "__recordAction"})
                await new_cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": RECORDER_SCRIPT})
                await new_cdp.send("Runtime.evaluate", {"expression": RECORDER_SCRIPT})
                new_cdp.on("Runtime.bindingCalled", lambda params: asyncio.create_task(on_binding_called(params)))
            except Exception as e:
                logger.warning(f"Failed to set up recorder on new page: {e}")

            new_page.on("framenavigated", lambda frame: asyncio.create_task(on_frame_navigated(frame)))

            # Emit tabs update
            await asyncio.sleep(0.5)
            await emit_record_tabs()

        be.context.on("page", on_new_page_record)

        # Emit initial tabs
        await emit_record_tabs()

        # Start keep-alive
        old_task = keepalive_tasks.pop(sid, None)
        if old_task:
            old_task.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop_record(sid))

    except Exception as e:
        logger.error(f"Error in start_record: {e}", exc_info=True)
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.on("new-tab-record")
async def new_tab_record(sid, data=None):
    """Open a new tab in the recording browser session."""
    session_data = sessions.get(sid)
    if not session_data or not isinstance(session_data, dict) or not session_data.get("recording"):
        return

    be = session_data.get("browser_executor")
    if not be:
        return

    try:
        await be.open_new_tab()

        # Record the action
        actions = recording_actions.get(sid, [])
        new_tab_action = {"action": "browser.new_tab", "args": {}}
        actions.append(new_tab_action)
        await sio.emit("recorded-action", {**new_tab_action, "index": len(actions) - 1}, to=sid)

        # Emit updated tabs
        await asyncio.sleep(0.5)
        tab_list = be.get_tabs()
        active_idx = be.get_active_page_index()
        if tab_list:
            await sio.emit("tabs", {"tabs": tab_list, "activeIndex": active_idx}, to=sid)

        logger.info(f"New tab opened for recording session {sid}")
    except Exception as e:
        logger.error(f"Error opening new tab in recording: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.on("switch-tab-record")
async def switch_tab_record(sid, data):
    """Switch to a different tab in the recording browser session."""
    session_data = sessions.get(sid)
    if not session_data or not isinstance(session_data, dict) or not session_data.get("recording"):
        return

    be = session_data.get("browser_executor")
    if not be or not be.context:
        return

    index = data.get("index", 0) if data else 0
    pages = be.context.pages
    if index < 0 or index >= len(pages):
        return

    try:
        be.page = pages[index]

        # Record the action
        actions = recording_actions.get(sid, [])
        switch_action = {"action": "browser.switch_tab", "args": {"tab_index": index}}
        actions.append(switch_action)
        await sio.emit("recorded-action", {**switch_action, "index": len(actions) - 1}, to=sid)

        # Emit updated tabs with new active index
        tab_list = be.get_tabs()
        if tab_list:
            await sio.emit("tabs", {"tabs": tab_list, "activeIndex": index}, to=sid)

        logger.info(f"Switched to tab {index} for recording session {sid}")
    except Exception as e:
        logger.error(f"Error switching tab in recording: {e}")
        await sio.emit("error", {"message": str(e)}, to=sid)


@sio.on("stop-record")
async def stop_record(sid, data=None):
    logger.info(f"Stopping recording for {sid}")

    actions = recording_actions.pop(sid, [])
    session_data = sessions.get(sid)

    last_url = ""
    if session_data and isinstance(session_data, dict) and session_data.get("recording"):
        be = session_data.get("browser_executor")
        if be:
            try:
                last_url = be.get_current_url()
            except Exception:
                pass

    # Cancel keep-alive
    task = keepalive_tasks.pop(sid, None)
    if task:
        task.cancel()

    await sio.emit(
        "record-result",
        {
            "actions": actions,
            "lastUrl": last_url,
        },
        to=sid,
    )


async def _keepalive_loop_record(sid, interval=30):
    """Keep-alive loop for recording sessions."""
    try:
        while True:
            await asyncio.sleep(interval)
            session_data = sessions.get(sid)
            if not session_data:
                break
            be = session_data.get("browser_executor") if isinstance(session_data, dict) else getattr(session_data, "browser_executor", None)
            if be:
                alive = await be.keep_alive_ping()
                if not alive:
                    logger.warning(f"Record keep-alive ping failed for {sid}")
                    break
    except asyncio.CancelledError:
        pass


@sio.on("disconnect")
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    # Cancel any running CUA task
    rt = running_tasks.pop(sid, None)
    if rt:
        rt.cancel()
    # Cancel any running keep-alive task
    task = keepalive_tasks.pop(sid, None)
    if task:
        task.cancel()
    # Clean up recording actions
    recording_actions.pop(sid, None)
    session_metadata.pop(sid, None)
    session_data = sessions.get(sid)
    if session_data:
        if isinstance(session_data, dict) and session_data.get("recording"):
            be = session_data.get("browser_executor")
            if be:
                await be.close()
                await be.release_session()
        else:
            await session_data.close()
            await session_data.release_session()
        del sessions[sid]


async def _emit_tabs(sid, agent_config):
    """Emit the current tabs list to the frontend."""
    try:
        be = getattr(agent_config, "browser_executor", None)
        if be:
            tabs = be.get_tabs()
            active_index = be.get_active_page_index()
            if tabs:
                await sio.emit("tabs", {"tabs": tabs, "activeIndex": active_index}, to=sid)
    except Exception as e:
        logger.warning(f"Failed to emit tabs: {e}")


async def _emit_initial_screenshot(sid, agent_config):
    """Emit one local browser screenshot after initialization.

    Local Playwright sessions do not have a Browserbase live URL. Some approved
    skills complete through API/tool replay without any browser action, so this
    keeps the Browser tab useful instead of showing the startup loader forever.
    """
    try:
        screenshot = await agent_config.take_screenshot()
        if not screenshot:
            return
        screenshots = getattr(agent_config, "screenshots", None)
        if isinstance(screenshots, list) and screenshot not in screenshots:
            screenshots.append(screenshot)
        await sio.emit("screenshot", {"screenshot": screenshot}, to=sid)
    except Exception as e:
        logger.warning(f"Failed to emit initial screenshot: {e}")


async def _keepalive_loop(sid, interval=30):
    """Periodically ping the browser to keep the Browserbase session alive."""
    try:
        while True:
            await asyncio.sleep(interval)
            agent_config = sessions.get(sid)
            if not agent_config:
                break
            alive = await agent_config.browser_executor.keep_alive_ping()
            if not alive:
                logger.warning(f"Keep-alive ping failed for {sid}, stopping loop")
                break
    except asyncio.CancelledError:
        pass


async def _perform_task(sid, max_steps=25):
    agent_config = sessions[sid]

    # Emit each action before it executes (with reasoning and previous_success)
    async def on_action(reasoning: str | None, action: str, previous_success: bool, metadata: dict | None = None):
        payload = {"action": action, "previous_success": previous_success}
        if reasoning:
            payload["reasoning"] = reasoning
        if metadata:
            payload.update(metadata)
        await sio.emit("action", payload, to=sid)

    agent_config.set_on_action(on_action)

    async def on_screenshot(screenshot: str):
        await sio.emit("screenshot", {"screenshot": screenshot}, to=sid)

    agent_config.set_on_screenshot(on_screenshot)

    # Wire up tab-change callback so frontend updates tab bar on new tab / close
    async def on_tab_change():
        await _emit_tabs(sid, agent_config)

    agent_config.browser_executor.set_on_tab_change(on_tab_change)

    try:
        # Check CUA availability before running steps
        if not await agent_config.cua.health_check():
            await sio.emit("error", {"message": "Agent is not working. Please try again later."}, to=sid)
            return

        for _ in range(max_steps):
            done, _valid = await agent_config.take_step()

            if done:
                break

        result = agent_config.get_result()

        # Attach lastUrl and actionHistory for session persistence and resume
        try:
            result["lastUrl"] = agent_config.browser_executor.get_current_url()
        except Exception as e:
            logger.warning(f"Failed to get current URL: {e}")
        result["actionHistory"] = agent_config.history
        result["screenshots"] = agent_config.screenshots or []
        result["runtimeState"] = getattr(agent_config, "_state", {})
        result["artifacts"] = await _persist_session_artifacts(sid, result.get("artifacts") or getattr(agent_config, "artifacts", []))

        await sio.emit("result", result, to=sid)

        # Start keep-alive pings to prevent Browserbase session from timing out
        old_task = keepalive_tasks.pop(sid, None)
        if old_task:
            old_task.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop(sid))
    except asyncio.CancelledError:
        logger.info(f"Task cancelled for {sid}")
    except Exception as e:
        logger.error(f"Error in _perform_task: {e}", exc_info=True)
        await sio.emit("error", {"message": str(e)}, to=sid)
    finally:
        running_tasks.pop(sid, None)
