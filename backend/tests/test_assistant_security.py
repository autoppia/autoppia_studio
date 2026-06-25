import pytest
from fastapi import HTTPException

from app.assistant import context as assistant_context
from app.assistant.context import AssistantContext, build_assistant_context
from app.assistant.service import ASSISTANT_FUNCTION_TOOLS, AutomataAssistantService
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

    def limit(self, *_args):
        return self

    async def to_list(self, length):
        return list(self.docs[:length])


def _matches_query(doc, query):
    for key, value in query.items():
        current = doc.get(key)
        if isinstance(value, dict) and "$in" in value:
            if current not in value["$in"]:
                return False
            continue
        if isinstance(value, dict) and "$ne" in value:
            if current == value["$ne"]:
                return False
            continue
        if current != value:
            return False
    return True


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.last_find_query = None
        self.last_count_query = None
        self.last_delete_query = None

    def find(self, query, projection=None):
        self.last_find_query = dict(query)
        docs = [
            doc
            for doc in self.docs
            if _matches_query(doc, query)
        ]
        return _Cursor(docs, self)

    async def count_documents(self, query):
        self.last_count_query = dict(query)
        return len(
            [
                doc
                for doc in self.docs
                if _matches_query(doc, query)
            ]
        )

    async def delete_many(self, query):
        self.last_delete_query = dict(query)
        kept = [doc for doc in self.docs if not _matches_query(doc, query)]
        deleted_count = len(self.docs) - len(kept)
        self.docs = kept

        class _DeleteResult:
            pass

        result = _DeleteResult()
        result.deleted_count = deleted_count
        return result


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


class _ConversationListCollection:
    def __init__(self, docs):
        self.docs = docs
        self.last_find_query = None

    def find(self, query, projection=None):
        self.last_find_query = dict(query)
        docs = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return _Cursor(docs, self)


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
async def test_assistant_tools_delete_chat_history_scoped_to_owner_and_company(monkeypatch):
    from app.assistant import tools as assistant_tools

    conversations = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "conversationId": "current"},
            {"email": "owner@example.com", "companyId": "company-1", "conversationId": "old"},
            {"email": "owner@example.com", "companyId": "company-2", "conversationId": "other-company"},
            {"email": "other@example.com", "companyId": "company-1", "conversationId": "other-user"},
        ]
    )
    monkeypatch.setattr(assistant_tools, "assistant_conversations_collection", conversations)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    result = await tools.delete_assistant_conversations(delete_all=True, exclude_conversation_id="current")

    assert result["deleted"] == 1
    assert conversations.last_delete_query == {
        "email": "owner@example.com",
        "companyId": "company-1",
        "conversationId": {"$ne": "current"},
    }
    assert [doc["conversationId"] for doc in conversations.docs] == ["current", "other-company", "other-user"]


