import pytest

from app.services import company_harvester, task_harvester
from ica import benchmark as infinite_company_arena
from ica.company_harvesters.schemas import CompanyHarvesterOutput
from ica.demo_companies import web_source_collector
from ica.demo_companies.web_source_collector import collect_web_snapshot, collect_web_snapshot_from_html
from ica.evaluation.task_discovery import evaluate_task_discovery


class _InsertResult:
    inserted_id = "inserted"


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, length=100):
        return [dict(doc) for doc in self.docs[:length]]


class _MemoryCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def _matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
                continue
            if doc.get(key) != value:
                return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _InsertResult()

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if self._matches(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return {key: value for key, value in doc.items() if key != "_id"}
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return _InsertResult()
        if upsert:
            self.docs.append({**query, **update.get("$setOnInsert", {}), **update.get("$set", {})})
        return _InsertResult()


@pytest.fixture()
def collections(monkeypatch):
    data = {
        "intakes": _MemoryCollection(),
        "runs": _MemoryCollection(),
        "connectors": _MemoryCollection(),
        "tools": _MemoryCollection(),
        "knowledge_docs": _MemoryCollection(),
        "benchmarks": _MemoryCollection(),
        "tasks": _MemoryCollection(),
        "entities": _MemoryCollection(),
    }
    monkeypatch.setattr(company_harvester, "company_intakes_collection", data["intakes"])
    monkeypatch.setattr(company_harvester, "company_harvest_runs_collection", data["runs"])
    monkeypatch.setattr(company_harvester, "connectors_collection", data["connectors"])
    monkeypatch.setattr(company_harvester, "tools_collection", data["tools"])
    monkeypatch.setattr(company_harvester, "knowledge_documents_collection", data["knowledge_docs"])
    monkeypatch.setattr(company_harvester, "benchmarks_collection", data["benchmarks"])
    monkeypatch.setattr(company_harvester, "benchmark_tasks_collection", data["tasks"])
    monkeypatch.setattr(company_harvester, "entities_collection", data["entities"])
    monkeypatch.setattr(task_harvester, "connectors_collection", data["connectors"])
    monkeypatch.setattr(task_harvester, "tools_collection", data["tools"])
    return data


def test_autoclaims_manifest_materializes_web_api_docs_and_tasks():
    project = infinite_company_arena.load_demo_project("autoclaims")
    materialized = infinite_company_arena.materialize_project(project)

    kinds = [material["kind"] for material in materialized.materials]
    assert "website" in kinds
    assert "openapi" in kinds
    assert kinds.count("document_url") == 2
    assert kinds.count("code_file") == 2
    assert "auth_note" in kinds
    assert len(materialized.userTasks) == 5

    api_material = next(material for material in materialized.materials if material["kind"] == "openapi")
    assert api_material["metadata"]["connector"]["type"] == "api"
    assert api_material["metadata"]["openApiUrl"].endswith("/openapi.json")

    web_material = next(material for material in materialized.materials if material["kind"] == "website")
    assert {hint["name"] for hint in web_material["metadata"]["uiTaskHints"]} == {"Add claim note from UI"}

    doc_material = next(material for material in materialized.materials if material["name"] == "Claims Policy")
    assert "AutoClaims may approve" in doc_material["content"]
    code_material = next(material for material in materialized.materials if material["name"] == "AutoClaims Backend Code")
    assert "FastAPI" in code_material["content"]


def test_autoclaims_benchmark_modes_materialize_separate_surfaces_and_tasks():
    project = infinite_company_arena.load_demo_project("autoclaims")

    api_only = infinite_company_arena.materialize_project(project, mode="api_only")
    assert api_only.mode == "api_only"
    assert {material["kind"] for material in api_only.materials} == {"openapi", "auth_note"}
    assert [task["metadata"]["icaTaskId"] for task in api_only.userTasks] == ["find_claim_status"]
    assert api_only.expectedHarvest.connectors == ["api"]
    assert all(task["metadata"]["prefersApi"] for task in api_only.userTasks)
    assert not any(task["metadata"]["requiresBrowser"] for task in api_only.userTasks)

    api_documents = infinite_company_arena.materialize_project(project, mode="api_documents")
    assert api_documents.mode == "api_documents"
    assert {material["kind"] for material in api_documents.materials} == {"openapi", "document_url", "auth_note"}
    assert [task["metadata"]["icaTaskId"] for task in api_documents.userTasks] == [
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "customer_summary",
    ]
    assert api_documents.expectedHarvest.connectors == ["api", "knowledge"]

    web_only = infinite_company_arena.materialize_project(project, mode="web_only")
    assert web_only.mode == "web_only"
    assert {material["kind"] for material in web_only.materials} == {"website", "auth_note"}
    assert [task["metadata"]["icaTaskId"] for task in web_only.userTasks] == ["web_add_claim_note"]
    assert web_only.expectedHarvest.connectors == ["web"]
    assert web_only.userTasks[0]["metadata"]["requiresBrowser"] is True

    code_only = infinite_company_arena.materialize_project(project, mode="code_only")
    assert code_only.mode == "code_only"
    assert {material["kind"] for material in code_only.materials} == {"code_file", "auth_note"}
    assert {"find_claim_status", "web_add_claim_note"} <= {task["metadata"]["icaTaskId"] for task in code_only.userTasks}
    assert "code" in code_only.expectedHarvest.connectors
    assert all(task["metadata"]["usesCode"] for task in code_only.userTasks)

    all_sources = infinite_company_arena.materialize_project(project, mode="all_sources")
    assert all_sources.mode == "all_sources"
    assert {material["kind"] for material in all_sources.materials} == {"website", "openapi", "document_url", "code_file", "auth_note"}
    assert len(all_sources.userTasks) == 5

    discovery_input = infinite_company_arena.materialize_project(project, mode="all_sources", include_ground_truth_tasks=False)
    assert discovery_input.userTasks == []
    web_material = next(material for material in discovery_input.materials if material["kind"] == "website")
    assert "uiTaskHints" not in web_material["metadata"]


def test_web_source_collector_extracts_ui_signals_from_html():
    snapshot = collect_web_snapshot_from_html(
        url="https://example.test/app",
        html="""
        <html><head><title>Ops Console</title></head>
        <body>
          <h1>Claims</h1>
          <form id="claim-search"><input id="claim-id" placeholder="Claim id" /></form>
          <button aria-label="Add claim note">Add note</button>
          <a href="/claims">Claims list</a>
        </body></html>
        """,
    )

    assert snapshot["title"] == "Ops Console"
    assert snapshot["headings"] == ["Claims"]
    assert snapshot["buttons"][0]["label"] == "Add claim note Add note"
    assert snapshot["inputs"][0]["placeholder"] == "Claim id"
    assert snapshot["links"][0]["href"] == "/claims"


def test_web_source_collector_auto_falls_back_to_html(monkeypatch):
    monkeypatch.setattr(
        web_source_collector,
        "collect_web_snapshot_browser",
        lambda url, timeout_seconds=6.0, screenshot=False: {"status": "failed", "error": "browser missing"},
    )
    monkeypatch.setattr(
        web_source_collector,
        "collect_web_snapshot_html",
        lambda url, timeout_seconds=2.0, max_bytes=800_000: {
            "url": url,
            "collectorMode": "html",
            "status": "ok",
            "title": "Fallback",
            "headings": [],
            "buttons": [],
            "inputs": [],
            "links": [],
            "forms": [],
            "visibleText": ["Fallback"],
            "stats": {},
        },
    )

    snapshot = collect_web_snapshot("https://example.test/app", mode="auto")

    assert snapshot["status"] == "ok"
    assert snapshot["collectorMode"] == "auto_html_fallback"
    assert snapshot["browserFallbackError"] == "browser missing"


def test_web_only_discovery_input_can_include_ground_truth_free_snapshot(monkeypatch):
    project = infinite_company_arena.load_demo_project("autocalendar_web")

    monkeypatch.setattr(
        "ica.demo_companies.materializer.web_snapshot_material",
        lambda *, name, url, metadata=None: {
            "kind": "website_snapshot",
            "name": f"{name} UI snapshot",
            "url": url,
            "content": "Calendar Create new event Search work Month view",
            "metadata": {**(metadata or {}), "collector": "test", "snapshot": {"status": "ok"}},
        },
    )
    materialized = infinite_company_arena.materialize_project(
        project,
        mode="web_only",
        include_ground_truth_tasks=False,
        collect_web_snapshots=True,
    )

    assert [material["kind"] for material in materialized.materials] == ["website", "website_snapshot"]
    assert materialized.userTasks == []
    assert "uiTaskHints" not in materialized.materials[0]["metadata"]
    assert materialized.materials[1]["metadata"]["groundTruthFree"] is True


def test_autopricing_materializes_code_only_company():
    project = infinite_company_arena.load_demo_project("autopricing")
    materialized = infinite_company_arena.materialize_project(project, mode="code_only")

    assert materialized.mode == "code_only"
    assert [material["kind"] for material in materialized.materials] == ["code_file"]
    assert "calculate_enterprise_discount" in materialized.materials[0]["content"]
    assert materialized.expectedHarvest.connectors == ["code"]
    assert [task["metadata"]["icaTaskId"] for task in materialized.userTasks] == ["calculate_enterprise_discount"]


def test_legacy_demo_web_wrapper_loads_as_web_only_ica_project():
    project = infinite_company_arena.load_demo_project("autocinema_web")
    materialized = infinite_company_arena.materialize_project(project, mode="web_only")

    assert project.projectId == "autocinema_web"
    assert materialized.expectedHarvest.connectors == ["web"]
    assert [material["kind"] for material in materialized.materials] == ["website"]
    assert materialized.materials[0]["metadata"]["legacyDemoWeb"] is True
    assert materialized.userTasks[0]["metadata"]["requiresBrowser"] is True


def test_autocalendar_web_uses_real_iwa_task_suite():
    project = infinite_company_arena.load_demo_project("autocalendar_web")
    materialized = infinite_company_arena.materialize_project(project, mode="web_only")

    assert [task["metadata"]["icaTaskId"] for task in materialized.userTasks] == [
        "iwa_select_month",
        "iwa_add_event",
        "iwa_search_submit",
    ]
    assert {task.metadata["iwaUseCase"] for task in project.tasks} == {"SELECT_MONTH", "ADD_EVENT", "SEARCH_SUBMIT"}
    assert {solution.taskId for solution in project.expectedSolutions} == {"iwa_select_month", "iwa_add_event", "iwa_search_submit"}


def test_only_web_task_discovery_scores_partial_iwa_recall():
    project = infinite_company_arena.load_demo_project("autobooks_web")

    result = evaluate_task_discovery(
        project=project,
        mode="web_only",
        discovered_tasks=[
            {
                "taskId": "find_book",
                "name": "Find a book in the AutoBooks catalog",
                "prompt": "Search the catalog and inspect book details.",
                "expectedSurfaces": ["web"],
            },
            {
                "taskId": "add_book_to_cart",
                "name": "Add a book to the shopping cart",
                "prompt": "Use the web UI to add a selected book to cart.",
                "expectedSurfaces": ["web"],
            },
        ],
    )

    assert result.passed is False
    assert result.score == result.recall
    assert result.matchedCount == 2
    assert result.expectedCount == 3
    assert result.missingTaskIds == ["iwa_registration_book"]


def test_company_harvester_output_accepts_javascript_custom_tool_code():
    output = CompanyHarvesterOutput.model_validate(
        {
            "companyId": "demo-company",
            "proposedTasks": [{"taskId": "task-1", "name": "Task 1", "prompt": "Do task 1"}],
            "taskSolutions": [
                {
                    "taskId": "task-1",
                    "tools": [
                        {
                            "name": "demo.custom_tool",
                            "origin": "proposed_custom",
                            "customToolCode": {
                                "language": "javascript",
                                "functionName": "run",
                                "code": "export async function run() { return true; }",
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert output.taskSolutions[0].tools[0].customToolCode
    assert output.taskSolutions[0].tools[0].customToolCode.language == "javascript"


@pytest.mark.asyncio
async def test_autoclaims_company_harvester_discovers_multisurface_company(collections):
    project = infinite_company_arena.load_demo_project("autoclaims")
    result = await infinite_company_arena.seed_company_harvester_from_project(
        project,
        email="owner@example.com",
        company_id="ica-company",
        process=True,
    )

    assert result["run"]["status"] == "solving_tasks"
    connector_types = {connector["type"] for connector in collections["connectors"].docs}
    assert {"web", "api", "knowledge"} <= connector_types

    tool_names = {tool["name"] for tool in collections["tools"].docs}
    assert "autoclaims.api.searchcustomers" in tool_names
    assert "autoclaims.api.listclaims" in tool_names
    assert "knowledge.company_docs.search" in tool_names
    assert "autoclaims.web.explore_workflows" in tool_names

    tasks_by_name = {task["name"]: task for task in collections["tasks"].docs}
    assert "Approve low risk claim" in tasks_by_name
    assert "Add claim note from UI" in tasks_by_name
    knowledge_task = next(task for task in collections["tasks"].docs if task.get("metadata", {}).get("sourceMaterialKind") == "document_url")
    assert len(tasks_by_name) >= project.expectedHarvest.minimumTaskCount

    api_strategy = await task_harvester.plan_task_strategy(tasks_by_name["Validate autoclaims.api.listclaims"])
    web_strategy = await task_harvester.plan_task_strategy(tasks_by_name["Add claim note from UI"])
    knowledge_strategy = await task_harvester.plan_task_strategy(knowledge_task)

    assert api_strategy["strategy"] == "api_tool"
    assert web_strategy["strategy"] == "browser"
    assert knowledge_strategy["strategy"] == "knowledge"


@pytest.mark.asyncio
async def test_ica_evaluate_project_scores_company_harvester_discovery(collections):
    project = infinite_company_arena.load_demo_project("autoclaims")

    result = await infinite_company_arena.evaluate_project_company_harvest(
        project,
        email="owner@example.com",
        company_id="ica-eval-company",
        mode="all_sources",
        process=True,
    )

    assert result.projectId == "autoclaims"
    assert result.mode == "all_sources"
    assert result.passed is False
    assert result.score < 1.0
    assert result.phases["inventory"]["passed"] is True
    assert result.phases["solutionDiscovery"]["passed"] is False
    assert set(result.phases["solutionDiscovery"]["missingTaskIds"]) == {
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "web_add_claim_note",
        "customer_summary",
    }
    assert result.phases["taskDiscovery"]["passed"] is False
    assert set(result.phases["taskDiscovery"]["missingTaskIds"]) == {
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "web_add_claim_note",
        "customer_summary",
    }
    intake = collections["intakes"].docs[0]
    assert intake["userTasks"] == []


def test_ica_task_discovery_evaluator_matches_ground_truth_suite():
    project = infinite_company_arena.load_demo_project("autoclaims")
    discovered = [
        {"taskId": "d1", "name": "Check claim status", "prompt": "Get claim details and latest note for a CLM id."},
        {"taskId": "d2", "name": "Approve eligible claim", "prompt": "Use policy and set claim decision approved."},
        {"taskId": "d3", "name": "Manual review for fraud flag", "prompt": "Escalate claim to manual review when fraud is present."},
        {"taskId": "d4", "name": "Add note to claim", "prompt": "Use the UI to add a callback note to a claim."},
        {"taskId": "d5", "name": "Summarize customer claims", "prompt": "List customer open claims and summarize next actions."},
    ]

    result = infinite_company_arena.evaluate_task_discovery(project=project, discovered_tasks=discovered, mode="all_sources")

    assert result.passed is True
    assert result.recall == 1.0
    assert result.matchedCount == 5
    assert result.missingTaskIds == []


def test_ica_task_discovery_allows_extra_discovered_tasks_without_failing_recall():
    project = infinite_company_arena.load_demo_project("autoclaims")
    discovered = [
        {"taskId": "d1", "name": "Check claim status", "prompt": "Get claim details and latest note for a CLM id."},
        {"taskId": "d2", "name": "Approve eligible claim", "prompt": "Use policy and set claim decision approved."},
        {"taskId": "d3", "name": "Manual review for fraud flag", "prompt": "Escalate claim to manual review when fraud is present."},
        {"taskId": "d4", "name": "Add note to claim", "prompt": "Use the UI to add a callback note to a claim."},
        {"taskId": "d5", "name": "Summarize customer claims", "prompt": "List customer open claims and summarize next actions."},
        {"taskId": "extra", "name": "Export audit report", "prompt": "Export an operational audit report."},
    ]

    result = infinite_company_arena.evaluate_task_discovery(project=project, discovered_tasks=discovered, mode="all_sources")

    assert result.passed is True
    assert result.recall == 1.0
    assert result.score == 1.0
    assert result.precision < 1.0
    assert result.extraTaskNames == ["Export audit report"]


def test_ica_solution_discovery_requires_agent_building_blocks():
    project = infinite_company_arena.load_demo_project("autoclaims")
    snapshot = {
        "connectors": [
            {"type": "api", "origin": "derived_from_openapi", "evidence": [{"openapi": True}]},
            {"type": "knowledge", "origin": "existing", "evidence": [{"inventory": True}]},
            {"type": "web", "origin": "existing", "evidence": [{"inventory": True}]},
            {"type": "code", "origin": "existing", "evidence": [{"inventory": True}]},
        ],
        "tools": [
            {"name": "knowledge.company_docs.search", "origin": "existing_connector_tool"},
            {"name": "autoclaims.web.explore_workflows", "origin": "existing_connector_tool"},
            {"name": "autoclaims.api.searchcustomers", "origin": "derived_from_openapi", "evidence": [{"operationId": "searchCustomers"}]},
            {"name": "autoclaims.api.listclaims", "origin": "derived_from_openapi", "evidence": [{"operationId": "listClaims"}]},
            {"name": "autoclaims.api.getclaim", "origin": "derived_from_openapi", "evidence": [{"operationId": "getClaim"}]},
            {"name": "autoclaims.api.setclaimdecision", "origin": "derived_from_openapi", "evidence": [{"operationId": "setClaimDecision"}]},
        ],
        "tasks": [],
        "benchmarks": [],
    }

    solutions = infinite_company_arena.propose_task_solutions(project=project, snapshot=snapshot, mode="all_sources")
    result = infinite_company_arena.evaluate_solution_discovery(project=project, solutions=solutions, snapshot=snapshot, mode="all_sources")

    assert result.passed is True
    assert result.solutionCount == 5
    assert {solution.agentProvider.runtimeKind for solution in result.solutions} <= {"model_agent", "claude_code", "codex"}
    assert all(solution.connectors and solution.tools and solution.trajectories and solution.skills for solution in result.solutions)
    assert result.invalidOriginIds == []
    assert result.hallucinatedToolNames == []

    broken = [solution.model_copy(update={"skills": []}) for solution in solutions]
    broken_result = infinite_company_arena.evaluate_solution_discovery(project=project, solutions=broken, snapshot=snapshot, mode="all_sources")
    assert broken_result.passed is False
    assert set(broken_result.incompleteTaskIds) == {
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "web_add_claim_note",
        "customer_summary",
    }

    hallucinated_snapshot = {
        **snapshot,
        "tools": [{"name": "autoclaims.api.getclaim", "origin": "unknown"}],
    }
    hallucinated_solutions = infinite_company_arena.propose_task_solutions(project=project, snapshot=hallucinated_snapshot, mode="api_only")
    hallucinated_result = infinite_company_arena.evaluate_solution_discovery(
        project=project,
        solutions=hallucinated_solutions,
        snapshot=hallucinated_snapshot,
        mode="api_only",
    )
    assert hallucinated_result.passed is False
    assert hallucinated_result.invalidOriginIds


def test_ica_company_harvester_input_includes_allowed_inventory():
    project = infinite_company_arena.load_demo_project("autocommerce")
    materialized = infinite_company_arena.materialize_project(project, mode="all_sources", include_ground_truth_tasks=False)
    request = infinite_company_arena._company_harvester_input_from_materialized(materialized, company_id="company-1")

    inventory = request.availableInventory
    assert {connector["type"] for connector in inventory["connectors"]} == {"web", "api", "knowledge", "code"}
    assert "knowledge.company_docs.search" in {tool["name"] for tool in inventory["tools"]}
    assert "autocommerce.code.inspect" in {tool["name"] for tool in inventory["tools"]}


def test_ica_task_solution_builds_agent_config():
    project = infinite_company_arena.load_demo_project("autoclaims")
    task = next(task for task in project.tasks if task.taskId == "web_add_claim_note")
    solution = next(solution for solution in project.expectedSolutions if solution.taskId == "web_add_claim_note")

    agent = infinite_company_arena.build_agent_config_from_solution(
        project=project,
        task=task.model_dump(),
        solution=solution,
        email="owner@example.com",
        company_id="company-1",
    )

    assert agent.runtimeKind == "claude_code"
    assert agent.runtimeProfile.provider == "anthropic"
    assert [tool.name for tool in agent.tools] == ["autoclaims.web.explore_workflows"]
    assert [skill.name for skill in agent.skills] == ["Add AutoClaims note through UI"]
    assert agent.skills[0].trajectoryIds == ["autoclaims:web_add_claim_note:web"]
    assert agent.capabilityDiscovery["icaTaskId"] == "web_add_claim_note"


def test_ica_task_solution_build_validation_reports_non_executable_agent():
    project = infinite_company_arena.load_demo_project("autoclaims")
    task = next(task for task in project.tasks if task.taskId == "find_claim_status")
    solution = next(solution for solution in project.expectedSolutions if solution.taskId == "find_claim_status")
    broken_solution = solution.model_copy(update={"trajectories": []})
    agent = infinite_company_arena.build_agent_config_from_solution(
        project=project,
        task=task.model_dump(),
        solution=broken_solution,
    )

    errors = infinite_company_arena.validate_built_agent_config(agent=agent, solution=broken_solution)

    assert "missing_trajectory_tool_calls" in errors


@pytest.mark.asyncio
async def test_autocommerce_agent_execution_runs_task_tests():
    project = infinite_company_arena.load_demo_project("autocommerce")
    result = await infinite_company_arena.evaluate_project_company_harvest(
        project,
        email="owner@example.com",
        company_id="autocommerce-agent-exec",
        mode="all_sources",
        runner=infinite_company_arena.CompanyHarvesterEngineIcaRunner("agentic"),
    )

    execution = result.phases["agentExecution"]
    assert execution["applicable"] is True
    assert execution["passed"] is True
    assert execution["score"] == 1.0
    assert set(execution["passedTaskIds"]) == {"find_order_status", "draft_delayed_refund", "web_update_inventory_note"}
    refund = next(item for item in execution["results"] if item["taskId"] == "draft_delayed_refund")
    assert refund["buildPassed"] is True
    assert refund["agentConfigSummary"]["runtimeKind"] in {"model_agent", "codex", "claude_code"}
    assert refund["agentConfigSummary"]["toolCount"] >= 1
    assert any(assertion["label"] == "refund draft created" and assertion["passed"] for assertion in refund["assertions"])


def test_autoclaims_agent_execution_runs_task_tests_from_expected_solutions():
    project = infinite_company_arena.load_demo_project("autoclaims")

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=project.expectedSolutions, mode="all_sources")

    assert execution.applicable is True
    assert execution.passed is True
    assert execution.score == 1.0
    assert set(execution.passedTaskIds) == {
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "web_add_claim_note",
        "customer_summary",
    }


def test_autopricing_agent_execution_runs_code_only_task_test():
    project = infinite_company_arena.load_demo_project("autopricing")

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=project.expectedSolutions, mode="code_only")

    assert execution.applicable is True
    assert execution.passed is True
    assert execution.score == 1.0
    assert execution.passedTaskIds == ["calculate_enterprise_discount"]


def test_agent_execution_requires_trajectory_tool_calls_not_only_tool_inventory():
    project = infinite_company_arena.load_demo_project("autoclaims")
    solution = next(solution for solution in project.expectedSolutions if solution.taskId == "approve_low_risk_claim")
    broken_trajectory = solution.trajectories[0].model_copy(
        update={
            "toolCalls": [
                call
                for call in solution.trajectories[0].toolCalls
                if call.get("toolName") != "autoclaims.api.setclaimdecision"
            ]
        }
    )
    broken_solution = solution.model_copy(update={"trajectories": [broken_trajectory]})

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=[broken_solution], mode="all_sources")

    assert execution.applicable is True
    assert execution.passed is False
    assert "approve_low_risk_claim" in execution.failedTaskIds
    approve_result = next(result for result in execution.results if result.taskId == "approve_low_risk_claim")
    decision_assertion = next(assertion for assertion in approve_result.assertions if assertion["label"] == "required tool autoclaims.api.setclaimdecision")
    assert decision_assertion["passed"] is False


def test_agent_execution_fails_build_when_solution_has_no_trajectory_calls():
    project = infinite_company_arena.load_demo_project("autoclaims")
    solution = next(solution for solution in project.expectedSolutions if solution.taskId == "find_claim_status")
    broken_solution = solution.model_copy(update={"trajectories": []})

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=[broken_solution], mode="api_only")

    assert execution.applicable is True
    assert execution.passed is False
    result = execution.results[0]
    assert result.taskId == "find_claim_status"
    assert result.buildPassed is False
    assert "missing_trajectory_tool_calls" in result.buildErrors
    assert result.error == "agent_build_failed"


def test_agent_execution_reports_missing_execution_tests():
    project = infinite_company_arena.load_demo_project("autostats_web")

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=[], mode="web_only")

    assert execution.applicable is False
    assert execution.skippedReason == "no_execution_tests"
    assert execution.expectedTaskCount == 0


def test_autocalendar_iwa_execution_harness_runs_expected_solutions():
    project = infinite_company_arena.load_demo_project("autocalendar_web")

    execution = infinite_company_arena.evaluate_agent_execution(project=project, solutions=project.expectedSolutions, mode="web_only")

    assert execution.applicable is True
    assert execution.executionMode == "trajectory_replay_harness"
    assert execution.runtimeExecuted is False
    assert execution.passed is True
    assert set(execution.passedTaskIds) == {"iwa_select_month", "iwa_add_event", "iwa_search_submit"}


def test_ica_evaluation_reports_missing_requirements():
    project = infinite_company_arena.load_demo_project("autoclaims")

    result = infinite_company_arena.evaluate_company_harvest_snapshot(
        project=project,
        snapshot={
            "connectors": [{"type": "web"}],
            "tools": [{"name": "autoclaims.web.explore_workflows"}],
            "tasks": [],
            "benchmarks": [],
        },
        expected_harvest=project.expectedHarvest,
    )

    assert result.passed is False
    assert result.score < 1.0
    assert result.connectors.missing == ["api", "code", "knowledge"]
    assert "api_tools:required" in result.missing
    assert "knowledge:required" in result.missing
    assert "tasks:0/5" in result.missing
