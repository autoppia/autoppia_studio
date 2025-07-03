import json
import logging
import socketio
import tempfile
from pathlib import Path

from app.utils.browser_manager import get_browser
from operators.openai import OpenAIOperator
from operators.browser_use import BrowserUseOperator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio)

sessions = {}

storage_state_dir = Path(tempfile.gettempdir()) / "automata" / "storage_states"
storage_state_dir.mkdir(parents=True, exist_ok=True)
history_gif_dir = Path(tempfile.gettempdir()) / "automata" / "history"
history_gif_dir.mkdir(parents=True, exist_ok=True)

@sio.on("connect")
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.on("start-task")
async def start_task(sid, data):
    task = data.get("task")
    initial_url = data.get("initial_url")
    storage_state = data.get("storage_state")
    provider = data.get("provider")
    if not task:
        await sio.emit("error", {"message": "No task provided"}, to=sid)
        return
    
    logger.info(f"Starting task: {task}, Initial URL: {initial_url}")

    if storage_state:
        storage_state_path = storage_state_dir / f"{sid}.json"
        with open(storage_state_path, "w") as storage_state_file:
            json.dump(storage_state, storage_state_file, indent=4)
    else:
        storage_state_path = None

    if provider == "openai":
        operator = OpenAIOperator()
    elif provider == "browser_use":
        operator = BrowserUseOperator()
    else:
        operator = BrowserUseOperator()

    browser = get_browser()
    await operator.initialize(browser, task, initial_url, storage_state_path)

    sessions[sid] = operator
    await _perform_task(sid)

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

    operator.add_new_task(task)
    await _perform_task(sid)

@sio.on("disconnect")
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")


async def _perform_task(sid, max_steps=25):
    operator = sessions[sid]

    for _ in range(max_steps):
        done, valid = await operator.take_step()

        screenshot = await operator.take_screenshot()
        if screenshot:
            await sio.emit('screenshot', {'screenshot': screenshot}, to=sid)

        model_thought = operator.get_model_thought()
        if not model_thought:
            continue

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