@pytest.mark.asyncio
async def test_assistant_tools_count_and_list_skills_from_capabilities(monkeypatch):
    from app.assistant import tools as assistant_tools

    companies = _Collection([{"email": "owner@example.com", "companyId": "company-1", "name": "Celeris"}])
    capabilities = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill", "name": "Approved skill"},
            {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "tool", "name": "Not a skill"},
        ]
    )
    empty = _Collection([])
    monkeypatch.setattr(assistant_tools, "companies_collection", companies)
    monkeypatch.setattr(assistant_tools, "agents_collection", empty)
    monkeypatch.setattr(assistant_tools, "connectors_collection", empty)
    monkeypatch.setattr(assistant_tools, "credentials_collection", empty)
    monkeypatch.setattr(assistant_tools, "knowledge_documents_collection", empty)
    monkeypatch.setattr(assistant_tools, "capabilities_collection", capabilities)
    monkeypatch.setattr(assistant_tools, "tools_collection", empty)
    monkeypatch.setattr(assistant_tools, "benchmark_tasks_collection", empty)
    monkeypatch.setattr(assistant_tools, "work_items_collection", empty)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    snapshot = await tools.studio_snapshot()
    capabilities_payload = await tools.list_capabilities()

    assert snapshot["counts"]["skills"] == 1
    assert capabilities.last_count_query == {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill"}
    assert capabilities_payload["skills"] == [
        {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill", "name": "Approved skill"}
    ]
    assert capabilities.last_find_query == {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill"}


@pytest.mark.asyncio
async def test_assistant_uses_gpt5_mini_with_low_latency_studio_tools(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "studio_list_companies",
                            "arguments": '{"limit": 10}',
                        }
                    ]
                )
            assert any(item.get("type") == "function_call_output" for item in kwargs["input"])
            return _FakeResponse([], "The active company is Celeris.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_companies(self, limit=10):
            return [{"companyId": "company-1", "name": "Celeris"}][:limit]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("AUTOMATA_ASSISTANT_MODEL", raising=False)
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("list my companies and mention what I can do next")

    assert draft is None
    assert "Celeris" in reply
    assert calls[0]["model"] == "gpt-5-mini"
    assert calls[0]["reasoning"] == {"effort": "minimal"}
    assert calls[0]["text"] == {"verbosity": "low"}
    assert calls[0]["max_output_tokens"] == 700
    assert {tool["name"] for tool in calls[0]["tools"]} >= {"studio_list_companies", "studio_list_connectors", "studio_list_capabilities"}
    assert any(event.get("toolName") == "studio_list_companies" for event in events)
    assert any("Celeris" in item.get("output", "") for item in calls[1]["input"] if item.get("type") == "function_call_output")


@pytest.mark.asyncio
async def test_assistant_executes_chat_history_delete_tool_with_current_conversation_excluded(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    deletions = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-delete",
                            "name": "studio_delete_assistant_conversations",
                            "arguments": '{"deleteAll": true}',
                        }
                    ]
                )
            return _FakeResponse([], "Deleted the old Automata chat history.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def delete_assistant_conversations(self, *, conversation_ids=None, delete_all=False, exclude_conversation_id=""):
            deletions.append(
                {
                    "conversation_ids": conversation_ids,
                    "delete_all": delete_all,
                    "exclude_conversation_id": exclude_conversation_id,
                }
            )
            return {"deleted": 3, "requested": 0, "deleteAll": delete_all, "excludedConversationId": exclude_conversation_id}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    service.current_conversation_id = "current-conversation"
    reply, events, draft = await service.respond("delete my chat history")

    assert draft is None
    assert reply == "Deleted the old Automata chat history."
    assert deletions == [
        {
            "conversation_ids": [],
            "delete_all": True,
            "exclude_conversation_id": "current-conversation",
        }
    ]
    assert any(event.get("toolName") == "studio_delete_assistant_conversations" for event in events)


@pytest.mark.asyncio
async def test_assistant_executes_create_work_item_tool_after_user_confirmation(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    created = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-create-work",
                            "name": "studio_create_work_item",
                            "arguments": (
                                '{"title":"Daily Good Morning Email",'
                                '"prompt":"Send an email to mauricio.munozlopez@gmail.com saying Good morning.",'
                                '"triggerType":"scheduled",'
                                '"scheduleFrequency":"daily",'
                                '"scheduleTime":"09:00"}'
                            ),
                        }
                    ]
                )
            return _FakeResponse([], "Created Daily Good Morning Email.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def create_work_item(self, **kwargs):
            created.append(kwargs)
            return {
                "success": True,
                "workItem": {
                    "workItemId": "work-1",
                    "title": kwargs["title"],
                    "triggerType": kwargs["trigger_type"],
                    "scheduleFrequency": kwargs["schedule_frequency"],
                    "scheduleTime": kwargs["schedule_time"],
                },
            }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("yes create it")

    assert draft is None
    assert reply == "Created Daily Good Morning Email."
    assert created == [
        {
            "title": "Daily Good Morning Email",
            "prompt": "Send an email to mauricio.munozlopez@gmail.com saying Good morning.",
            "success_criteria": "",
            "agent_id": "",
            "agent_name": "",
            "run_target": "all",
            "browser_enabled": True,
            "browser_mode": "headless",
            "max_credits_per_run": 5.0,
            "max_budget_credits": None,
            "max_steps": 8,
            "trigger_type": "scheduled",
            "schedule_frequency": "daily",
            "schedule_time": "09:00",
            "schedule_day_of_week": 1,
            "trigger_config": {},
            "judge_implementation": "llm",
        }
    ]
    assert any(event.get("toolName") == "studio_create_work_item" for event in events)


def test_assistant_exposes_core_action_tools():
    names = {tool["name"] for tool in ASSISTANT_FUNCTION_TOOLS}

    assert {
        "studio_create_work_item",
        "studio_update_work_item",
        "studio_run_work_item",
        "studio_create_connector",
        "studio_test_connector",
        "studio_create_agent",
        "studio_approve_approval",
        "studio_save_knowledge_document_from_url",
        "studio_update_tool_approval",
        "studio_promote_trajectory_to_skill",
        "studio_list_credentials",
        "studio_list_api_keys",
        "studio_list_browser_profiles",
        "studio_get_account_info",
        "studio_get_analytics_summary",
        "studio_get_billing_plan_status",
        "studio_get_assistant_memory",
        "studio_rebuild_assistant_memory",
    } <= names


@pytest.mark.asyncio
async def test_assistant_executes_memory_rebuild_tool(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    rebuilds = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-memory",
                            "name": "studio_rebuild_assistant_memory",
                            "arguments": '{"limit": 100}',
                        }
                    ]
                )
            return _FakeResponse([], "Queued memory rebuild.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def get_assistant_memory(self):
            return {"exists": False, "summary": ""}

        async def rebuild_assistant_memory(self, limit=200):
            rebuilds.append(limit)
            return {"queued": True, "jobId": "job-1", "status": "queued", "limit": limit}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("summarize all conversations and give Automata past context")

    assert draft is None
    assert reply == "Queued memory rebuild."
    assert rebuilds == [100]
    assert any(event.get("toolName") == "studio_rebuild_assistant_memory" for event in events)


@pytest.mark.asyncio
async def test_assistant_executes_connector_action_tool(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    created = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-create-connector",
                            "name": "studio_create_connector",
                            "arguments": '{"name":"BOPA","type":"api","config":{"docsUrl":"https://example.com/docs"}}',
                        }
                    ]
                )
            return _FakeResponse([], "Created connector BOPA.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def create_connector(self, **kwargs):
            created.append(kwargs)
            return {"success": True, "connector": {"connectorId": "connector-1", "name": kwargs["name"]}}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("create a BOPA API connector")

    assert draft is None
    assert reply == "Created connector BOPA."
    assert created == [
        {
            "name": "BOPA",
            "connector_type": "api",
            "category": "software",
            "description": "",
            "status": "not_connected",
            "config": {"docsUrl": "https://example.com/docs"},
            "provider": "",
            "auth_required": None,
        }
    ]
    assert any(event.get("toolName") == "studio_create_connector" for event in events)


@pytest.mark.asyncio
async def test_assistant_answers_active_company_name_without_llm(monkeypatch):
    from app.assistant import service as assistant_service

    class _FailOpenAI:
        def __init__(self, api_key):
            raise AssertionError("quick company lookup should not call OpenAI")

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_companies(self, limit=20):
            return [
                {"companyId": "company-1", "name": "Celeris"},
                {"companyId": "company-2", "name": "Amazon"},
            ][:limit]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FailOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("which is current company name")

    assert draft is None
    assert 'Your active company is "Celeris".' in reply
    assert any(event.get("toolName") == "studio_list_companies" for event in events)


@pytest.mark.asyncio
async def test_assistant_routes_greetings_through_llm(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []

    class _FakeResponse:
        output = []
        output_text = "Hello from the model."

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return _FakeResponse()

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("hello")

    assert draft is None
    assert reply == "Hello from the model."
    assert calls
    assert any(event.get("content") == "Thinking with Studio tools." for event in events)


@pytest.mark.asyncio
async def test_assistant_keeps_rule_fallback_without_openai_key(monkeypatch):
    from app.assistant import service as assistant_service

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_connectors(self, limit=20):
            return [{"name": "Gmail", "status": "needs_auth"}]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("list my connectors")

    assert draft is None
    assert "Gmail" in reply
    assert any(event.get("toolName") == "studio.list_connectors" for event in events)


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


@pytest.mark.asyncio
async def test_assistant_company_scoped_load_rejects_unscoped_conversation(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "mode": "studio_global",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))

    with pytest.raises(HTTPException) as exc:
        await service.get_conversation("conv-1")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assistant_company_scoped_load_rejects_other_company(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "companyId": "company-2",
            "mode": "studio_global",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))

    with pytest.raises(HTTPException) as exc:
        await service.send_message("conv-1", "summary")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assistant_history_is_scoped_by_email_and_company(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationListCollection(
        [
            {
                "conversationId": "owned-1",
                "email": "owner@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Owned question"}],
                "updatedAt": "2026-01-01T00:00:00+00:00",
            },
            {
                "conversationId": "foreign-company",
                "email": "owner@example.com",
                "companyId": "company-2",
                "messages": [{"role": "user", "content": "Other company"}],
            },
            {
                "conversationId": "foreign-user",
                "email": "other@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Other user"}],
            },
        ]
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    history = await service.list_conversations()

    assert collection.last_find_query == {"email": "owner@example.com", "companyId": "company-1"}
    assert [item["conversationId"] for item in history] == ["owned-1"]
    assert history[0]["title"] == "Owned question"


@pytest.mark.asyncio
async def test_assistant_history_without_company_does_not_return_company_chats(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationListCollection(
        [
            {
                "conversationId": "global-1",
                "email": "owner@example.com",
                "companyId": "",
                "messages": [{"role": "user", "content": "Global question"}],
                "updatedAt": "2026-01-01T00:00:00+00:00",
            },
            {
                "conversationId": "company-1",
                "email": "owner@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Company question"}],
            },
        ]
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com"))
    history = await service.list_conversations()

    assert collection.last_find_query == {"email": "owner@example.com", "companyId": ""}
    assert [item["conversationId"] for item in history] == ["global-1"]
