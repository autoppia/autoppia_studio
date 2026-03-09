import uuid
import asyncio
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from operators.autoppia_operator import AutoppiaOperator
from operators.browser_use_operator import BrowserUseOperator

router = APIRouter()

tasks = {}

home_dir = Path.home()
history_gif_dir = home_dir / ".automata" / "history"
history_gif_dir.mkdir(parents=True, exist_ok=True)

class TaskRequest(BaseModel):
    task: str
    initial_url: str = None
    provider: Literal["autoppia", "browser_use"] = "autoppia"

class TaskResponse(BaseModel):
    task_id: str

class TaskDetails(BaseModel):
    id: str
    task: str
    initial_url: str | None
    provider: Literal["autoppia", "browser_use"]
    status: str
    steps: list[dict]
    output: str | None

class TaskStatus(BaseModel):
    status: str

class TaskScreenshots(BaseModel):
    screenshots: list[str]

class TaskGif(BaseModel):
    gif: str


@router.post("/run-task", tags=["Operator"], response_model=TaskResponse)
async def run_task(request: TaskRequest):
    task = request.task
    initial_url = request.initial_url
    provider = request.provider

    if not task:
        raise HTTPException(status_code=400, detail="No task provided")
    
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "id": task_id,
        "task": task,
        "initial_url": initial_url,
        "provider": provider,
        "status": "pending",
        "screenshots": [],
        "steps": [],
        "gif": None,
        "output": None,
    }

    asyncio.create_task(_perform_task(task_id))

    return {"task_id": task_id}

@router.get("/task/{task_id}", tags=["Operator"], response_model=TaskDetails)
async def get_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "id": task["id"],
        "task": task["task"],
        "initial_url": task["initial_url"],
        "provider": task["provider"],
        "status": task["status"],
        "steps": task["steps"],
        "output": task["output"],
    }

@router.get("/task/{task_id}/status", tags=["Operator"], response_model=TaskStatus)
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"status": task["status"]}

@router.get("/task/{task_id}/screenshots", tags=["Operator"], response_model=TaskScreenshots)
async def get_task_screenshots(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"screenshots": task["screenshots"]}

@router.get("/task/{task_id}/gif", tags=["Operator"], response_model=TaskGif)
async def get_task_gif(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"gif": task["gif"]}

async def _perform_task(task_id: str, max_steps: int = 25):
    tasks[task_id]["status"] = "running"

    task = tasks[task_id].get("task")
    initial_url = tasks[task_id].get("initial_url")
    provider = tasks[task_id].get("provider")

    if provider == "browser_use":
        operator = BrowserUseOperator()
    else:
        operator = AutoppiaOperator()

    await operator.initialize(task, initial_url)

    # Wire up per-action callback so screenshots and steps are collected
    # after each individual action, not just per step.
    if isinstance(operator, AutoppiaOperator):
        async def on_action(action_type: str, screenshot: str | None, success: bool):
            if screenshot:
                tasks[task_id]["screenshots"].append(screenshot)
            tasks[task_id]["steps"].append({
                "action": action_type,
                "success": success,
            })

        operator.set_on_action(on_action)

    # Capture the initial page screenshot after navigation
    screenshot = await operator.take_screenshot()
    if screenshot:
        tasks[task_id]["screenshots"].append(screenshot)

    for _ in range(max_steps):
        done, valid = await operator.take_step()

        # For operators without per-action callback, collect per-step data
        if not isinstance(operator, AutoppiaOperator):
            screenshot = await operator.take_screenshot()
            if screenshot:
                tasks[task_id]["screenshots"].append(screenshot)

            model_thought = operator.get_model_thought()
            if model_thought:
                tasks[task_id]["steps"].append(model_thought)

        if done and valid:
            break

    screenshot = await operator.take_screenshot()
    if screenshot:
        tasks[task_id]["screenshots"].append(screenshot)

    gif = operator.generate_gif(history_gif_dir / f"{task_id}.gif")
    tasks[task_id]["gif"] = gif

    result = operator.get_result()
    tasks[task_id]["output"] = result.get("content")
    tasks[task_id]["status"] = "completed" if result.get("success") else "failed"

    await operator.close()
