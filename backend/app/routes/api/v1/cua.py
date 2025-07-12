import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from cua.openai import OpenAICUA

router = APIRouter()

agents = {}

class CUAInput(BaseModel):
    provider: Literal["openai"] = "openai"
    user_input: Optional[str] = None
    screenshot: Optional[str] = None
    current_url: Optional[str] = None
    display_width: int = Field(None, gt=0)
    display_height: int = Field(None, gt=0)

    @model_validator(mode="after")
    def check_user_input_or_screenshot(cls, model):
        if model.user_input is None and model.screenshot is None:
            raise ValueError("Either user_input or screenshot must be provided")
        if model.screenshot is not None and model.current_url is None:
            raise ValueError("Current url must be provided when sending screenshot")
        return model


@router.post("/cua/start", tags=["CUA"])
async def start(request: CUAInput):
    agent_id = str(uuid.uuid4())

    if request.provider == "openai":
        cua = OpenAICUA()
    else:
        cua = OpenAICUA()

    if request.display_width and request.display_height:
        cua.set_dimension(request.display_width, request.display_height)
    agents[agent_id] = cua

    output = await cua.call(user_input=request.user_input)
    return {"agent_id": agent_id, "output": output}

@router.put("/cua/{agent_id}/forward", tags=["CUA"])
async def forward(agent_id: str, request: CUAInput):
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    cua = agents.get(agent_id)    
    output = await cua.call(
        user_input=request.user_input, 
        screenshot=request.screenshot, 
        current_url=request.current_url
    )
    return {"agent_id": agent_id, "output": output}

@router.put("/cua/{agent_id}/stop", tags=["CUA"])
async def stop(agent_id: str):
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    del agents[agent_id]
    return {}


@router.get("/cua/{agent_id}/gif", tags=["CUA"])
async def gif(agent_id: str):
    return {"agent_id": agent_id, "gif": "Not implemented"}