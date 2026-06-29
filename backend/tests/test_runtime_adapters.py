import pytest

from app.runtimes.registry import (
    default_runtime_profile,
    get_runtime_adapter,
    normalize_runtime_kind,
    runtime_catalog_payload,
    runtime_descriptor_payload,
)
from app.services import agent_builder, agent_runtime


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, length=100):
        return [dict(doc) for doc in self.docs[:length]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def _get(self, doc, key):
        current = doc
        for part in str(key).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _matches(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(doc, item) for item in value):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(doc, item) for item in value):
                    return False
                continue
            current = self._get(doc, key)
            if isinstance(value, dict) and "$in" in value:
                if isinstance(current, list):
                    if not any(item in value["$in"] for item in current):
                        return False
                elif current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if self._matches(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return None
        if upsert:
            self.docs.append({**query, **update.get("$set", {})})
        return None


def test_runtime_registry_exposes_three_agent_types():
    catalog = runtime_catalog_payload()
    kinds = {item["kind"] for item in catalog}

    assert kinds == {"model_agent", "codex", "claude_code"}
    assert normalize_runtime_kind("unknown") == "model_agent"
    assert get_runtime_adapter("codex").descriptor().supports["code"] is True
    assert get_runtime_adapter("model_agent").descriptor().supports["code"] is False
    assert default_runtime_profile("claude_code").provider == "anthropic"
    assert runtime_descriptor_payload("claude_code")["defaultProvider"] == "anthropic"


def test_agent_config_payload_includes_runtime_descriptor():
    payload = agent_runtime._agent_config_payload(
        {
            "agentId": "agent-1",
            "name": "Agent",
            "runtimeKind": "codex",
            "runtimeProfile": {"kind": "codex", "provider": "openai", "model": "gpt-5-codex"},
            "deliverySurfaces": {"api": {"endpoint": "/runtime/agents/agent-1/step"}},
        },
        {"tools": [], "skills": [], "resources": [], "entities": {}},
        {},
    )

    assert payload["runtimeKind"] == "codex"
    assert payload["runtimeDescriptor"]["kind"] == "codex"
    assert payload["runtimeDescriptor"]["supports"]["code"] is True
    assert payload["deliverySurfaces"]["api"]["endpoint"] == "/runtime/agents/agent-1/step"


@pytest.mark.asyncio
async def test_runtime_contract_includes_runtime_catalog(monkeypatch):
    async def fake_capability_context(agent_config):
        return {"tools": [], "skills": [], "resources": [], "entities": {}, "callables": []}

    monkeypatch.setattr(agent_runtime, "_capability_context", fake_capability_context)

    contract = await agent_runtime.runtime_contract_payload({"agentId": "agent-1", "runtimeKind": "claude_code"})

    assert contract["runtimeKind"] == "claude_code"
    assert contract["runtimeDescriptor"]["kind"] == "claude_code"
    assert {item["kind"] for item in contract["runtimeAdapters"]} == {"model_agent", "codex", "claude_code"}


@pytest.mark.asyncio
async def test_agent_step_dispatches_external_fallback_through_runtime_adapter(monkeypatch):
    posted = {}

    class _AgentsCollection:
        async def find_one(self, query, projection=None):
            return {
                "agentId": "agent-1",
                "name": "Claude Company Agent",
                "companyId": "company-1",
                "baseRuntimeEndpoint": "http://runtime.local",
                "runtimeType": "company_agent",
                "runtimeKind": "claude_code",
                "runtimeProfile": {"kind": "claude_code", "provider": "anthropic", "model": "claude-test"},
                "runtimeCapabilities": {"browser": True, "apiCalls": True, "knowledge": True, "humanApprovalForWrites": True},
                "runtimeSpec": {"tools": {"browser": True, "connectors": True, "skills": True, "knowledge": True}},
            }

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"content": "ok", "done": True, "state_out": {}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _Response()

    async def fake_capability_context(agent_config):
        return {"tools": [], "skills": [], "resources": [], "entities": {}, "callables": []}

    async def noop(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _AgentsCollection())
    monkeypatch.setattr(agent_runtime, "_capability_context", fake_capability_context)
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", noop)
    monkeypatch.setattr(agent_runtime, "record_usage", noop)

    result = await agent_runtime.agent_step_result("agent-1", {"prompt": "hello"})

    assert posted["url"] == "http://runtime.local/step"
    assert posted["json"]["agentConfig"]["runtimeKind"] == "claude_code"
    assert posted["json"]["agentConfig"]["runtimeDescriptor"]["kind"] == "claude_code"
    assert result["router_trace"]["runtimeKind"] == "claude_code"
    assert result["router_trace"]["runtimeAdapter"]["kind"] == "claude_code"


@pytest.mark.asyncio
async def test_generated_company_agent_step_contract_reaches_runtime_adapter(monkeypatch):
    posted = {}
    agents = _Collection()
    tools = _Collection(
        [
            {
                "toolId": "tool-1",
                "companyId": "company-1",
                "status": "ready",
                "name": "knowledge.company_docs.search",
                "description": "Search company docs.",
                "connectorId": "company-1:knowledge:company",
                "executionType": "knowledge_search",
                "sideEffects": "reads",
                "policyBoundary": "read",
                "runtimeRequirements": ["vectorstore"],
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                "outputSchema": {"type": "object", "properties": {"results": {"type": "array"}}},
            }
        ]
    )
    capabilities = _Collection(
        [
            {
                "capabilityId": "skill-1",
                "skillId": "skill-1",
                "agentId": "company-1:agent:model_agent",
                "companyId": "company-1",
                "capabilityKind": "skill",
                "status": "ready",
                "name": "Answer payroll question",
                "toolName": "skill.answer_payroll_question",
                "description": "Answer payroll questions.",
                "whenToUse": "Use for payroll questions.",
                "trajectoryIds": ["traj-1"],
                "runtimeRequirements": ["connector_runtime"],
                "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}},
            }
        ]
    )
    resources = _Collection(
        [
            {
                "documentId": "doc-1",
                "resourceId": "doc-1",
                "companyId": "company-1",
                "filename": "Payroll handbook.pdf",
                "status": "indexed",
                "connectorId": "company-1:knowledge:company",
                "resourceContract": {
                    "resourceId": "doc-1",
                    "resourceKind": "document",
                    "status": "indexed",
                    "indexing": {"indexed": True},
                    "governance": {"companyId": "company-1", "connectorId": "company-1:knowledge:company"},
                },
            }
        ]
    )
    entities = _Collection(
        [
            {
                "entityId": "entity-1",
                "companyId": "company-1",
                "name": "KnowledgeQuery",
                "fields": [{"name": "query", "type": "string"}],
                "relationships": [],
            }
        ]
    )

    monkeypatch.setattr(agent_builder, "agents_collection", agents)
    monkeypatch.setattr(agent_builder, "tools_collection", tools)
    monkeypatch.setattr(agent_builder, "capabilities_collection", capabilities)
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", resources)
    monkeypatch.setattr(agent_builder, "entities_collection", entities)
    monkeypatch.setattr(agent_runtime, "agents_collection", agents)
    monkeypatch.setattr(agent_runtime, "tools_collection", tools)
    monkeypatch.setattr(agent_runtime, "capabilities_collection", capabilities)
    monkeypatch.setattr(agent_runtime, "knowledge_documents_collection", resources)
    monkeypatch.setattr(agent_runtime, "entities_collection", entities)

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"content": "ok", "done": True, "state_out": {}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _Response()

    async def noop(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", noop)
    monkeypatch.setattr(agent_runtime, "record_usage", noop)

    built = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        runtime_kinds=["model_agent"],
        runtime_profiles={"model_agent": {"provider": "anthropic", "model": "claude-sonnet"}},
    )
    agent_doc = agents.docs[0]
    agent_doc["baseRuntimeEndpoint"] = "http://runtime.local"

    result = await agent_runtime.agent_step_result(
        built["agentIds"][0],
        {"prompt": "Use general reasoning about operations.", "context": {"disableSkillRouting": True}},
    )

    posted_config = posted["json"]["agentConfig"]
    automata_capabilities = posted["json"]["context"]["automataCapabilities"]
    assert posted["url"] == "http://runtime.local/step"
    assert posted_config["runtimeKind"] == "model_agent"
    assert posted_config["runtimeProfile"]["provider"] == "anthropic"
    assert posted_config["tools"][0]["name"] == "knowledge.company_docs.search"
    assert posted_config["tools"][0]["executionReady"] is True
    assert posted_config["tools"][0]["implementationRequired"] is False
    assert posted_config["skills"][0]["name"] == "skill.answer_payroll_question"
    assert posted_config["resources"][0]["resourceId"] == "doc-1"
    assert posted_config["deliverySurfaces"]["api"]["endpoint"] == f"/runtime/agents/{built['agentIds'][0]}/step"
    assert automata_capabilities["tools"][0]["name"] == "knowledge.company_docs.search"
    assert automata_capabilities["skills"][0]["toolName"] == "skill.answer_payroll_question"
    assert result["router_trace"]["decision"] == "skill_routing_disabled"
    assert result["router_trace"]["runtimeKind"] == "model_agent"
