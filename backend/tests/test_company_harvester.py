import pytest

from app.models.agent_config import AgentConfig
from app.request_scope import RequestScope
from app.routes import company_harvester as company_harvester_route
from app.runtimes.base import AgentRuntimeProfile
from app.services import company_harvester


class _InsertResult:
    inserted_id = "inserted"


class _MemoryCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _InsertResult()

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return {key: value for key, value in doc.items() if key != "_id"}
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                doc.update(update.get("$setOnInsert", {}))
                return _InsertResult()
        if upsert:
            doc = {**query, **update.get("$setOnInsert", {}), **update.get("$set", {})}
            self.docs.append(doc)
        return _InsertResult()


@pytest.fixture(autouse=True)
def _patch_entities_collection(monkeypatch):
    entities = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "entities_collection", entities)
    return entities


def test_agent_config_accepts_three_runtime_profiles():
    for kind in ("codex", "claude_code", "model_agent"):
        profile = AgentRuntimeProfile(kind=kind, provider="anthropic" if kind == "claude_code" else "openai")
        config = AgentConfig(agentId=f"agent-{kind}", name=f"{kind} Agent", runtimeKind=kind, runtimeProfile=profile)
        assert config.runtimeKind == kind
        assert config.runtimeProfile.kind == kind


def test_custom_connector_executor_blueprints_recompute_registration_status():
    from app.services import custom_connector_executors

    custom_connector_executors.clear_custom_connector_executors()
    try:
        tool = {
            "toolId": "tool-payroll",
            "name": "payroll.lookup_employee",
            "connectorId": "payroll",
            "runtimeExecutor": "custom.payroll.lookup_employee",
            "executorBlueprint": {
                "executorName": "custom.payroll.lookup_employee",
                "registrationStatus": "missing",
                "toolName": "payroll.lookup_employee",
            },
        }

        assert company_harvester._custom_connector_executor_blueprints_from_tools([tool])[0]["registrationStatus"] == "missing"

        custom_connector_executors.register_custom_connector_executor("custom.payroll.lookup_employee", lambda _payload: {"ok": True})

        assert company_harvester._custom_connector_executor_blueprints_from_tools([tool])[0]["registrationStatus"] == "registered"
    finally:
        custom_connector_executors.clear_custom_connector_executors()


@pytest.mark.asyncio
async def test_inline_task_harvest_route_blocks_promotion_on_implementation_required(monkeypatch):
    async def harvest_benchmark_tasks(benchmark_id, **kwargs):
        return {
            "benchmarkId": benchmark_id,
            "count": 1,
            "implementationRequiredCount": 1,
            "results": [{"taskId": "task-1", "status": "implementation_required"}],
        }

    async def judge_and_promote_benchmark_trajectories(*_args, **_kwargs):
        raise AssertionError("Promotion should be blocked")

    monkeypatch.setattr(company_harvester_route, "harvest_benchmark_tasks", harvest_benchmark_tasks)
    monkeypatch.setattr(company_harvester_route, "judge_and_promote_benchmark_trajectories", judge_and_promote_benchmark_trajectories)

    result = await company_harvester_route.start_task_harvest(
        company_harvester_route.TaskHarvestRequest(
            email="owner@example.com",
            benchmarkId="bench-1",
            inline=True,
            promoteSkills=True,
            buildAgents=True,
            companyId="company-1",
        ),
        scope=RequestScope(email="owner@example.com"),
    )

    assert result == {
        "success": True,
        "result": {
            "benchmarkId": "bench-1",
            "count": 1,
            "implementationRequiredCount": 1,
            "results": [{"taskId": "task-1", "status": "implementation_required"}],
        },
        "blockedActions": [
            {
                "kind": "promote_or_build_agents",
                "reason": "task_harvest_requires_connector_implementation",
                "benchmarkId": "bench-1",
            }
        ],
    }


