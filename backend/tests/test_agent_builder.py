import pytest

from app.services import agent_builder
from app.services import custom_connector_executors


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, length=100):
        return [dict(doc) for doc in self.docs[:length]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.updates = []

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
        self.updates.append((query, update, upsert))
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return None
        if upsert:
            self.docs.append({**query, **update.get("$set", {})})
        return None


@pytest.mark.asyncio
async def test_build_company_agents_creates_three_runtime_kinds_from_skills(monkeypatch):
    skills = _Collection([
        {
            "capabilityId": "skill-1",
            "skillId": "skill-1",
            "companyId": "company-1",
            "email": "owner@example.com",
            "capabilityKind": "skill",
            "status": "ready",
            "name": "Search claims",
            "toolName": "skill.search_claims",
            "whenToUse": "Find claim status.",
            "trajectoryIds": ["traj-1"],
            "runtimeRequirements": ["connector_runtime"],
            "benchmarkId": "bench-1",
        }
    ])
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "capabilities_collection", skills)
    monkeypatch.setattr(agent_builder, "tools_collection", _Collection())
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        benchmark_id="bench-1",
    )

    assert result["agentCount"] == 3
    assert result["skillCount"] == 1
    assert result["toolCount"] == 0
    assert result["resourceCount"] == 0
    assert result["entityCount"] == 0
    assert set(result["agentIds"]) == {
        "company-1:agent:model_agent",
        "company-1:agent:codex",
        "company-1:agent:claude_code",
    }
    assert {doc["runtimeKind"] for doc in agents.docs} == {"model_agent", "codex", "claude_code"}
    assert {doc["runtimeProfile"]["kind"] for doc in agents.docs} == {"model_agent", "codex", "claude_code"}
    assert all(doc["runtimeType"] == "company_agent" for doc in agents.docs)
    assert all(doc["deliverySurfaces"]["chat"]["available"] is True for doc in agents.docs)
    assert all(doc["deliverySurfaces"]["api"]["endpoint"] == f"/runtime/agents/{doc['agentId']}/step" for doc in agents.docs)
    assert all(doc["deliverySurfaces"]["widget"]["embedScript"] == "/embed/v1/widget.js" for doc in agents.docs)
    assert all(doc["skills"][0]["capabilityId"] == "skill-1" for doc in agents.docs)
    assert all(doc["tasks"][0]["trajectoryId"] == "traj-1" for doc in agents.docs)
    assert all(doc["status"] == "ready" for doc in agents.docs)


@pytest.mark.asyncio
async def test_build_company_agents_without_skills_creates_draft_model_agent(monkeypatch):
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", _Collection())
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
    )

    assert result["agentCount"] == 1
    assert result["skillCount"] == 0
    assert agents.docs[0]["runtimeKind"] == "model_agent"
    assert agents.docs[0]["status"] == "draft"
    assert agents.docs[0]["trainingStatus"] == "needs_skills"


