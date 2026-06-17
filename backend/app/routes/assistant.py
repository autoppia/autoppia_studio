from __future__ import annotations

from fastapi import APIRouter, Depends

from app.assistant.context import build_assistant_context
from app.assistant.schemas import AssistantConversationCreateRequest, AssistantMessageRequest
from app.assistant.service import AutomataAssistantService
from app.request_scope import RequestScope, get_request_scope

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/conversations")
async def list_assistant_conversations(
    email: str,
    companyId: str = "",
    mode: str = "studio_global",
    limit: int = 30,
    scope: RequestScope = Depends(get_request_scope),
):
    context = await build_assistant_context(
        scope=scope,
        email=email,
        mode=mode if mode in {"studio_global", "onboarding", "agent_detail", "connectors", "capabilities", "evals", "work"} else "studio_global",
        company_id=companyId,
    )
    service = AutomataAssistantService(context)
    return {"conversations": await service.list_conversations(limit=limit)}


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


@router.get("/conversations/{conversation_id}")
async def get_assistant_conversation(
    conversation_id: str,
    email: str,
    companyId: str = "",
    mode: str = "studio_global",
    scope: RequestScope = Depends(get_request_scope),
):
    context = await build_assistant_context(
        scope=scope,
        email=email,
        mode=mode if mode in {"studio_global", "onboarding", "agent_detail", "connectors", "capabilities", "evals", "work"} else "studio_global",
        company_id=companyId,
    )
    service = AutomataAssistantService(context)
    return {"conversation": await service.get_conversation(conversation_id)}


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