@pytest.mark.asyncio
async def test_company_harvest_run_has_normal_and_dev_views(monkeypatch, _patch_entities_collection):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {"kind": "document_url", "name": "Policy", "url": "https://example.com/policy.pdf"},
            {"kind": "openapi", "name": "CRM API", "url": "https://example.com/openapi.json"},
            {"kind": "website", "name": "CRM", "url": "https://crm.example.com"},
        ],
        user_tasks=[{"name": "Claim status", "prompt": "Find claim status and draft a reply."}],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status(run["runId"], mode="dev", email="owner@example.com")

    assert normal["summary"]["materialsReceived"] == 3
    assert normal["summary"]["knowledgeSourcesFound"] == 1
    assert normal["summary"]["systemsFound"] == 3
    assert normal["summary"]["taskCandidatesFound"] == 4
    assert normal["summary"]["entityCandidatesFound"] == 0
    assert normal["summary"]["connectorsReadyForFactory"] == 3
    assert normal["summary"]["benchmarkId"].startswith("company-1:company_harvest:")
    assert normal["nextAction"]["kind"] == "run_task_harvester"
    assert processed["status"] == "solving_tasks"
    assert all(step["visibility"] == "normal" for step in normal["steps"])
    assert len(dev["artifacts"]) >= 11
    assert {"knowledge_document", "connector_candidate", "tool_candidate", "task_candidate", "benchmark"} <= set(dev["devSummary"]["artifactKinds"])
    assert "entity_candidate" not in set(dev["devSummary"]["artifactKinds"])
    assert len(connectors.docs) == 3
    assert {doc["type"] for doc in connectors.docs} == {"knowledge", "api", "web"}
    assert all(doc["capabilityDiscovery"]["toolSynthesis"]["typedToolCount"] == 1 for doc in connectors.docs)
    assert all(doc["capabilityDiscovery"]["candidateTasks"]["count"] >= 1 for doc in connectors.docs)
    assert all(doc["capabilityDiscovery"]["ingestionPipeline"]["state"] in {"needs_benchmark", "ready"} for doc in connectors.docs)
    assert all(doc["toolIds"] for doc in connectors.docs)
    assert len(tools.docs) == 3
    assert _patch_entities_collection.docs == []
    assert len(knowledge_docs.docs) == 1
    assert knowledge_docs.docs[0]["resourceContract"]["resourceKind"] == "document"
    assert knowledge_docs.docs[0]["status"] == "pending_indexing"
    assert dev["devSummary"]["knowledgeDocumentIds"] == [knowledge_docs.docs[0]["documentId"]]
    assert {doc["executionType"] for doc in tools.docs} == {"knowledge_search", "api_call", "browser_automation"}
    assert all(doc["toolContract"]["format"] == "autoppia.tool_contract" for doc in tools.docs)
    assert len(benchmarks.docs) == 1
    assert benchmarks.docs[0]["taskCount"] == 4
    assert len(tasks.docs) == 4
    assert all(task["status"] == "needs_harvest" for task in tasks.docs)
    assert all(task["trajectoryId"] == "" for task in tasks.docs)
    by_name = {task["name"]: task for task in tasks.docs}
    assert by_name["Inspect CRM API"]["metadata"]["expectedTools"] == ["crm.api.discover_operations"]
    assert by_name["Explore CRM"]["metadata"]["expectedTools"] == ["crm.explore_workflows"]
    assert by_name["Answer from Policy"]["metadata"]["expectedTools"] == ["knowledge.company_docs.search"]


@pytest.mark.asyncio
async def test_company_harvest_only_creates_explicit_business_entities(monkeypatch, _patch_entities_collection):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "knowledge_note",
                "name": "Celeris domain",
                "content": "Celeris tracks customer cases.",
                "metadata": {
                    "entities": [
                        {
                            "name": "CustomerCase",
                            "description": "A customer support case owned by Celeris.",
                            "fields": [
                                {"name": "caseId", "type": "string", "role": "identifier", "required": True},
                                {"name": "status", "type": "string", "role": "status"},
                            ],
                        }
                    ]
                },
            }
        ],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    await company_harvester.process_company_harvest_run(run["runId"])

    assert len(_patch_entities_collection.docs) == 1
    assert _patch_entities_collection.docs[0]["name"] == "CustomerCase"
    assert _patch_entities_collection.docs[0]["metadata"]["inferenceSource"] == "material_metadata"
    assert _patch_entities_collection.docs[0]["fields"][0]["name"] == "caseId"


@pytest.mark.asyncio
async def test_company_harvest_blocks_for_missing_company_material(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")

    assert processed["status"] == "needs_user_input"
    assert normal["status"] == "needs_user_input"
    assert normal["nextAction"]["kind"] == "answer_questions"
    assert normal["questions"][0]["code"] == "company_material_required"
    assert normal["summary"]["blockedItems"][0]["code"] == "company_material_required"
    assert connectors.docs == []
    assert tools.docs == []
    assert benchmarks.docs == []
    assert tasks.docs == []


@pytest.mark.asyncio
async def test_company_harvest_creates_tasks_from_explicit_connector_tools(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "openapi",
                "name": "Claims API",
                "url": "https://api.example.com/openapi.json",
                "metadata": {
                    "tools": [
                        {
                            "name": "claims.search_claims",
                            "description": "Search claims.",
                            "sideEffects": "reads",
                            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                        },
                        {
                            "name": "claims.update_claim_status",
                            "description": "Update claim status.",
                            "sideEffects": "writes",
                            "inputSchema": {"type": "object", "properties": {"claimId": {"type": "string"}}, "required": ["claimId"]},
                        },
                    ]
                },
            }
        ],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status(run["runId"], mode="dev", email="owner@example.com")

    assert processed["status"] == "solving_tasks"
    assert len(tools.docs) == 2
    assert {tool["name"] for tool in tools.docs} == {"claims.search_claims", "claims.update_claim_status"}
    assert len(tasks.docs) == 3
    by_name = {task["name"]: task for task in tasks.docs}
    assert by_name["Validate claims.search_claims"]["metadata"]["expectedTools"] == ["claims.search_claims"]
    assert by_name["Validate claims.search_claims"]["metadata"]["prefersApi"] is True
    assert by_name["Validate claims.search_claims"]["riskClass"] == "read"
    assert by_name["Validate claims.update_claim_status"]["riskClass"] == "write"
    assert by_name["Inspect Claims API"]["metadata"]["expectedTools"] == ["claims.api.discover_operations"]


