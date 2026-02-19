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

        # Send initial screenshot and action after navigation
        try:
            screenshot = await operator.take_screenshot()
            if screenshot:
                await sio.emit('screenshot', {'screenshot': screenshot}, to=sid)
            await sio.emit('action', {'action': f'NavigateAction', 'previous_success': True}, to=sid)
        except Exception:
            pass

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

    await operator.add_new_task(task)
    await _perform_task(sid)

@sio.on("disconnect")
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    operator = sessions.get(sid)
    if operator:
        await operator.close()
        del sessions[sid]


async def _perform_task(sid, max_steps=25):
    operator = sessions[sid]

    # Wire up per-action callback for AutoppiaOperator so the frontend
    # receives a screenshot + action description after every single action
    # instead of waiting for the entire step to finish.
    if isinstance(operator, AutoppiaOperator):
        async def on_action(action_type: str, screenshot: str | None, success: bool):
            if screenshot:
                await sio.emit('screenshot', {'screenshot': screenshot}, to=sid)
            await sio.emit('action', {
                'action': action_type,
                'previous_success': success,
            }, to=sid)

        operator.set_on_action(on_action)

    try:
        for _ in range(max_steps):
            done, valid = await operator.take_step()

            # For operators without per-action callback (e.g. BrowserUseOperator),
            # still emit per-step updates as before.
            if not isinstance(operator, AutoppiaOperator):
                screenshot = await operator.take_screenshot()
                if screenshot:
                    await sio.emit('screenshot', {'screenshot': screenshot}, to=sid)

                model_thought = operator.get_model_thought()
                if model_thought:
                    next_goal = model_thought['next_goal']
                    previous_success = model_thought['previous_success']
                    await sio.emit('action', {'action': next_goal, 'previous_success': previous_success}, to=sid)

            if done and valid:
                break

        screenshot = await operator.take_screenshot()
        if screenshot:
            await sio.emit('screenshot', {'screenshot': screenshot}, to=sid)
        result = operator.get_result()
        await sio.emit('result', result, to=sid)
    except Exception as e:
        logger.error(f"Error in _perform_task: {e}", exc_info=True)
        await sio.emit('error', {'message': str(e)}, to=sid)