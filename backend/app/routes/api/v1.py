import uuid
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.utils.browser_manager import get_browser
from operators.openai import OpenAIOperator
from operators.browser_use import BrowserUseOperator

router = APIRouter()

tasks = {}

class TaskRequest(BaseModel):
    task: str
    initial_url: str = None
    provider: Literal["browser_use", "openai"] = "browser_use"

class TaskResponse(BaseModel):
    task_id: str

class TaskDetails(BaseModel):
    id: str
    task: str
    initial_url: str
    provider: Literal["browser_use", "openai"]
    status: str
    steps: list
    output: str | None

class TaskStatus(BaseModel):
    status: str

class TaskScreenshots(BaseModel):
    screenshots: list

class TaskGif(BaseModel):
    gif: str

@router.post("/run-task", response_model=TaskResponse)
async def run_task(request: TaskRequest):
    task = request.get("task")
    initial_url = request.get("initial_url")
    provider = request.get("provider")

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

@router.get("/task/{task_id}", response_model=TaskDetails)
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

@router.get("/task/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"status": task["status"]}

@router.get("/task/{task_id}/screenshots", response_model=TaskScreenshots)
async def get_task_screenshots(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"screenshots": task["screenshots"]}

@router.get("/task/{task_id}/gif", response_model=TaskGif)
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

    if provider == "openai":
        operator = OpenAIOperator()
    elif provider == "browser_use":
        operator = BrowserUseOperator()
    else:
        operator = BrowserUseOperator()

    browser = get_browser()
    await operator.initialize(browser, task, initial_url)

    for _ in range(max_steps):
        done, valid = await operator.take_step()

        screenshot = await operator.take_screenshot()
        if screenshot:
            tasks[task_id]["screenshots"].append(screenshot)
            
        model_thought = operator.get_model_thought()
        if model_thought:
            tasks[task_id]["step"].append(model_thought)

        if done and valid:
            break

    screenshot = await operator.take_screenshot()
    if screenshot:
        tasks[task_id]["screenshots"].append(screenshot)

    gif = await operator.generate_gif()
    if gif:
        tasks[task_id]["gif"] = gif

    result = await operator.get_result()
    if result["output"]:
        tasks[task_id]["output"] = result["content"]
    if result["success"]:
        tasks[task_id]["status"] = "completed"
    else:
        tasks[task_id]["status"] = "failed"

    await operator.close()


    
