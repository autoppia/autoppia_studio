from __future__ import annotations

import re
from typing import Any

from app.assistant.context import AssistantContext
from app.database import (
    agents_collection,
    benchmark_tasks_collection,
    companies_collection,
    connectors_collection,
    credentials_collection,
    knowledge_documents_collection,
    skills_collection,
    tools_collection,
    work_items_collection,
)

SECRET_KEY_RE = re.compile(r"(secret|token|password|api[_-]?key|refresh|credential)", re.IGNORECASE)


def _clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in doc.items() if key != "_id"}
    return _mask_secrets(cleaned)


def _mask_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            masked[key] = "***" if SECRET_KEY_RE.search(str(key)) and item not in ("", None) else _mask_secrets(item)
        return masked
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    return value


async def _to_list(cursor: Any, limit: int = 20) -> list[dict[str, Any]]:
    docs = await cursor.to_list(length=limit)
    return [_clean_doc(doc) for doc in docs]


class AutomataAssistantTools:
    """Scoped tools available to the internal Automata Assistant."""

    def __init__(self, context: AssistantContext):
        self.context = context

    def _query(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {"email": self.context.email}
        if self.context.company_id:
            query["companyId"] = self.context.company_id
        query.update(extra or {})
        return query

    async def studio_snapshot(self) -> dict[str, Any]:
        companies = await _to_list(companies_collection.find({"email": self.context.email}, {"_id": 0}).sort("createdAt", 1), 10)
        company_id = self.context.company_id or (companies[0].get("companyId", "") if companies else "")
        scoped = {"email": self.context.email, **({"companyId": company_id} if company_id else {})}
        counts = {
            "companies": len(companies),
            "agents": await agents_collection.count_documents(scoped),
            "connectors": await connectors_collection.count_documents(scoped),
            "credentials": await credentials_collection.count_documents(scoped),
            "knowledgeDocuments": await knowledge_documents_collection.count_documents(scoped),
            "skills": await skills_collection.count_documents(scoped),
            "tools": await tools_collection.count_documents(scoped),
            "benchmarkTasks": await benchmark_tasks_collection.count_documents(scoped),
            "workItems": await work_items_collection.count_documents(scoped),
        }
        return {"companies": companies, "activeCompanyId": company_id, "counts": counts}

    async def list_agents(self, limit: int = 10) -> list[dict[str, Any]]:
        return await _to_list(agents_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def list_connectors(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(connectors_collection.find(self._query(), {"_id": 0}).sort("createdAt", 1), limit)

    async def list_capabilities(self, limit: int = 20) -> dict[str, Any]:
        return {
            "tools": await _to_list(tools_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit),
            "skills": await _to_list(skills_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit),
        }

    async def list_work_items(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(work_items_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

