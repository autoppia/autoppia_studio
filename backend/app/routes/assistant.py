from __future__ import annotations

from fastapi import APIRouter, Depends

from app.assistant.context import build_assistant_context
from app.assistant.schemas import AssistantConversationCreateRequest, AssistantMessageRequest
from app.assistant.service import AutomataAssistantService
from app.request_scope import RequestScope, get_request_scope

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/conversations")
async def create_assistant_conversation(
    body: AssistantConversationCreateRequest,
    scope: RequestScope = Depends(get_request_scope),
):
    context = await build_assistant_context(
        scope=scope,
        email=body.email,
        mode=body.mode,
        company_id=body.companyId,
        route=body.route,
        visible_state=body.visibleState,
    )
    service = AutomataAssistantService(context)
    conversation = await service.create_conversation(seed_prompt=body.seedPrompt)
    return {"conversation": conversation}


@router.post("/conversations/{conversation_id}/messages")
async def send_assistant_message(
    conversation_id: str,
    body: AssistantMessageRequest,
    scope: RequestScope = Depends(get_request_scope),
):
    context = await build_assistant_context(
        scope=scope,
        email=body.email,
        mode=body.mode or "studio_global",
        company_id=body.companyId,
        route=body.route,
        visible_state=body.visibleState,
    )
    service = AutomataAssistantService(context)
    conversation = await service.send_message(conversation_id, body.message)
    return {"conversation": conversation}

