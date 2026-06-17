from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.database import companies_collection
from app.request_scope import RequestScope
from app.assistant.schemas import AssistantMode


@dataclass(frozen=True)
class AssistantContext:
    email: str
    mode: AssistantMode = "studio_global"
    company_id: str = ""
    route: str = ""
    visible_state: dict[str, Any] = field(default_factory=dict)
    allowed_scopes: tuple[str, ...] = ("studio:read", "onboarding:draft")


async def build_assistant_context(
    *,
    scope: RequestScope,
    email: str,
    mode: AssistantMode,
    company_id: str = "",
    route: str = "",
    visible_state: dict[str, Any] | None = None,
) -> AssistantContext:
    owner = scope.require_email(email)
    if company_id:
        company = await companies_collection.find_one({"email": owner, "companyId": company_id}, {"_id": 1})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
    return AssistantContext(
        email=owner,
        mode=mode,
        company_id=company_id,
        route=route,
        visible_state=visible_state or {},
        allowed_scopes=("studio:read", "onboarding:draft", "draft:write"),
    )