@pytest.mark.asyncio
async def test_build_company_agents_applies_runtime_profile_overrides(monkeypatch):
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", _Collection())
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
        runtime_profiles={
            "model_agent": {
                "provider": "anthropic",
                "model": "claude-sonnet",
                "systemPrompt": "Follow Celeris operating policy.",
                "metadata": {"temperature": 0.1},
            }
        },
    )

    assert result["agentCount"] == 1
    assert agents.docs[0]["runtimeProfile"]["kind"] == "model_agent"
    assert agents.docs[0]["runtimeProfile"]["provider"] == "anthropic"
    assert agents.docs[0]["runtimeProfile"]["model"] == "claude-sonnet"
    assert agents.docs[0]["runtimeProfile"]["systemPrompt"] == "Follow Celeris operating policy."
    assert agents.docs[0]["runtimeProfile"]["metadata"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_build_company_agents_with_tools_creates_ready_tool_enabled_agent(monkeypatch):
    tools = _Collection([
        {
            "toolId": "tool-1",
            "companyId": "company-1",
            "status": "candidate",
            "name": "knowledge.company_docs.search",
            "description": "Search company docs.",
            "connectorId": "company-1:knowledge:company",
            "executionType": "knowledge_search",
            "sideEffects": "reads",
            "policyBoundary": "read",
            "riskLevel": "low",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "outputSchema": {"type": "object", "properties": {"results": {"type": "array"}}},
            "permissions": {"connectorId": "company-1:knowledge:company", "scopes": ["read"]},
            "approvalPolicy": {"required": False, "mode": "never"},
            "scopes": ["read", "connector:company-1:knowledge:company"],
            "runtimeRequirements": ["vectorstore"],
            "toolContract": {"format": "autoppia.tool_contract", "policyBoundary": "read"},
            "updatedAt": "2026-01-01T00:00:00+00:00",
        }
    ])
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", tools)
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
    )

    assert result["agentCount"] == 1
    assert result["skillCount"] == 0
    assert result["toolCount"] == 1
    assert result["resourceCount"] == 0
    assert result["entityCount"] == 0
    assert agents.docs[0]["status"] == "ready"
    assert agents.docs[0]["trainingStatus"] == "tools_ready"
    assert agents.docs[0]["tools"][0]["name"] == "knowledge.company_docs.search"
    assert agents.docs[0]["tools"][0]["kind"] == "tool"
    assert agents.docs[0]["tools"][0]["toolContract"]["format"] == "autoppia.tool_contract"
    assert agents.docs[0]["skills"] == []
    assert agents.docs[0]["generatedFrom"]["toolIds"] == ["tool-1"]


@pytest.mark.asyncio
async def test_build_company_agents_with_missing_custom_connector_executor_is_not_ready(monkeypatch):
    custom_connector_executors.clear_custom_connector_executors()
    tools = _Collection([
        {
            "toolId": "tool-payroll",
            "companyId": "company-1",
            "status": "candidate",
            "name": "payroll.lookup_employee",
            "description": "Lookup payroll employee.",
            "connectorId": "payroll",
            "executionType": "connector_tool",
            "runtimeExecutor": "custom.payroll.lookup_employee",
            "metadata": {"customConnector": True},
            "executorBlueprint": {
                "executorName": "custom.payroll.lookup_employee",
                "registrationStatus": "missing",
            },
        }
    ])
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", tools)
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
    )

    assert result["toolCount"] == 1
    assert result["executableToolCount"] == 0
    assert result["missingToolExecutorCount"] == 1
    assert agents.docs[0]["status"] == "draft"
    assert agents.docs[0]["trainingStatus"] == "connector_implementation_required"
    assert agents.docs[0]["runtimeReadiness"]["missingToolNames"] == ["payroll.lookup_employee"]
    assert agents.docs[0]["tools"][0]["executionReady"] is False
    assert agents.docs[0]["tools"][0]["implementationRequired"] is True


@pytest.mark.asyncio
async def test_build_company_agents_with_registered_custom_connector_executor_is_ready(monkeypatch):
    custom_connector_executors.clear_custom_connector_executors()
    custom_connector_executors.register_custom_connector_executor("custom.payroll.lookup_employee", lambda _payload: {"ok": True})
    tools = _Collection([
        {
            "toolId": "tool-payroll",
            "companyId": "company-1",
            "status": "candidate",
            "name": "payroll.lookup_employee",
            "description": "Lookup payroll employee.",
            "connectorId": "payroll",
            "executionType": "connector_tool",
            "runtimeExecutor": "custom.payroll.lookup_employee",
            "metadata": {"customConnector": True},
            "executorBlueprint": {
                "executorName": "custom.payroll.lookup_employee",
                "registrationStatus": "registered",
            },
        }
    ])
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", tools)
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    try:
        result = await agent_builder.build_company_agents(
            email="owner@example.com",
            company_id="company-1",
            runtime_kinds=["model_agent"],
        )
    finally:
        custom_connector_executors.clear_custom_connector_executors()

    assert result["toolCount"] == 1
    assert result["executableToolCount"] == 1
    assert result["missingToolExecutorCount"] == 0
    assert agents.docs[0]["status"] == "ready"
    assert agents.docs[0]["trainingStatus"] == "tools_ready"
    assert agents.docs[0]["runtimeReadiness"]["executableToolCount"] == 1
    assert agents.docs[0]["tools"][0]["executionReady"] is True
    assert agents.docs[0]["tools"][0]["implementationRequired"] is False