@pytest.mark.asyncio
async def test_company_harvest_synthesizes_tools_and_tasks_from_openapi_spec(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "openapi",
                "name": "Claims API",
                "url": "https://api.example.com/openapi.json",
                "metadata": {
                    "openapi": {
                        "openapi": "3.1.0",
                        "paths": {
                            "/claims": {
                                "get": {
                                    "operationId": "searchClaims",
                                    "summary": "Search claims",
                                    "parameters": [{"name": "query", "in": "query", "schema": {"type": "string"}, "required": True}],
                                    "responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "title": "ClaimSearchResult"}}}}},
                                }
                            },
                            "/claims/{claimId}/status": {
                                "patch": {
                                    "operationId": "updateClaimStatus",
                                    "summary": "Update claim status",
                                    "parameters": [{"name": "claimId", "in": "path", "schema": {"type": "string"}, "required": True}],
                                    "requestBody": {
                                        "required": True,
                                        "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}}}}},
                                    },
                                    "responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "title": "Claim"}}}}},
                                }
                            },
                        },
                    }
                },
            }
        ],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status(run["runId"], mode="dev", email="owner@example.com")

    assert processed["status"] == "solving_tasks"
    assert {tool["name"] for tool in tools.docs} == {"claims.api.searchclaims", "claims.api.updateclaimstatus"}
    assert {tool["policyBoundary"] for tool in tools.docs} == {"read", "write"}
    assert all(tool["metadata"]["openapiPath"] for tool in tools.docs)
    assert len(tasks.docs) == 3
    by_name = {task["name"]: task for task in tasks.docs}
    assert by_name["Validate claims.api.searchclaims"]["metadata"]["expectedTools"] == ["claims.api.searchclaims"]
    assert by_name["Validate claims.api.searchclaims"]["riskClass"] == "read"
    assert by_name["Validate claims.api.updateclaimstatus"]["metadata"]["expectedTools"] == ["claims.api.updateclaimstatus"]
    assert by_name["Validate claims.api.updateclaimstatus"]["riskClass"] == "write"
    assert by_name["Inspect Claims API"]["metadata"]["expectedTools"] == ["claims.api.discover_operations"]
    assert connectors.docs[0]["capabilityDiscovery"]["toolSynthesis"]["typedToolCount"] == 2
    assert connectors.docs[0]["capabilityDiscovery"]["candidateTasks"]["count"] == 3


