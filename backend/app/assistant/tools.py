from __future__ import annotations

import re
from typing import Any

from app.assistant.context import AssistantContext
from app.database import (
    agents_collection,
    approvals_collection,
    artifacts_collection,
    benchmark_tasks_collection,
    capabilities_collection,
    companies_collection,
    connectors_collection,
    credentials_collection,
    entities_collection,
    knowledge_documents_collection,
    tools_collection,
    work_items_collection,
)
from app.services.entity_mapper import propose_entities_from_openapi_url

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
            "skills": await capabilities_collection.count_documents({**scoped, "capabilityKind": "skill"}),
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
            "skills": await _to_list(
                capabilities_collection.find({**self._query(), "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", -1),
                limit,
            ),
        }

    async def list_work_items(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(work_items_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def list_companies(self, limit: int = 10) -> list[dict[str, Any]]:
        return await _to_list(companies_collection.find({"email": self.context.email}, {"_id": 0}).sort("createdAt", 1), limit)

    async def list_entities(self, limit: int = 50) -> list[dict[str, Any]]:
        return await _to_list(entities_collection.find(self._query(), {"_id": 0}).sort("name", 1), limit)

    async def generate_entities_from_openapi(
        self,
        *,
        source_url: str,
        apply: bool = False,
        replace_existing: bool = False,
        limit: int = 25,
    ) -> dict[str, Any]:
        proposals = (await propose_entities_from_openapi_url(source_url))[: max(1, min(limit, 100))]
        existing = await _to_list(entities_collection.find(self._query(), {"_id": 0, "name": 1}).sort("name", 1), 500)
        existing_names = {str(doc.get("name") or "") for doc in existing}
        entities = []
        skipped = []
        if not apply:
            return {"applied": False, "sourceUrl": source_url, "entities": proposals, "skipped": []}

        from datetime import datetime, timezone
        from uuid import uuid4

        now = datetime.now(timezone.utc).isoformat()
        for proposal in proposals:
            name = str(proposal.get("name") or "").strip()[:80]
            if not name:
                continue
            doc = {
                "entityId": str(uuid4()),
                "email": self.context.email,
                "companyId": self.context.company_id,
                "name": name,
                "description": str(proposal.get("description") or "").strip(),
                "fields": proposal.get("fields") if isinstance(proposal.get("fields"), list) else [],
                "relationships": proposal.get("relationships") if isinstance(proposal.get("relationships"), list) else [],
                "sourceConnectorId": "",
                "source": "openapi",
                "metadata": proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {},
                "createdAt": now,
                "updatedAt": now,
            }
            if name in existing_names and not replace_existing:
                skipped.append({"name": name, "reason": "already_exists"})
                continue
            if name in existing_names and replace_existing:
                await entities_collection.update_one(
                    self._query({"name": name}),
                    {"$set": {key: value for key, value in doc.items() if key not in {"entityId", "createdAt"}}},
                )
                refreshed = await entities_collection.find_one(self._query({"name": name}), {"_id": 0}) or doc
                entities.append(_clean_doc(refreshed))
                continue
            await entities_collection.insert_one(doc)
            existing_names.add(name)
            entities.append(_clean_doc(doc))
        return {"applied": True, "sourceUrl": source_url, "entities": entities, "skipped": skipped}

    async def list_approvals(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(approvals_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def list_knowledge_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(knowledge_documents_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def list_artifacts(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(artifacts_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)
