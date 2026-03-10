import asyncio
import logging
import socketio
from pathlib import Path

from agent.autoppia_operator import AutoppiaOperator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*", ping_timeout=120, ping_interval=25)
socket_app = None  # Will be set in main.py after FastAPI app is created

sessions = {}
keepalive_tasks = {}  # sid -> asyncio.Task for browser keep-alive pings

home_dir = Path.home()
storage_state_dir = home_dir / ".automata" / "storage_states"
storage_state_dir.mkdir(parents=True, exist_ok=True)

@sio.on("connect")
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.on("start-task")
async def start_task(sid, data):
    task = data.get("task")
    initial_url = data.get("initial_url")
    context_id = data.get("context_id", "")
    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return

    logger.info(f"Starting task: {task}, Initial URL: {initial_url}, Context ID: {context_id}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        # Notify frontend of initial navigation before browser launches
        await sio.emit('action', {
            'action': 'browser.navigate',
            'reasoning': f'Navigating to {initial_url or "https://duckduckgo.com"}...',
            'previous_success': True,
        }, to=sid)

        operator = AutoppiaOperator()
        await operator.initialize(task, initial_url, storage_state_path, context_id=context_id)

        sessions[sid] = operator

        # Send the Browserbase live URL to the frontend for iframe embedding
        live_url = operator.get_live_url()
        if live_url:
            await sio.emit('live_url', {'url': live_url}, to=sid)

        # Send initial tabs list
        await _emit_tabs(sid, operator)

        await _perform_task(sid)
    except Exception as e:
        logger.error(f"Error in start_task: {e}", exc_info=True)
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on("continue-task")
async def continue_task(sid, data):
    task = data.get('task')
    if not task:
        await sio.emit('error', {'message': 'No task provided'}, to=sid)
        return

    logger.info(f"Continuing task: {task}")

    operator = sessions.get(sid)
    if not operator:
        await sio.emit('error', {'message': 'No existing session for this sid'}, to=sid)
        return

    await operator.add_new_task(task, preserve_history=True)
    await _perform_task(sid)

@sio.on("resume-task")
async def resume_task(sid, data):
    task = data.get("task")
    last_url = data.get("lastUrl")
    action_history = data.get("actionHistory", [])
    context_id = data.get("context_id", "")

    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return
    if not last_url:
        await sio.emit("error", {"message": "No lastUrl provided for resume"}, to=sid)
        return

    logger.info(f"Resuming task: {task}, Last URL: {last_url}, History steps: {len(action_history)}, Context ID: {context_id}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        # Notify frontend of navigation before browser launches
        await sio.emit('action', {
            'action': 'browser.navigate',
            'reasoning': f'Resuming session at {last_url}...',
            'previous_success': True,
        }, to=sid)

        operator = AutoppiaOperator()

        # Initialize with the saved lastUrl as the starting URL
        await operator.initialize(task, last_url, storage_state_path, context_id=context_id)

        # Pre-load action history so CUA has context of previous actions
        if action_history:
            operator.history = action_history
            operator.step_index = len(action_history)

        sessions[sid] = operator

        live_url = operator.get_live_url()
        if live_url:
            await sio.emit('live_url', {'url': live_url}, to=sid)

        await _emit_tabs(sid, operator)

        await _perform_task(sid)
    except Exception as e:
        logger.error(f"Error in resume_task: {e}", exc_info=True)
        await sio.emit('error', {'message': str(e)}, to=sid)

@sio.on("disconnect")
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    # Cancel any running keep-alive task
    task = keepalive_tasks.pop(sid, None)
    if task:
        task.cancel()
    operator = sessions.get(sid)
    if operator:
        await operator.close()
        await operator.release_session()
        del sessions[sid]


async def _emit_tabs(sid, operator):
    """Emit the current tabs list to the frontend."""
    try:
        be = getattr(operator, 'browser_executor', None)
        if be:
            tabs = be.get_tabs()
            active_index = be.get_active_page_index()
            if tabs:
                await sio.emit('tabs', {'tabs': tabs, 'activeIndex': active_index}, to=sid)
    except Exception as e:
        logger.warning(f"Failed to emit tabs: {e}")


async def _keepalive_loop(sid, interval=30):
    """Periodically ping the browser to keep the Browserbase session alive."""
    try:
        while True:
            await asyncio.sleep(interval)
            operator = sessions.get(sid)
            if not operator:
                break
            alive = await operator.browser_executor.keep_alive_ping()
            if not alive:
                logger.warning(f"Keep-alive ping failed for {sid}, stopping loop")
                break
    except asyncio.CancelledError:
        pass


async def _perform_task(sid, max_steps=25):
    operator = sessions[sid]

    # Emit each action before it executes (with reasoning and previous_success)
    async def on_action(reasoning: str | None, action: str, previous_success: bool):
        payload = {'action': action, 'previous_success': previous_success}
        if reasoning:
            payload['reasoning'] = reasoning
        await sio.emit('action', payload, to=sid)

    operator.set_on_action(on_action)

    # Wire up tab-change callback so frontend updates tab bar on new tab / close
    async def on_tab_change():
        await _emit_tabs(sid, operator)

    operator.browser_executor.set_on_tab_change(on_tab_change)

    try:
        for _ in range(max_steps):
            done, _valid = await operator.take_step()

            if done:
                break

        result = operator.get_result()

        # Attach lastUrl and actionHistory for session persistence and resume
        try:
            result['lastUrl'] = operator.browser_executor.get_current_url()
        except Exception as e:
            logger.warning(f"Failed to get current URL: {e}")
        result['actionHistory'] = operator.history

        await sio.emit('result', result, to=sid)

        # Start keep-alive pings to prevent Browserbase session from timing out
        old_task = keepalive_tasks.pop(sid, None)
        if old_task:
            old_task.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop(sid))
    except Exception as e:
        logger.error(f"Error in _perform_task: {e}", exc_info=True)
        await sio.emit('error', {'message': str(e)}, to=sid)