@pytest.mark.asyncio
async def test_build_company_agents_with_knowledge_resources_creates_ready_grounded_agent(monkeypatch):
    resources = _Collection([
        {
            "documentId": "doc-1",
            "resourceId": "doc-1",
            "companyId": "company-1",
            "filename": "Claims handbook.pdf",
            "status": "indexed",
            "source": "upload",
            "contentType": "application/pdf",
            "connectorId": "company-1:knowledge:company",
            "vectorDatabaseId": "vector-1",
            "vectorDatabaseName": "company_docs",
            "vectorCollectionName": "claims",
            "size": 1234,
            "storagePath": "/tmp/secret-path",
            "resourceContract": {
                "resourceId": "doc-1",
                "resourceKind": "document",
                "status": "indexed",
                "indexing": {
                    "indexed": True,
                    "vectorDatabaseId": "vector-1",
                    "vectorDatabaseName": "company_docs",
                    "vectorCollectionName": "claims",
                },
                "governance": {
                    "companyId": "company-1",
                    "connectorId": "company-1:knowledge:company",
                    "source": "upload",
                    "contentType": "application/pdf",
                    "acl": {"visibility": "company", "allowedRoles": ["owner"], "allowedUsers": []},
                    "freshness": {"status": "current"},
                    "citability": {"citable": True, "citationLabel": "Claims handbook.pdf", "sourceUrl": ""},
                },
                "readTools": ["knowledge.company_docs.search"],
            },
            "updatedAt": "2026-01-01T00:00:00+00:00",
        }
    ])
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", _Collection())
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", resources)
    monkeypatch.setattr(agent_builder, "entities_collection", _Collection())
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
    )

    assert result["agentCount"] == 1
    assert result["skillCount"] == 0
    assert result["toolCount"] == 0
    assert result["resourceCount"] == 1
    assert agents.docs[0]["status"] == "ready"
    assert agents.docs[0]["trainingStatus"] == "knowledge_ready"
    assert agents.docs[0]["resources"][0]["resourceId"] == "doc-1"
    assert agents.docs[0]["knowledge"] == agents.docs[0]["resources"]
    assert agents.docs[0]["resources"][0]["readTools"] == ["knowledge.company_docs.search"]
    assert "storagePath" not in agents.docs[0]["resources"][0]
    assert agents.docs[0]["generatedFrom"]["resourceIds"] == ["doc-1"]


@pytest.mark.asyncio
async def test_build_company_agents_includes_company_entity_graph(monkeypatch):
    entities = _Collection([
        {
            "entityId": "ent-claim",
            "companyId": "company-1",
            "name": "Claim",
            "description": "Insurance claim.",
            "fields": [{"name": "id", "type": "string", "role": "identifier"}],
            "relationships": [{"name": "customer", "kind": "belongsTo", "target": "Customer", "via": "customerId"}],
            "sourceConnectorId": "connector-1",
            "source": "company_harvester",
            "metadata": {"companyHarvest": True},
        },
        {
            "entityId": "ent-customer",
            "companyId": "company-1",
            "name": "Customer",
            "description": "Customer record.",
            "fields": [{"name": "id", "type": "string", "role": "identifier"}],
            "relationships": [],
            "sourceConnectorId": "connector-1",
            "source": "company_harvester",
        },
    ])
    monkeypatch.setattr(agent_builder, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_builder, "tools_collection", _Collection())
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", _Collection())
    monkeypatch.setattr(agent_builder, "entities_collection", entities)
    agents = _Collection()
    monkeypatch.setattr(agent_builder, "agents_collection", agents)

    result = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        runtime_kinds=["model_agent"],
    )

    assert result["entityCount"] == 2
    assert agents.docs[0]["entities"]["nodes"][0]["name"] == "Claim"
    assert {node["name"] for node in agents.docs[0]["entities"]["nodes"]} == {"Claim", "Customer"}
    assert agents.docs[0]["entities"]["edges"] == [
        {"from": "Claim", "to": "Customer", "name": "customer", "kind": "belongsTo", "via": "customerId", "description": ""}
    ]
    assert agents.docs[0]["generatedFrom"]["entityIds"] == ["ent-claim", "ent-customer"]