@pytest.mark.asyncio
async def test_company_harvest_creates_custom_connectors_from_system_specs(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "knowledge_note",
                "name": "Operations context",
                "content": "Celeris handles payroll requests in a legacy ERP.",
                "metadata": {
                    "systems": [
                        {
                            "name": "Payroll ERP",
                            "surface": "custom",
                            "description": "Legacy payroll system without an existing connector.",
                            "tools": [
                                {
                                    "name": "payroll.lookup_employee",
                                    "description": "Look up employee payroll status.",
                                    "inputSchema": {"type": "object", "properties": {"employeeEmail": {"type": "string"}}, "required": ["employeeEmail"]},
                                    "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
                                    "sideEffects": "reads",
                                }
                            ],
                            "tasks": [
                                {
                                    "name": "Check payroll status",
                                    "prompt": "Look up an employee payroll status and summarize whether HR follow-up is needed.",
                                    "successCriteria": "Payroll status is found or a connector implementation gap is recorded.",
                                    "toolName": "payroll.lookup_employee",
                                }
                            ],
                        }
                    ]
                },
            }
        ],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status(run["runId"], mode="dev", email="owner@example.com")

    assert processed["status"] == "solving_tasks"
    assert {doc["type"] for doc in connectors.docs} == {"knowledge", "custom"}
    custom = next(doc for doc in connectors.docs if doc["type"] == "custom")
    assert custom["name"] == "Payroll ERP"
    assert custom["generationStatus"] == "connector_spec_provided"
    assert custom["connectorSpec"]["tools"][0]["name"] == "payroll.lookup_employee"
    assert custom["capabilityDiscovery"]["toolIds"]
    assert {tool["name"] for tool in tools.docs} == {"knowledge.company_docs.search", "payroll.lookup_employee"}
    payroll_tool = next(tool for tool in tools.docs if tool["name"] == "payroll.lookup_employee")
    assert payroll_tool["connectorId"] == custom["connectorId"]
    assert payroll_tool["executionType"] == "connector_tool"
    assert payroll_tool["metadata"]["customConnector"] is True
    assert payroll_tool["executorBlueprint"]["schemaVersion"] == "custom_connector_executor_blueprint/v1"
    assert payroll_tool["executorBlueprint"]["executorName"] == "custom.payroll_erp.lookup_employee"
    assert payroll_tool["executorBlueprint"]["registrationStatus"] == "missing"
    assert payroll_tool["metadata"]["suggestedRuntimeExecutor"] == "custom.payroll_erp.lookup_employee"
    assert len(tasks.docs) == 3
    by_name = {task["name"]: task for task in tasks.docs}
    assert by_name["Validate payroll.lookup_employee"]["metadata"]["customConnector"] is True
    assert by_name["Validate payroll.lookup_employee"]["metadata"]["expectedTools"] == ["payroll.lookup_employee"]
    assert by_name["Validate payroll.lookup_employee"]["allowedSystems"] == [custom["connectorId"]]
    assert by_name["Check payroll status"]["metadata"]["connectorSpecTask"] is True
    assert by_name["Check payroll status"]["metadata"]["expectedTools"] == ["payroll.lookup_employee"]
    assert by_name["Check payroll status"]["allowedSystems"] == [custom["connectorId"]]
    assert benchmarks.docs[0]["taskCount"] == 3
    assert normal["summary"]["connectorImplementationGaps"] == 1
    assert normal["summary"]["connectorImplementationGapIds"] == [custom["connectorId"]]
    assert normal["summary"]["customConnectorExecutorBlueprints"] == 1
    assert normal["summary"]["missingCustomConnectorExecutors"] == 1
    assert normal["summary"]["customConnectorExecutorNames"] == ["custom.payroll_erp.lookup_employee"]
    assert normal["summary"]["recommendedNextAction"] == "Implement missing connector executors"
    assert normal["nextAction"]["kind"] == "implement_connectors"
    assert normal["nextAction"]["executorNames"] == ["custom.payroll_erp.lookup_employee"]
    assert normal["nextAction"]["toolNames"] == ["payroll.lookup_employee"]
    assert normal["nextAction"]["afterAction"] == {
        "kind": "run_task_harvester",
        "label": "Solve discovered benchmark tasks",
        "benchmarkId": benchmarks.docs[0]["benchmarkId"],
    }
    assert dev["devSummary"]["connectorImplementationGaps"][0]["toolNames"] == ["payroll.lookup_employee"]
    assert dev["devSummary"]["customConnectorExecutorBlueprints"][0]["executorName"] == "custom.payroll_erp.lookup_employee"
    assert dev["devSummary"]["customConnectorExecutorBlueprints"][0]["registrationStatus"] == "missing"


@pytest.mark.asyncio
async def test_company_harvest_blocks_and_resumes_custom_connector_auth(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "knowledge_note",
                "name": "Payroll context",
                "content": "Payroll requests are handled in a legacy ERP.",
                "metadata": {
                    "systems": [
                        {
                            "name": "Payroll ERP",
                            "surface": "custom",
                            "authRequired": True,
                            "tools": [{"name": "payroll.lookup_employee", "sideEffects": "reads"}],
                        }
                    ]
                },
            }
        ],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    blocked = await company_harvester.process_company_harvest_run(run["runId"])

    assert blocked["status"] == "needs_user_input"
    assert blocked["questions"][0]["code"] == "custom_connector_auth_required"
    assert blocked["questions"][0]["expectedAnswerType"] == "credentials"
    assert blocked["questions"][0]["metadata"]["connectorName"] == "Payroll ERP"
    assert connectors.docs == []
    assert tools.docs == []
    assert benchmarks.docs == []
    assert tasks.docs == []

    await company_harvester.answer_company_harvest_questions(
        run["runId"],
        email="owner@example.com",
        answers=[
            {
                "questionId": blocked["questions"][0]["questionId"],
                "code": blocked["questions"][0]["code"],
                "credentialRef": "credential:payroll-owner",
            }
        ],
    )
    processed = await company_harvester.process_company_harvest_run(run["runId"])

    assert processed["status"] == "solving_tasks"
    custom = next(doc for doc in connectors.docs if doc["type"] == "custom")
    assert custom["status"] == "connected"
    assert custom["authConfigured"] is True
    assert custom["credentialRefs"] == {"default": "credential:payroll-owner"}
    assert {tool["name"] for tool in tools.docs} == {"knowledge.company_docs.search", "payroll.lookup_employee"}
    assert any(task["metadata"].get("customConnector") for task in tasks.docs)


