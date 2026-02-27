import asyncio
import logging
import socketio
from pathlib import Path

from operators.autoppia_operator import AutoppiaOperator
from operators.browser_use_operator import BrowserUseOperator

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
    provider = data.get("provider")
    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return

    logger.info(f"Starting task: {task}, Initial URL: {initial_url}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        if provider == "browser_use":
            operator = BrowserUseOperator()
        else:
            operator = AutoppiaOperator()

        await operator.initialize(task, initial_url, storage_state_path)

        sessions[sid] = operator

        # Send the Browserbase live URL to the frontend for iframe embedding
        live_url = operator.get_live_url()
        if live_url:
            await sio.emit('live_url', {'url': live_url}, to=sid)

        # Only emit initial NavigateAction for AutoppiaOperator;
        # BrowserUseOperator handles its own navigation internally.
        if isinstance(operator, AutoppiaOperator):
            await sio.emit('action', {'action': 'NavigateAction', 'previous_success': True}, to=sid)

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
    provider = data.get("provider", "autoppia")

    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return
    if not last_url:
        await sio.emit("error", {"message": "No lastUrl provided for resume"}, to=sid)
        return

    logger.info(f"Resuming task: {task}, Last URL: {last_url}, History steps: {len(action_history)}")

    storage_state_path = storage_state_dir / "automata.json"
    if not storage_state_path.exists():
        storage_state_path = None

    try:
        if provider == "browser_use":
            operator = BrowserUseOperator()
        else:
            operator = AutoppiaOperator()

        # Initialize with the saved lastUrl as the starting URL
        await operator.initialize(task, last_url, storage_state_path)

        # Pre-load action history so CUA has context of previous actions
        if isinstance(operator, AutoppiaOperator) and action_history:
            operator.history = action_history
            operator.step_index = len(action_history)

        sessions[sid] = operator

        live_url = operator.get_live_url()
        if live_url:
            await sio.emit('live_url', {'url': live_url}, to=sid)

        if isinstance(operator, AutoppiaOperator):
            await sio.emit('action', {'action': 'Resuming from previous session...', 'previous_success': True}, to=sid)

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


async def _keepalive_loop(sid, interval=30):
    """Periodically ping the browser to keep the Browserbase session alive."""
    try:
        while True:
            await asyncio.sleep(interval)
            operator = sessions.get(sid)
            if not operator:
                break
            if isinstance(operator, AutoppiaOperator):
                alive = await operator.browser_executor.keep_alive_ping()
                if not alive:
                    logger.warning(f"Keep-alive ping failed for {sid}, stopping loop")
                    break
    except asyncio.CancelledError:
        pass


async def _perform_task(sid, max_steps=25):
    operator = sessions[sid]

    # Wire up per-action callback for AutoppiaOperator so the frontend
    # receives action descriptions after every single action.
    if isinstance(operator, AutoppiaOperator):
        async def on_action(action_type: str, screenshot: str | None, success: bool):
            payload = {
                'action': action_type,
                'previous_success': success,
            }
            if screenshot:
                payload['screenshot'] = screenshot
            await sio.emit('action', payload, to=sid)

        operator.set_on_action(on_action)

    try:
        for _ in range(max_steps):
            done, _valid = await operator.take_step()

            # For operators without per-action callback (e.g. BrowserUseOperator),
            # still emit per-step action updates with screenshots.
            if not isinstance(operator, AutoppiaOperator):
                model_thought = operator.get_model_thought()
                if model_thought:
                    next_goal = model_thought['next_goal']
                    previous_success = model_thought['previous_success']
                    payload = {'action': next_goal, 'previous_success': previous_success}
                    try:
                        screenshot = await operator.take_screenshot()
                        if screenshot:
                            payload['screenshot'] = screenshot
                    except Exception as e:
                        logger.warning(f"Failed to take screenshot: {e}")
                    await sio.emit('action', payload, to=sid)

            if done:
                break

        result = operator.get_result()

        # Attach lastUrl and actionHistory for session persistence and resume
        if isinstance(operator, AutoppiaOperator):
            result['lastUrl'] = operator.browser_executor.get_current_url()
            result['actionHistory'] = operator.history
        else:
            try:
                result['lastUrl'] = await operator.get_current_url()
            except Exception as e:
                logger.warning(f"Failed to get current URL: {e}")

        await sio.emit('result', result, to=sid)

        # Start keep-alive pings to prevent Browserbase session from timing out
        old_task = keepalive_tasks.pop(sid, None)
        if old_task:
            old_task.cancel()
        keepalive_tasks[sid] = asyncio.create_task(_keepalive_loop(sid))
    except Exception as e:
        logger.error(f"Error in _perform_task: {e}", exc_info=True)
        await sio.emit('error', {'message': str(e)}, to=sid)