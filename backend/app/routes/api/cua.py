import os
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from cua.apified_cua import ApifiedCUA

load_dotenv()

router = APIRouter()

agents = {}


class CUAStartInput(BaseModel):
    task: str
    url: str = "https://google.com"
    snapshot_html: str = ""


class CUAForwardInput(BaseModel):
    snapshot_html: str
    url: str
    step_index: int = 0


@router.post("/cua/start", tags=["CUA"])
async def start(request: CUAStartInput):
    agent_id = str(uuid.uuid4())

    base_url = os.getenv("AUTOPPIA_AGENT_BASE_URL", "")
    if not base_url:
        raise HTTPException(status_code=500, detail="AUTOPPIA_AGENT_BASE_URL not configured")

    cua = ApifiedCUA(base_url=base_url)
    agents[agent_id] = {
        "cua": cua,
        "task": request.task,
        "history": [],
        "step_index": 0,
    }

    actions = await cua.act(
        task_id=agent_id,
        prompt=request.task,
        snapshot_html=request.snapshot_html,
        url=request.url,
        step_index=0,
    )
    agents[agent_id]["step_index"] = 1

    return {"agent_id": agent_id, "actions": [a.model_dump() for a in actions]}


@router.put("/cua/{agent_id}/forward", tags=["CUA"])
async def forward(agent_id: str, request: CUAForwardInput):
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_data = agents[agent_id]
    cua = agent_data["cua"]
    step_index = request.step_index or agent_data["step_index"]

    actions = await cua.act(
        task_id=agent_id,
        prompt=agent_data["task"],
        snapshot_html=request.snapshot_html,
        url=request.url,
        step_index=step_index,
        history=agent_data["history"],
    )
    agent_data["step_index"] = step_index + 1

    return {"agent_id": agent_id, "actions": [a.model_dump() for a in actions]}


@router.put("/cua/{agent_id}/stop", tags=["CUA"])
async def stop(agent_id: str):
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    del agents[agent_id]
    return {}


@router.get("/cua/{agent_id}/gif", tags=["CUA"])
async def gif(agent_id: str):
    return {"agent_id": agent_id, "gif": "Not implemented"}
