from typing import Any

from fastapi import APIRouter, Body

from app.services.agent_runtime import agent_step_result

router = APIRouter()


@router.get("/runtime/agents/{agent_id}/health")
async def runtime_agent_health(agent_id: str):
    return {"status": "ok", "agentId": agent_id}


@router.post("/runtime/agents/{agent_id}/step")
async def runtime_agent_step(agent_id: str, payload: dict[str, Any] = Body(...)):
    return await agent_step_result(agent_id, payload)
