from __future__ import annotations

from typing import Any

from app.request_scope import RequestScope


class ScopedRepository:
    def __init__(self, collection: Any, scope: RequestScope):
        self.collection = collection
        self.scope = scope

    def scoped_query(self, query: dict[str, Any] | None = None, *, email: str = "") -> dict[str, Any]:
        scoped = dict(query or {})
        owner = self.scope.require_email(email or str(scoped.get("email") or ""))
        scoped["email"] = owner
        return scoped

    async def find_owned_one(self, query: dict[str, Any], *, not_found: str = "Not found") -> dict[str, Any]:
        doc = await self.collection.find_one(query, {"_id": 0})
        return self.scope.assert_owns(doc, not_found=not_found)

    def _owned_write_query(self, query: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
        return {**query, "email": self.scope.require_email(str(doc.get("email") or ""))}

    async def update_owned_one(self, query: dict[str, Any], update: dict[str, Any], *, not_found: str = "Not found") -> dict[str, Any]:
        existing = await self.find_owned_one(query, not_found=not_found)
        write_query = self._owned_write_query(query, existing)
        await self.collection.update_one(write_query, update)
        refreshed = await self.collection.find_one(write_query, {"_id": 0})
        return refreshed or existing

    async def delete_owned_one(self, query: dict[str, Any], *, not_found: str = "Not found") -> int:
        existing = await self.find_owned_one(query, not_found=not_found)
        result = await self.collection.delete_one(self._owned_write_query(query, existing))
        return int(getattr(result, "deleted_count", 0) or 0)


class AgentConfigRepository(ScopedRepository):
    async def by_id(self, agent_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"agentId": agent_id}, not_found="Agent not found")


class CompanyRepository(ScopedRepository):
    async def by_id(self, company_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"companyId": company_id}, not_found="Company not found")


class ConnectorRepository(ScopedRepository):
    async def by_id(self, connector_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"connectorId": connector_id}, not_found="Connector not found")


class CredentialRepository(ScopedRepository):
    async def by_id(self, credential_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"credentialId": credential_id}, not_found="Credential not found")


class WorkBoardRepository(ScopedRepository):
    async def by_id(self, board_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"boardId": board_id}, not_found="Work board not found")


class WorkItemRepository(ScopedRepository):
    async def by_id(self, work_item_id: str) -> dict[str, Any]:
        return await self.find_owned_one({"workItemId": work_item_id}, not_found="Work item not found")