@pytest.mark.asyncio
async def test_company_harvest_blocks_for_missing_auth(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "website",
                "name": "CRM",
                "url": "https://crm.example.com",
                "metadata": {"authRequired": True},
            }
        ],
        user_tasks=[{"name": "Find customer", "prompt": "Find a customer by email."}],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status(run["runId"], mode="dev", email="owner@example.com")

    assert processed["status"] == "needs_user_input"
    assert normal["questions"][0]["code"] == "website_auth_required"
    assert normal["questions"][0]["expectedAnswerType"] == "credentials"
    assert dev["questions"][0]["metadata"]["url"] == "https://crm.example.com"
    assert connectors.docs == []
    assert tools.docs == []
    assert benchmarks.docs == []
    assert tasks.docs == []


@pytest.mark.asyncio
async def test_company_harvest_answers_unblock_missing_auth_and_resume(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "website",
                "name": "CRM",
                "url": "https://crm.example.com",
                "metadata": {"authRequired": True},
            }
        ],
        user_tasks=[{"name": "Find customer", "prompt": "Find a customer by email."}],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    blocked = await company_harvester.process_company_harvest_run(run["runId"])
    question = blocked["questions"][0]

    answered = await company_harvester.answer_company_harvest_questions(
        run["runId"],
        email="owner@example.com",
        answers=[
            {
                "questionId": question["questionId"],
                "code": question["code"],
                "credentialRef": "credential:crm-owner",
            }
        ],
    )
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")

    assert answered["status"] == "indexing_knowledge"
    assert answered["questions"] == []
    assert normal["questions"] == []
    assert normal["nextAction"]["kind"] == "continue_company_harvest"
    assert any(item["kind"] == "auth_note" for item in intakes.docs[0]["materials"])
    assert any(item["status"] == "answered" for item in answered["artifacts"] if item["kind"] == "question_for_user")

    processed = await company_harvester.process_company_harvest_run(run["runId"])

    assert processed["status"] == "solving_tasks"
    assert len(connectors.docs) == 1
    assert connectors.docs[0]["status"] == "connected"
    assert connectors.docs[0]["authConfigured"] is True
    assert connectors.docs[0]["credentialRefs"] == {"default": "credential:crm-owner"}
    assert "credential:crm-owner" not in str(processed["normalSummary"])
    assert len(tools.docs) == 1
    assert tools.docs[0]["executionType"] == "browser_automation"
    assert len(benchmarks.docs) == 1
    assert len(tasks.docs) == 2


