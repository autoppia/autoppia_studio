import pytest
from fastapi import HTTPException

from app.assistant import context as assistant_context
from app.assistant.context import AssistantContext, build_assistant_context
from app.assistant.service import AutomataAssistantService
from app.assistant.tools import AutomataAssistantTools
from app.request_scope import RequestScope


class _CompanyCollection:
    def __init__(self, doc=None):
        self.doc = doc
        self.last_query = None

    async def find_one(self, query, projection=None):
        self.last_query = dict(query)
        if self.doc and all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None


class _Cursor:
    def __init__(self, docs, collection):
        self.docs = docs
        self.collection = collection

    def sort(self, *args):
        return self

    async def to_list(self, length):
        return list(self.docs[:length])


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.last_find_query = None
        self.last_count_query = None

    def find(self, query, projection=None):
        self.last_find_query = dict(query)
        docs = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return _Cursor(docs, self)

    async def count_documents(self, query):
        self.last_count_query = dict(query)
        return len(
            [
                doc
                for doc in self.docs
                if all(doc.get(key) == value for key, value in query.items())
            ]
        )


class _ConversationCollection:
    def __init__(self, doc):
        self.doc = dict(doc)
        self.last_update_query = None
        self.last_update = None

    async def find_one(self, query, projection=None):
        if all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        self.last_update_query = dict(query)
        self.last_update = dict(update)
        self.doc.update(update.get("$set", {}))


@pytest.mark.asyncio
async def test_assistant_context_rejects_foreign_company(monkeypatch):
    companies = _CompanyCollection({"email": "owner@example.com", "companyId": "company-1"})
    monkeypatch.setattr(assistant_context, "companies_collection", companies)

    with pytest.raises(HTTPException) as exc:
        await build_assistant_context(
            scope=RequestScope(email="other@example.com", token_email="other@example.com"),
            email="other@example.com",
            mode="studio_global",
            company_id="company-1",
        )

    assert exc.value.status_code == 404
    assert companies.last_query == {"email": "other@example.com", "companyId": "company-1"}


@pytest.mark.asyncio
async def test_assistant_tools_scope_queries_by_email_and_company(monkeypatch):
    from app.assistant import tools as assistant_tools

    connectors = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "name": "Owned"},
            {"email": "other@example.com", "companyId": "company-1", "name": "Foreign"},
        ]
    )
    monkeypatch.setattr(assistant_tools, "connectors_collection", connectors)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    docs = await tools.list_connectors()

    assert connectors.last_find_query == {"email": "owner@example.com", "companyId": "company-1"}
    assert [doc["name"] for doc in docs] == ["Owned"]


@pytest.mark.asyncio
async def test_assistant_tools_mask_secret_like_fields(monkeypatch):
    from app.assistant import tools as assistant_tools

    connectors = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "name": "API",
                "config": {"apiKey": "secret-value", "baseUrl": "https://example.com"},
            }
        ]
    )
    monkeypatch.setattr(assistant_tools, "connectors_collection", connectors)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    docs = await tools.list_connectors()

    assert docs[0]["config"]["apiKey"] == "***"
    assert docs[0]["config"]["baseUrl"] == "https://example.com"


@pytest.mark.asyncio
async def test_assistant_message_inherits_conversation_company_scope(monkeypatch):
    from app.assistant import service as assistant_service

    seen_company_ids = []

    class _Tools:
        def __init__(self, context):
            seen_company_ids.append(context.company_id)

        async def studio_snapshot(self):
            return {
                "companies": [{"companyId": "company-1"}],
                "activeCompanyId": "company-1",
                "counts": {
                    "companies": 1,
                    "agents": 0,
                    "connectors": 0,
                    "credentials": 0,
                    "knowledgeDocuments": 0,
                    "skills": 0,
                    "tools": 0,
                    "benchmarkTasks": 0,
                    "workItems": 0,
                },
            }

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "mode": "studio_global",
            "companyId": "company-1",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com"))
    await service.send_message("conv-1", "summary")

    assert seen_company_ids == ["", "company-1"]
    assert collection.last_update["$set"]["companyId"] == "company-1"
