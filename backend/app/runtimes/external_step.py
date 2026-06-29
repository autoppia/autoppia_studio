from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from app.runtimes.base import AgentRuntimeContext


def step_url(endpoint: str) -> str:
    clean = endpoint.rstrip("/")
    if not clean:
        return ""
    if clean.endswith("/step"):
        return clean
    return f"{clean}/step"


class ExternalStepRuntimeMixin:
    async def step(self, request: Any, context: AgentRuntimeContext) -> Any:
        if not isinstance(request, dict):
            raise HTTPException(status_code=400, detail="Agent runtime request must be an object")

        agent_config = context.agentConfig if isinstance(context.agentConfig, dict) else {}
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        default_endpoint = str(metadata.get("defaultEndpoint") or "").strip()
        endpoint = step_url(str(agent_config.get("baseRuntimeEndpoint") or default_endpoint))
        if not endpoint:
            raise HTTPException(status_code=409, detail="Agent runtime is not deployed yet")

        client_factory = metadata.get("httpClientFactory") or httpx.AsyncClient
        timeout = float(metadata.get("timeoutSeconds") or 45.0)
        try:
            async with client_factory(timeout=timeout) as client:
                response = await client.post(endpoint, json=request)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Agent runtime request failed: {exc}") from exc

        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"runtimeStatus": response.status_code, "body": response.text})
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