@pytest.mark.asyncio
async def test_company_harvest_applies_auth_answer_to_api_connector(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[{"kind": "openapi", "name": "Claims API", "url": "https://api.example.com/openapi.json", "metadata": {"authRequired": True}}],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    blocked = await company_harvester.process_company_harvest_run(run["runId"])
    question = blocked["questions"][0]
    await company_harvester.answer_company_harvest_questions(
        run["runId"],
        email="owner@example.com",
        answers=[{"questionId": question["questionId"], "code": question["code"], "credentialRef": "credential:claims-api"}],
    )

    processed = await company_harvester.process_company_harvest_run(run["runId"])

    assert processed["status"] == "solving_tasks"
    assert connectors.docs[0]["type"] == "api"
    assert connectors.docs[0]["status"] == "connected"
    assert connectors.docs[0]["credentialRefs"] == {"default": "credential:claims-api"}
    assert len(tools.docs) == 1
    assert tools.docs[0]["executionType"] == "api_call"


@pytest.mark.asyncio
async def test_company_harvest_answer_adds_material_for_empty_intake(monkeypatch):
    intakes = _MemoryCollection()
    runs = _MemoryCollection()
    connectors = _MemoryCollection()
    tools = _MemoryCollection()
    knowledge_docs = _MemoryCollection()
    benchmarks = _MemoryCollection()
    tasks = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_intakes_collection", intakes)
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    monkeypatch.setattr(company_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(company_harvester, "tools_collection", tools)
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(company_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", tasks)

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[],
        user_tasks=[],
        mode="normal",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    blocked = await company_harvester.process_company_harvest_run(run["runId"])
    question = blocked["questions"][0]

    answered = await company_harvester.answer_company_harvest_questions(
        run["runId"],
        email="owner@example.com",
        answers=[
            {
                "questionId": question["questionId"],
                "code": "company_material_required",
                "material": {"kind": "document_url", "name": "Policy", "url": "https://example.com/policy.pdf"},
            }
        ],
    )
    processed = await company_harvester.process_company_harvest_run(run["runId"])

    assert answered["status"] == "indexing_knowledge"
    assert len(intakes.docs[0]["materials"]) == 1
    assert processed["status"] == "solving_tasks"
    assert len(connectors.docs) == 1
    assert connectors.docs[0]["type"] == "knowledge"
    assert len(tools.docs) == 1
    assert tools.docs[0]["name"] == "knowledge.company_docs.search"
    assert len(tasks.docs) == 1


@pytest.mark.asyncio
async def test_company_harvest_records_task_promotion_and_agent_results(monkeypatch):
    runs = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    run = {
        "runId": "run-1",
        "intakeId": "intake-1",
        "email": "owner@example.com",
        "companyId": "company-1",
        "status": "solving_tasks",
        "currentStep": "solving_tasks",
        "steps": company_harvester._new_steps(),
        "artifacts": [],
        "normalSummary": {"benchmarkId": "bench-1", "agentsReady": 0},
        "devSummary": {"benchmarkId": "bench-1"},
        "nextAction": {"kind": "run_task_harvester", "benchmarkId": "bench-1"},
    }
    await runs.insert_one(run)

    updated = await company_harvester.record_company_harvest_results(
        "run-1",
        knowledge_index_jobs=[{"jobId": "job-1", "payload": {"documentId": "doc-1"}}],
        task_harvest={"benchmarkId": "bench-1", "harvestedCount": 2, "failedCount": 0},
        promotion={"benchmarkId": "bench-1", "promotedCount": 1, "skillIds": ["skill-1"]},
        agent_build={
            "companyId": "company-1",
            "agentCount": 3,
            "agentIds": ["agent-a", "agent-b", "agent-c"],
            "skillCount": 1,
            "toolCount": 2,
            "agents": [
                {
                    "agentId": "agent-a",
                    "name": "Ops Agent",
                    "runtimeKind": "model_agent",
                    "status": "ready",
                    "trainingStatus": "verified",
                    "deliverySurfaces": {
                        "chat": {"available": True, "agentId": "agent-a"},
                        "api": {"available": True, "endpoint": "/runtime/agents/agent-a/step"},
                        "widget": {"available": True, "agentId": "agent-a", "embedScript": "/embed/v1/widget.js"},
                    },
                },
                {"agentId": "agent-b", "name": "Codex Agent", "runtimeKind": "codex", "status": "ready", "trainingStatus": "verified"},
                {"agentId": "agent-c", "name": "Claude Agent", "runtimeKind": "claude_code", "status": "ready", "trainingStatus": "verified"},
            ],
        },
    )
    normal = await company_harvester.company_harvest_status("run-1", mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status("run-1", mode="dev", email="owner@example.com")

    assert updated["status"] == "ready"
    assert updated["currentStep"] == "ready"
    assert normal["summary"]["tasksSolved"] == 2
    assert normal["summary"]["knowledgeIndexJobsQueued"] == 1
    assert normal["summary"]["knowledgeIndexDocumentIds"] == ["doc-1"]
    assert normal["summary"]["skillsReady"] == 1
    assert normal["summary"]["agentsReady"] == 3
    assert normal["delivery"]["state"] == "ready"
    assert normal["delivery"]["surfaces"] == {"chat": True, "api": True, "widget": True}
    assert normal["delivery"]["agents"][0]["apiEndpoint"] == "/runtime/agents/agent-a/step"
    assert normal["delivery"]["agents"][0]["widgetAvailable"] is True
    assert normal["delivery"]["agents"][0]["widgetEmbedScript"] == "/embed/v1/widget.js"
    assert "deliverySurfaces" not in normal["delivery"]["agents"][0]
    assert normal["nextAction"]["kind"] == "use_agents"
    assert normal["nextAction"]["delivery"]["agentCount"] == 3
    assert {artifact["kind"] for artifact in dev["artifacts"]} == {"knowledge_document", "trajectory", "skill", "agent_config"}
    assert dev["devSummary"]["knowledgeIndexJobs"][0]["jobId"] == "job-1"
    assert dev["devSummary"]["delivery"]["agents"][0]["deliverySurfaces"]["api"]["endpoint"] == "/runtime/agents/agent-a/step"
    steps = {step["key"]: step for step in dev["steps"]}
    assert steps["solving_tasks"]["status"] == "done"
    assert steps["promoting_skills"]["status"] == "done"
    assert steps["building_agents"]["status"] == "done"


@pytest.mark.asyncio
async def test_company_harvest_records_task_implementation_gaps_as_next_action(monkeypatch):
    runs = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    await runs.insert_one(
        {
            "runId": "run-1",
            "intakeId": "intake-1",
            "email": "owner@example.com",
            "companyId": "company-1",
            "status": "solving_tasks",
            "currentStep": "solving_tasks",
            "steps": company_harvester._new_steps(),
            "artifacts": [],
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {"benchmarkId": "bench-1"},
            "nextAction": {"kind": "run_task_harvester", "benchmarkId": "bench-1"},
        }
    )

    updated = await company_harvester.record_company_harvest_results(
        "run-1",
        task_harvest={
            "benchmarkId": "bench-1",
            "count": 1,
            "results": [
                {
                    "taskId": "task-1",
                    "trajectoryId": "traj-1",
                    "status": "harvested",
                    "strategy": {
                        "strategy": "connector_tool",
                        "executionReadiness": "implementation_required",
                        "implementationGaps": [
                            {
                                "kind": "connector_tool_executor_missing",
                                "connectorId": "payroll",
                                "toolId": "tool-payroll",
                                "toolName": "payroll.lookup_employee",
                                "nextAction": "Implement payroll executor.",
                            }
                        ],
                    },
                }
            ],
        },
    )
    normal = await company_harvester.company_harvest_status("run-1", mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status("run-1", mode="dev", email="owner@example.com")

    assert updated["status"] == "solving_tasks"
    assert normal["summary"]["tasksSolved"] == 1
    assert normal["summary"]["taskImplementationGaps"] == 1
    assert normal["summary"]["taskImplementationGapToolNames"] == ["payroll.lookup_employee"]
    assert normal["nextAction"] == {
        "kind": "implement_connectors",
        "label": "Implement missing connector executors",
        "benchmarkId": "bench-1",
        "toolNames": ["payroll.lookup_employee"],
    }
    assert dev["devSummary"]["taskImplementationGaps"][0]["taskId"] == "task-1"
    assert dev["devSummary"]["taskImplementationGaps"][0]["connectorId"] == "payroll"


@pytest.mark.asyncio
async def test_company_harvest_does_not_count_implementation_required_tasks_as_solved(monkeypatch):
    runs = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    await runs.insert_one(
        {
            "runId": "run-1",
            "intakeId": "intake-1",
            "email": "owner@example.com",
            "companyId": "company-1",
            "status": "solving_tasks",
            "currentStep": "solving_tasks",
            "steps": company_harvester._new_steps(),
            "artifacts": [],
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {"benchmarkId": "bench-1"},
            "nextAction": {"kind": "run_task_harvester", "benchmarkId": "bench-1"},
        }
    )

    updated = await company_harvester.record_company_harvest_results(
        "run-1",
        task_harvest={
            "benchmarkId": "bench-1",
            "count": 1,
            "harvestedCount": 0,
            "failedCount": 0,
            "implementationRequiredCount": 1,
            "results": [
                {
                    "taskId": "task-1",
                    "trajectoryId": "",
                    "status": "implementation_required",
                    "strategy": {
                        "strategy": "connector_tool",
                        "executionReadiness": "implementation_required",
                        "implementationGaps": [
                            {
                                "kind": "connector_tool_executor_missing",
                                "connectorId": "payroll",
                                "toolId": "tool-payroll",
                                "toolName": "payroll.lookup_employee",
                            }
                        ],
                    },
                }
            ],
        },
    )
    normal = await company_harvester.company_harvest_status("run-1", mode="normal", email="owner@example.com")

    assert updated["status"] == "solving_tasks"
    assert normal["summary"]["tasksSolved"] == 0
    assert normal["summary"]["tasksImplementationRequired"] == 1
    assert normal["summary"]["taskHarvestFailures"] == 0
    assert normal["summary"]["taskImplementationGaps"] == 1
    assert normal["nextAction"]["kind"] == "implement_connectors"


@pytest.mark.asyncio
async def test_company_harvest_agent_build_with_missing_executors_is_not_ready(monkeypatch):
    runs = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    await runs.insert_one(
        {
            "runId": "run-1",
            "intakeId": "intake-1",
            "email": "owner@example.com",
            "companyId": "company-1",
            "status": "building_agents",
            "currentStep": "building_agents",
            "steps": company_harvester._new_steps(),
            "artifacts": [],
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {"benchmarkId": "bench-1"},
            "nextAction": {"kind": "build_agents", "benchmarkId": "bench-1"},
        }
    )

    updated = await company_harvester.record_company_harvest_results(
        "run-1",
        agent_build={
            "companyId": "company-1",
            "agentCount": 3,
            "agentIds": ["agent-model", "agent-codex", "agent-claude"],
            "skillCount": 0,
            "toolCount": 1,
            "executableToolCount": 0,
            "missingToolExecutorCount": 1,
            "missingToolNames": ["payroll.lookup_employee"],
            "agents": [
                {
                    "agentId": "agent-model",
                    "name": "Ops Agent",
                    "runtimeKind": "model_agent",
                    "status": "draft",
                    "trainingStatus": "connector_implementation_required",
                    "runtimeReadiness": {
                        "executableToolCount": 0,
                        "missingToolExecutorCount": 1,
                        "missingToolNames": ["payroll.lookup_employee"],
                    },
                    "deliverySurfaces": {
                        "chat": {"available": True, "agentId": "agent-model"},
                        "api": {"available": True, "endpoint": "/runtime/agents/agent-model/step"},
                        "widget": {"available": True, "agentId": "agent-model", "embedScript": "/embed/v1/widget.js"},
                    },
                },
                {
                    "agentId": "agent-codex",
                    "name": "Codex Agent",
                    "runtimeKind": "codex",
                    "status": "draft",
                    "trainingStatus": "connector_implementation_required",
                    "runtimeReadiness": {
                        "executableToolCount": 0,
                        "missingToolExecutorCount": 1,
                        "missingToolNames": ["payroll.lookup_employee"],
                    },
                },
                {
                    "agentId": "agent-claude",
                    "name": "Claude Agent",
                    "runtimeKind": "claude_code",
                    "status": "draft",
                    "trainingStatus": "connector_implementation_required",
                    "runtimeReadiness": {
                        "executableToolCount": 0,
                        "missingToolExecutorCount": 1,
                        "missingToolNames": ["payroll.lookup_employee"],
                    },
                },
            ],
        },
    )
    normal = await company_harvester.company_harvest_status("run-1", mode="normal", email="owner@example.com")
    dev = await company_harvester.company_harvest_status("run-1", mode="dev", email="owner@example.com")

    assert updated["status"] == "building_agents"
    assert normal["status"] == "building_agents"
    assert normal["summary"]["agentsReady"] == 0
    assert normal["summary"]["agentsBlocked"] == 3
    assert normal["summary"]["missingAgentToolExecutorNames"] == ["payroll.lookup_employee"]
    assert normal["delivery"]["state"] == "blocked"
    assert normal["delivery"]["readyAgentCount"] == 0
    assert normal["delivery"]["blockedAgentCount"] == 3
    assert normal["delivery"]["surfaces"] == {"chat": False, "api": False, "widget": False}
    assert normal["delivery"]["agents"][0]["ready"] is False
    assert normal["delivery"]["agents"][0]["chatAvailable"] is False
    assert normal["nextAction"]["kind"] == "implement_connectors"
    assert normal["nextAction"]["toolNames"] == ["payroll.lookup_employee"]
    assert dev["devSummary"]["delivery"]["agents"][0]["runtimeReadiness"]["missingToolExecutorCount"] == 1


@pytest.mark.asyncio
async def test_company_harvest_ready_agent_build_does_not_override_task_implementation_gaps(monkeypatch):
    runs = _MemoryCollection()
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", runs)
    await runs.insert_one(
        {
            "runId": "run-1",
            "intakeId": "intake-1",
            "email": "owner@example.com",
            "companyId": "company-1",
            "status": "solving_tasks",
            "currentStep": "solving_tasks",
            "steps": company_harvester._new_steps(),
            "artifacts": [],
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {"benchmarkId": "bench-1"},
            "nextAction": {"kind": "run_task_harvester", "benchmarkId": "bench-1"},
        }
    )

    updated = await company_harvester.record_company_harvest_results(
        "run-1",
        task_harvest={
            "benchmarkId": "bench-1",
            "count": 1,
            "harvestedCount": 0,
            "implementationRequiredCount": 1,
            "results": [
                {
                    "taskId": "task-1",
                    "trajectoryId": "",
                    "status": "implementation_required",
                    "strategy": {
                        "implementationGaps": [
                            {"toolName": "payroll.lookup_employee", "connectorId": "payroll"}
                        ]
                    },
                }
            ],
        },
        agent_build={
            "companyId": "company-1",
            "agentCount": 1,
            "agentIds": ["agent-model"],
            "skillCount": 1,
            "toolCount": 1,
            "agents": [
                {
                    "agentId": "agent-model",
                    "name": "Ops Agent",
                    "runtimeKind": "model_agent",
                    "status": "ready",
                    "trainingStatus": "verified",
                    "runtimeReadiness": {"missingToolExecutorCount": 0, "missingToolNames": []},
                    "deliverySurfaces": {
                        "chat": {"available": True, "agentId": "agent-model"},
                        "api": {"available": True, "endpoint": "/runtime/agents/agent-model/step"},
                        "widget": {"available": True, "agentId": "agent-model", "embedScript": "/embed/v1/widget.js"},
                    },
                }
            ],
        },
    )
    normal = await company_harvester.company_harvest_status("run-1", mode="normal", email="owner@example.com")

    assert updated["status"] == "building_agents"
    assert normal["delivery"]["state"] == "ready"
    assert normal["summary"]["agentsReady"] == 1
    assert normal["summary"]["taskImplementationGaps"] == 1
    assert normal["nextAction"]["kind"] == "implement_connectors"
    assert normal["nextAction"]["toolNames"] == ["payroll.lookup_employee"]
