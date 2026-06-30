import pytest

from app.services import company_harvester, infinite_company_arena, task_harvester


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
    assert "auth_note" in kinds
    assert len(materialized.userTasks) == 5

    api_material = next(material for material in materialized.materials if material["kind"] == "openapi")
    assert api_material["metadata"]["connector"]["type"] == "api"
    assert api_material["metadata"]["openApiUrl"].endswith("/openapi.json")

    web_material = next(material for material in materialized.materials if material["kind"] == "website")
    assert {hint["name"] for hint in web_material["metadata"]["uiTaskHints"]} == {"Add claim note from UI"}

    doc_material = next(material for material in materialized.materials if material["name"] == "Claims Policy")
    assert "AutoClaims may approve" in doc_material["content"]


def test_autoclaims_benchmark_modes_materialize_separate_surfaces_and_tasks():
    project = infinite_company_arena.load_demo_project("autoclaims")

    api_only = infinite_company_arena.materialize_project(project, mode="api_only")
    assert api_only.mode == "api_only"
    assert {material["kind"] for material in api_only.materials} == {"openapi", "document_url", "auth_note"}
    assert [task["metadata"]["icaTaskId"] for task in api_only.userTasks] == [
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "customer_summary",
    ]
    assert api_only.expectedHarvest.connectors == ["api", "knowledge"]
    assert all(task["metadata"]["prefersApi"] for task in api_only.userTasks)
    assert not any(task["metadata"]["requiresBrowser"] for task in api_only.userTasks)

    web_only = infinite_company_arena.materialize_project(project, mode="web_only")
    assert web_only.mode == "web_only"
    assert {material["kind"] for material in web_only.materials} == {"website", "auth_note"}
    assert [task["metadata"]["icaTaskId"] for task in web_only.userTasks] == ["web_add_claim_note"]
    assert web_only.expectedHarvest.connectors == ["web"]
    assert web_only.userTasks[0]["metadata"]["requiresBrowser"] is True

    hybrid = infinite_company_arena.materialize_project(project, mode="hybrid")
    assert hybrid.mode == "hybrid"
    assert {material["kind"] for material in hybrid.materials} == {"website", "openapi", "document_url", "auth_note"}
    assert len(hybrid.userTasks) == 5

    discovery_input = infinite_company_arena.materialize_project(project, mode="hybrid", include_ground_truth_tasks=False)
    assert discovery_input.userTasks == []
    web_material = next(material for material in discovery_input.materials if material["kind"] == "website")
    assert "uiTaskHints" not in web_material["metadata"]


def test_legacy_demo_web_wrapper_loads_as_web_only_ica_project():
    project = infinite_company_arena.load_demo_project("autocinema_web")
    materialized = infinite_company_arena.materialize_project(project, mode="web_only")

    assert project.projectId == "autocinema_web"
    assert materialized.expectedHarvest.connectors == ["web"]
    assert [material["kind"] for material in materialized.materials] == ["website"]
    assert materialized.materials[0]["metadata"]["legacyDemoWeb"] is True
    assert materialized.userTasks[0]["metadata"]["requiresBrowser"] is True


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
        mode="hybrid",
        process=True,
    )

    assert result.projectId == "autoclaims"
    assert result.mode == "hybrid"
    assert result.passed is False
    assert result.score < 1.0
    assert result.phases["inventory"]["passed"] is True
    assert result.phases["solutionDiscovery"]["passed"] is True
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

    result = infinite_company_arena.evaluate_task_discovery(project=project, discovered_tasks=discovered, mode="hybrid")

    assert result.passed is True
    assert result.recall == 1.0
    assert result.matchedCount == 5
    assert result.missingTaskIds == []


def test_ica_solution_discovery_requires_agent_building_blocks():
    project = infinite_company_arena.load_demo_project("autoclaims")
    snapshot = {
        "connectors": [{"type": "api"}, {"type": "knowledge"}, {"type": "web"}],
        "tools": [
            {"name": "knowledge.company_docs.search"},
            {"name": "autoclaims.web.explore_workflows"},
            {"name": "autoclaims.api.searchcustomers"},
            {"name": "autoclaims.api.listclaims"},
            {"name": "autoclaims.api.getclaim"},
            {"name": "autoclaims.api.setclaimdecision"},
        ],
        "tasks": [],
        "benchmarks": [],
    }

    solutions = infinite_company_arena.propose_task_solutions(project=project, snapshot=snapshot, mode="hybrid")
    result = infinite_company_arena.evaluate_solution_discovery(project=project, solutions=solutions, snapshot=snapshot, mode="hybrid")

    assert result.passed is True
    assert result.solutionCount == 5
    assert {solution.agentProvider.runtimeKind for solution in result.solutions} <= {"model_agent", "claude_code", "codex"}
    assert all(solution.connectors and solution.tools and solution.trajectories and solution.skills for solution in result.solutions)

    broken = [solution.model_copy(update={"skills": []}) for solution in solutions]
    broken_result = infinite_company_arena.evaluate_solution_discovery(project=project, solutions=broken, snapshot=snapshot, mode="hybrid")
    assert broken_result.passed is False
    assert set(broken_result.incompleteTaskIds) == {
        "find_claim_status",
        "approve_low_risk_claim",
        "escalate_flagged_claim",
        "web_add_claim_note",
        "customer_summary",
    }


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
    assert result.connectors.missing == ["api", "knowledge"]
    assert "api_tools:required" in result.missing
    assert "knowledge:required" in result.missing
    assert "tasks:0/5" in result.missing
