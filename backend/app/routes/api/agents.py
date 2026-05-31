from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import capabilities_collection, operators_collection

router = APIRouter()


class AgentActRequest(BaseModel):
    task: str = ""
    prompt: str = ""
    url: str = ""
    snapshot_html: str = ""
    history: list[Any] = []
    state_in: dict[str, Any] | None = None
    context: dict[str, Any] = {}


def _act_url(endpoint: str) -> str:
    clean = endpoint.rstrip("/")
    if not clean:
        return ""
    return clean if clean.endswith("/act") else f"{clean}/act"


def _serialize_agent(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "operatorId": doc.get("operatorId", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeType": doc.get("runtimeType", ""),
        "status": doc.get("status", ""),
        "trainingStatus": doc.get("trainingStatus", ""),
        "apiSpecUrl": doc.get("apiSpecUrl", ""),
        "apiAuthConfigured": bool(doc.get("apiAuth", {}).get("headerValueConfigured")),
    }


async def _load_operator(operator_id: str) -> dict[str, Any]:
    operator = await operators_collection.find_one({"operatorId": operator_id}, {"_id": 0})
    if not operator:
        raise HTTPException(status_code=404, detail="Agent not found")
    return operator


@router.get("/agents/{operator_id}", tags=["Agents"])
async def get_agent(operator_id: str):
    operator = await _load_operator(operator_id)
    return {"agent": _serialize_agent(operator)}


@router.get("/agents/{operator_id}/skills", tags=["Agents"])
async def list_agent_skills(operator_id: str):
    await _load_operator(operator_id)
    cursor = capabilities_collection.find({"operatorId": operator_id}, {"_id": 0}).sort("createdAt", 1)
    return {"skills": await cursor.to_list(length=500)}


@router.post("/agents/{operator_id}/act", tags=["Agents"])
async def agent_act(operator_id: str, body: AgentActRequest):
    operator = await _load_operator(operator_id)
    endpoint = _act_url(str(operator.get("runtimeEndpoint") or ""))
    if not endpoint:
        raise HTTPException(status_code=409, detail="Agent runtime is not deployed yet")

    prompt = (body.prompt or body.task).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="task or prompt is required")

    payload = body.model_dump()
    payload["prompt"] = prompt
    payload["task"] = prompt

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(endpoint, json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Agent runtime request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"runtimeStatus": response.status_code, "body": response.text})

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    return {
        "operatorId": operator_id,
        "operatorName": operator.get("name", ""),
        "runtimeEndpoint": endpoint,
        "result": data,
    }
