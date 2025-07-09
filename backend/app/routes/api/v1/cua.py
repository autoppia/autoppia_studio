from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

router = APIRouter()

class CUAInput(BaseModel):
    provider: Literal["openai"] = "openai"
    user_message: Optional[str] = None
    screenshot: Optional[str] = None
    current_url: Optional[str] = None
    display_width: int = Field(None, gt=0)
    display_height: int = Field(None, gt=0)

    @model_validator(mode="after")
    def check_user_message_or_screenshot(cls, model):
        if model.user_message is None and model.screenshot is None:
            raise ValueError("Either user_message or screenshot must be provided")
        if model.screenshot is not None and model.current_url is None:
            raise ValueError("Current url must be provided when sending screenshot")
        return model


@router.post("/cua/start", tags=["CUA"])
async def start(request: CUAInput):
    pass

@router.put("/cua/{agent_id}/forward", tags=["CUA"])
async def forward(agent_id: str, request: CUAInput):
    pass

@router.put("/cua/{agent_id}/stop", tags=["CUA"])
async def stop(agent_id: str):
    pass

@router.get("/cua/{agent_id}/gif", tags=["CUA"])
async def gif(agent_id: str):
    pass