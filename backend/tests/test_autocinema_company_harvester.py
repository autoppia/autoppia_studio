import pytest

from app.services import company_harvester, task_harvester


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
                doc.update(update.get("$setOnInsert", {}))
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


AUTOCINEMA_UI_HINTS = [
    {
        "name": "Search film from UI",
        "prompt": "Search for the movie 'The Lord of the Rings: The Fellowship of the Ring' in Autocinema.",
        "successCriteria": "The matching film is found from the web search flow.",
        "riskClass": "read",
    },
    {
        "name": "Add film from UI",
        "prompt": "Add a new Action film in Autocinema with rating greater than or equal to 3.3.",
        "successCriteria": "The movie catalog contains the newly created Action film.",
        "riskClass": "write",
    },
    {
        "name": "Login from UI",
        "prompt": "Login to Autocinema with username user<web_agent_id> and password password123.",
        "successCriteria": "The UI shows an authenticated user session.",
        "riskClass": "read",
    },
]


AUTOCINEMA_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "Autocinema API", "version": "0.1.0"},
    "paths": {
        "/films": {
            "get": {
                "operationId": "searchFilms",
                "summary": "Search films by title, genre, year or rating.",
                "parameters": [{"name": "query", "in": "query", "schema": {"type": "string"}}],
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "title": "FilmSearchResult"}}}}},
            },
            "post": {
                "operationId": "addFilm",
                "summary": "Create a new film in the catalog.",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object", "properties": {"title": {"type": "string"}, "genre": {"type": "string"}, "rating": {"type": "number"}}}}},
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"type": "object", "title": "Film"}}}}},
            },
        },
        "/films/{filmId}/comments": {
            "post": {
                "operationId": "addComment",
                "summary": "Add a comment to a film.",
                "parameters": [{"name": "filmId", "in": "path", "schema": {"type": "string"}, "required": True}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object", "properties": {"comment": {"type": "string"}}}}},
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"type": "object", "title": "Comment"}}}}},
            }
        },
    },
}


def _website_material():
    return {
        "kind": "website",
        "name": "Autocinema",
        "url": "http://localhost:8000",
        "metadata": {
            "projectKey": "web_1_autocinema",
            "demoPath": "/home/usuario1/daryxx/autoppia/operator/autoppia_webs_demo/web_1_autocinema",
            "uiTaskHints": AUTOCINEMA_UI_HINTS,
        },
    }


def _api_material():
    return {
        "kind": "openapi",
        "name": "Autocinema API",
        "url": "http://localhost:8000/openapi.json",
        "metadata": {"openapi": AUTOCINEMA_OPENAPI},
    }


async def _run_company_harvest(materials, collections):
    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="autocinema-company",
        company_name="Autocinema",
        materials=materials,
        user_tasks=[],
        mode="dev",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email="owner@example.com")
    processed = await company_harvester.process_company_harvest_run(run["runId"])
    assert processed["status"] == "solving_tasks"
    return collections


@pytest.mark.asyncio
async def test_autocinema_ui_only_onboarding_discovers_browser_tasks(collections):
    data = await _run_company_harvest([_website_material()], collections)

    assert {connector["type"] for connector in data["connectors"].docs} == {"web"}
    assert {tool["name"] for tool in data["tools"].docs} == {"autocinema.explore_workflows"}

    by_name = {task["name"]: task for task in data["tasks"].docs}
    assert {"Search film from UI", "Add film from UI", "Login from UI", "Explore Autocinema"} <= set(by_name)

    search_strategy = await task_harvester.plan_task_strategy(by_name["Search film from UI"])
    add_strategy = await task_harvester.plan_task_strategy(by_name["Add film from UI"])

    assert search_strategy["strategy"] == "browser"
    assert add_strategy["strategy"] == "browser"
    assert by_name["Search film from UI"]["metadata"]["source"] == "company_harvester_ui_hint"
    assert by_name["Search film from UI"]["metadata"]["expectedTools"] == ["autocinema.explore_workflows"]
    assert by_name["Add film from UI"]["riskClass"] == "write"


@pytest.mark.asyncio
async def test_autocinema_api_only_onboarding_discovers_api_tasks(collections):
    data = await _run_company_harvest([_api_material()], collections)

    assert {connector["type"] for connector in data["connectors"].docs} == {"api"}
    assert {tool["name"] for tool in data["tools"].docs} == {
        "autocinema.api.searchfilms",
        "autocinema.api.addfilm",
        "autocinema.api.addcomment",
    }

    by_name = {task["name"]: task for task in data["tasks"].docs}
    assert "Validate autocinema.api.searchfilms" in by_name
    assert "Validate autocinema.api.addfilm" in by_name
    assert "Inspect Autocinema API" in by_name

    search_strategy = await task_harvester.plan_task_strategy(by_name["Validate autocinema.api.searchfilms"])
    add_strategy = await task_harvester.plan_task_strategy(by_name["Validate autocinema.api.addfilm"])

    assert search_strategy["strategy"] == "api_tool"
    assert add_strategy["strategy"] == "api_tool"
    assert by_name["Validate autocinema.api.searchfilms"]["riskClass"] == "read"
    assert by_name["Validate autocinema.api.addfilm"]["riskClass"] == "write"


@pytest.mark.asyncio
async def test_autocinema_hybrid_onboarding_keeps_ui_and_api_tasks_separate(collections):
    data = await _run_company_harvest([_website_material(), _api_material()], collections)

    assert {connector["type"] for connector in data["connectors"].docs} == {"web", "api"}
    by_name = {task["name"]: task for task in data["tasks"].docs}
    ui_strategy = await task_harvester.plan_task_strategy(by_name["Add film from UI"])
    api_strategy = await task_harvester.plan_task_strategy(by_name["Validate autocinema.api.addfilm"])

    assert ui_strategy["strategy"] == "browser"
    assert api_strategy["strategy"] == "api_tool"
    assert by_name["Add film from UI"]["metadata"]["requiresBrowser"] is True
    assert by_name["Validate autocinema.api.addfilm"]["metadata"]["prefersApi"] is True
    assert data["benchmarks"].docs[0]["taskCount"] == len(data["tasks"].docs)
