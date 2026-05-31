import uuid
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.autoppia_operator import AutoppiaOperator

router = APIRouter()

tasks = {}

home_dir = Path.home()
history_gif_dir = home_dir / ".automata" / "history"
history_gif_dir.mkdir(parents=True, exist_ok=True)


class TaskRequest(BaseModel):
    task: str
    initial_url: str = None


class TaskResponse(BaseModel):
    task_id: str


class TaskDetails(BaseModel):
    id: str
    task: str
    initial_url: str | None
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

    if not task:
        raise HTTPException(status_code=400, detail="No task provided")

    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "id": task_id,
        "task": task,
        "initial_url": initial_url,
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

    operator = AutoppiaOperator()
    try:
        await operator.initialize(task, initial_url)

        async def on_action(action_type: str, screenshot: str | None, success: bool):
            if screenshot:
                tasks[task_id]["screenshots"].append(screenshot)
            tasks[task_id]["steps"].append(
                {
                    "action": action_type,
                    "success": success,
                }
            )

        operator.set_on_action(on_action)

        screenshot = await operator.take_screenshot()
        if screenshot:
            tasks[task_id]["screenshots"].append(screenshot)

        for _ in range(max_steps):
            done, valid = await operator.take_step()
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
    except Exception as exc:
        tasks[task_id]["output"] = f"{exc.__class__.__name__}: {exc}"
        tasks[task_id]["status"] = "failed"
    finally:
        await operator.close()
