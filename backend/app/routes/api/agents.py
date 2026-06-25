import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import agents_collection, capabilities_collection
from app.api_errors import api_error
from app.middleware import verify_api_key
from app.services.observability import record_runtime_event
from app.services.agent_runtime import step_url as _step_url
from app.services.agent_runtime import agent_step_result, runtime_contract_payload
from app.services.agent_runtime import load_agent_config, serialize_agent

router = APIRouter()
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}


class AgentStepRequest(BaseModel):
    task: str = ""
    prompt: str = ""
    url: str = ""
    snapshot_html: str = ""
    history: list[Any] = Field(default_factory=list)
    state_in: dict[str, Any] | None = None
    context: dict[str, Any] = Field(default_factory=dict)


def _api_key_id(api_key: dict[str, Any]) -> str:
    return str(api_key.get("_id") or api_key.get("keyHash") or api_key.get("email") or "unknown")


def _rate_limit(api_key: dict[str, Any]) -> None:
    limit = int(os.getenv("AUTOMATA_API_STEP_RATE_LIMIT_PER_MINUTE", "120"))
    if limit <= 0:
        return
    key = _api_key_id(api_key)
    now = time.time()
    window_start = now - 60
    bucket = [stamp for stamp in _RATE_LIMIT_BUCKETS.get(key, []) if stamp >= window_start]
    if len(bucket) >= limit:
        raise api_error(
            429,
            "rate_limited",
            "Too many /step requests for this API key. Try again shortly.",
            {"limitPerMinute": limit},
        )
    bucket.append(now)
    _RATE_LIMIT_BUCKETS[key] = bucket


async def _owned_agent(agent_id: str, api_key: dict[str, Any]) -> dict[str, Any]:
    agent_config = await load_agent_config(agent_id)
    key_email = str(api_key.get("email") or "")
    if key_email and agent_config.get("email") != key_email:
        raise api_error(404, "agent_not_found", "Agent not found")
    return agent_config


def _serialize_skill(doc: dict[str, Any]) -> dict[str, Any]:
    try:
        version = max(1, int(doc.get("version") or 1))
    except (TypeError, ValueError):
        version = 1
    return {
        "skillId": doc.get("skillId") or doc.get("capabilityId", ""),
        "capabilityId": doc.get("capabilityId", ""),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "status": doc.get("status", ""),
        "promotionStatus": doc.get("promotionStatus") or doc.get("status", "draft"),
        "version": version,
        "versionLabel": doc.get("versionLabel") or f"v{version}",
        "runtime": doc.get("runtime", ""),
        "toolName": doc.get("toolName", ""),
        "inputSchema": doc.get("inputSchema") or {"type": "object", "properties": {}},
        "sideEffects": doc.get("sideEffects", "reads"),
        "riskPolicy": doc.get("riskPolicy", ""),
        "riskLevel": doc.get("riskLevel", ""),
        "connectorIds": doc.get("connectorIds") or [],
        "toolIds": doc.get("toolIds") or [],
        "runtimeRequirements": doc.get("runtimeRequirements") or [],
        "trajectoryCount": len(doc.get("trajectoryIds") or []),
        "trajectoryIds": doc.get("trajectoryIds") or [],
        "judge": doc.get("judge") or {},
        "publishedAt": doc.get("publishedAt"),
        "readyAt": doc.get("readyAt"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


@router.get("/agents/{agent_id}/runtime-contract", tags=["Agents"])
async def runtime_contract(agent_id: str, api_key: dict[str, Any] = Depends(verify_api_key)):
    agent_config = await _owned_agent(agent_id, api_key)
    runtime_contract = await runtime_contract_payload(agent_config)
    return {
        "protocolVersion": "1.0",
        "stepEndpoint": f"/api/v1/agents/{agent_id}/step",
        "auth": {"header": "x-api-key"},
        "runtimeCapabilities": runtime_contract["runtimeCapabilities"],
        "runtimeSpec": runtime_contract["runtimeSpec"],
        "request": {
            "requiredOneOf": ["prompt", "task"],
            "properties": {
                "prompt": {"type": "string"},
                "task": {"type": "string"},
                "url": {"type": "string", "description": "Current browser URL."},
                "snapshot_html": {"type": "string", "description": "Optional current DOM/snapshot context."},
                "step_index": {"type": "integer", "description": "0-based step counter supplied by the caller."},
                "history": {"type": "array", "items": {"type": "object"}},
                "state_in": {"type": "object", "description": "Previous state_out returned by /step."},
            },
        },
        "response": {
            "properties": {
                "tool_calls": {"type": "array", "description": "Actions the caller should execute."},
                "reasoning": {"type": "string"},
                "content": {"type": ["string", "null"]},
                "done": {"type": "boolean"},
                "state_out": {"type": "object", "description": "Persist and send as state_in on the next call."},
                "capability_match": {"type": "object", "description": "Present when a skill/capability is being used."},
                "executionMode": {"type": "string", "enum": ["skill_replay", "generalist", "connector_tool"]},
            },
        },
        "toolCalls": runtime_contract["toolCalls"],
        "unavailableToolCalls": runtime_contract["unavailableToolCalls"],
        "tools": runtime_contract["tools"],
        "skills": runtime_contract["skills"],
        "example": {
            "request": {"prompt": "Summarize latest BOPA labor updates.", "url": "about:blank", "step_index": 0, "state_in": {}},
            "response": {"tool_calls": [{"name": "browser.navigate", "arguments": {"url": "https://www.bopa.ad/"}}], "done": False, "state_out": {}},
        },
    }


@router.get("/agents", tags=["Agents"])
async def list_agents(companyId: str = "", api_key: dict[str, Any] = Depends(verify_api_key)):
    query: dict[str, Any] = {"email": api_key.get("email", "")}
    if companyId:
        query["companyId"] = companyId
    cursor = agents_collection.find(query, {"_id": 0}).sort("createdAt", -1)
    return {"agents": [serialize_agent(doc) async for doc in cursor]}


@router.get("/agents/{agent_id}", tags=["Agents"])
async def get_agent(agent_id: str, api_key: dict[str, Any] = Depends(verify_api_key)):
    agent_config = await _owned_agent(agent_id, api_key)
    return {"agent": serialize_agent(agent_config)}


@router.get("/agents/{agent_id}/skills", tags=["Agents"])
async def list_agent_skills(agent_id: str, api_key: dict[str, Any] = Depends(verify_api_key)):
    await _owned_agent(agent_id, api_key)
    cursor = capabilities_collection.find({"agentId": agent_id, "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", 1)
    return {"skills": [_serialize_skill(doc) for doc in await cursor.to_list(length=500)]}


@router.post("/agents/{agent_id}/step", tags=["Agents"])
async def agent_step(agent_id: str, body: AgentStepRequest, api_key: dict[str, Any] = Depends(verify_api_key)):
    agent_config = await _owned_agent(agent_id, api_key)
    _rate_limit(api_key)
    payload = body.model_dump()
    await record_runtime_event(
        agent_id=agent_id,
        company_id=str(agent_config.get("companyId") or ""),
        event_type="api.agent.step.request",
        step_index=int(payload.get("step_index") or 0),
        payload={
            "apiKeyId": _api_key_id(api_key),
            "apiKeyPrefix": api_key.get("prefix", ""),
            "email": api_key.get("email", ""),
            "prompt": payload.get("prompt") or payload.get("task") or "",
        },
    )
    data = await agent_step_result(agent_id, payload)
    if isinstance(data, dict):
        data.setdefault("executionMode", "skill_replay" if data.get("capability_match") else "generalist")
    return data
