import pytest
from fastapi import HTTPException

from app.routes import evals as evals_route
from app.routes.evals import BenchmarkCreateRequest, BenchmarkRunCreateRequest, BenchmarkTaskCreateRequest


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    async def to_list(self, length):
        return list(self.docs)[:length]


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _FakeEvalsCollection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        benchmark_id = query["$or"][0]["benchmarkId"]
        agent_id = query["$or"][1]["agentId"]
        return _FakeCursor(
            [
                doc
                for doc in self.docs
                if doc.get("benchmarkId") == benchmark_id or doc.get("agentId") == agent_id
            ]
        )


class _FakeRunsCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return _Result(matched_count=1)
        return _Result(matched_count=0)


class _FakeBenchmarksCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _FakeBenchmarkTasksCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _FakeAgentsCollection:
    async def find_one(self, query, projection=None):
        if query.get("agentId") == "op-2":
            return {"name": "Second Agent"}
        return None


@pytest.mark.asyncio
async def test_create_benchmark_run_uses_selected_agent(monkeypatch):
    evals = _FakeEvalsCollection(
        [
            {
                "evalId": "eval-1",
                "email": "user@example.com",
                "benchmarkId": "bench-1",
                "benchmarkName": "Demo Benchmark",
                "agentId": "original-op",
                "agentName": "Original Agent",
                "agentTaskName": "Task 1",
                "prompt": "Do the first thing",
                "initialUrl": "https://example.com",
            }
        ]
    )
    runs = _FakeRunsCollection()
    monkeypatch.setattr(evals_route, "evals_collection", evals)
    monkeypatch.setattr(evals_route, "eval_runs_collection", runs)
    monkeypatch.setattr(evals_route, "agents_collection", _FakeAgentsCollection())

    result = await evals_route.create_benchmark_run(
        "bench-1",
        BenchmarkRunCreateRequest(agentId="op-2"),
    )

    assert result["success"] is True
    assert len(runs.docs) == 1
    assert runs.docs[0]["agentId"] == "op-2"
    assert runs.docs[0]["agentName"] == "Second Agent"
    assert result["runs"][0]["prompt"] == "Do the first thing"


@pytest.mark.asyncio
async def test_create_benchmark_and_task(monkeypatch):
    benchmarks = _FakeBenchmarksCollection()
    tasks = _FakeBenchmarkTasksCollection()
    monkeypatch.setattr(evals_route, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(evals_route, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(evals_route, "agents_collection", _FakeAgentsCollection())

    created = await evals_route.create_benchmark(
        BenchmarkCreateRequest(
            email="user@example.com",
            companyId="company-1",
            name="Knowledge QA",
            description="Ask questions over documents.",
            websiteUrl="https://example.com",
            agentId="op-2",
        )
    )
    benchmark_id = created["benchmark"]["benchmarkId"]

    task = await evals_route.create_benchmark_task(
        benchmark_id,
        BenchmarkTaskCreateRequest(
            email="user@example.com",
            companyId="company-1",
            name="Answer policy question",
            prompt="What is the travel approval policy?",
            successCriteria="Answer cites the policy.",
            initialUrl="https://example.com/start",
        ),
    )

    assert created["success"] is True
    assert created["benchmark"]["name"] == "Knowledge QA"
    assert created["benchmark"]["agentName"] == "Second Agent"
    assert tasks.docs[0]["benchmarkId"] == benchmark_id
    assert tasks.docs[0]["metadata"]["startUrl"] == "https://example.com/start"
    assert tasks.docs[0]["judgeType"] == "manual"
    assert task["task"]["agentTaskName"] == "Answer policy question"
    assert task["task"]["initialUrl"] == "https://example.com/start"


@pytest.mark.asyncio
async def test_connector_benchmark_catalog_endpoint():
    result = await evals_route.list_connector_benchmark_catalog()

    keys = {item["key"] for item in result["benchmarks"]}
    assert {"email", "bopa", "web"} <= keys


@pytest.mark.asyncio
async def test_seed_connector_benchmark_endpoint(monkeypatch):
    async def fake_seed_connector_benchmark(**kwargs):
        assert kwargs["benchmark_key"] == "email"
        assert kwargs["publish_tools"] is True
        return {
            "benchmark": {"benchmarkId": "bench-1"},
            "agent": {"agentId": "agent-1"},
            "tasks": [{"taskId": "task-1"}],
        }

    monkeypatch.setattr(evals_route, "seed_connector_benchmark", fake_seed_connector_benchmark)

    result = await evals_route.seed_connector_benchmark_endpoint(
        evals_route.ConnectorBenchmarkSeedRequest(
            email="user@example.com",
            companyId="co-1",
            connectorId="smtp-1",
            benchmarkKey="email",
        )
    )

    assert result["success"] is True
    assert result["benchmark"]["benchmarkId"] == "bench-1"


@pytest.mark.asyncio
async def test_connector_audit_matrix_endpoint(monkeypatch):
    async def fake_audit_connector_benchmark_matrix(**kwargs):
        assert kwargs["email"] == "user@example.com"
        assert kwargs["company_id"] == "co-1"
        assert kwargs["publish_tools"] is False
        return {"summary": {"pass": 1, "blocked": 1, "missing": 0, "fail": 0, "total": 2}, "rows": []}

    monkeypatch.setattr(evals_route, "audit_connector_benchmark_matrix", fake_audit_connector_benchmark_matrix)

    result = await evals_route.audit_connector_benchmark_matrix_endpoint(
        evals_route.ConnectorBenchmarkAuditRequest(
            email="user@example.com",
            companyId="co-1",
            publishTools=False,
        )
    )

    assert result["success"] is True
    assert result["connectorAudit"]["summary"]["blocked"] == 1


@pytest.mark.asyncio
async def test_connector_runtime_smoke_endpoint(monkeypatch):
    monkeypatch.setattr(evals_route, "benchmarks_collection", _FakeBenchmarksCollection([{"benchmarkId": "bench-1", "agentId": "agent-1"}]))

    async def fake_run_connector_runtime_smoke(**kwargs):
        assert kwargs["benchmark_id"] == "bench-1"
        assert kwargs["agent_id"] == "agent-1"
        assert kwargs["task_keys"] == ["search_recent_topic"]
        return {"benchmarkId": "bench-1", "agentId": "agent-1", "total": 1, "passed": 1, "failed": 0, "results": []}

    monkeypatch.setattr(evals_route, "run_connector_runtime_smoke", fake_run_connector_runtime_smoke)

    result = await evals_route.run_connector_benchmark_smoke(
        "bench-1",
        evals_route.ConnectorBenchmarkSmokeRequest(taskKeys=["search_recent_topic"]),
    )

    assert result["success"] is True
    assert result["runtimeSmoke"]["passed"] == 1


@pytest.mark.asyncio
async def test_connector_harvest_and_smoke_endpoint(monkeypatch):
    monkeypatch.setattr(evals_route, "benchmarks_collection", _FakeBenchmarksCollection([{"benchmarkId": "bench-1", "agentId": "agent-1"}]))

    async def fake_harvest_and_smoke_connector_benchmark(**kwargs):
        assert kwargs["benchmark_id"] == "bench-1"
        assert kwargs["agent_id"] == "agent-1"
        assert kwargs["task_keys"] == ["latest_pdf_artifact"]
        assert kwargs["approve_skills"] is True
        return {"success": True, "runtimeWithoutSkill": {"failed": 0}, "harvest": {"harvested": 1}, "runtimeWithSkill": {"failed": 0}}

    monkeypatch.setattr(evals_route, "harvest_and_smoke_connector_benchmark", fake_harvest_and_smoke_connector_benchmark)

    result = await evals_route.harvest_and_smoke_connector_benchmark_endpoint(
        "bench-1",
        evals_route.ConnectorBenchmarkSmokeRequest(taskKeys=["latest_pdf_artifact"], approveSkills=True),
    )

    assert result["success"] is True
    assert result["report"]["harvest"]["harvested"] == 1


@pytest.mark.asyncio
async def test_llm_judge_task_run_and_manual_override(monkeypatch):
    evals = _FakeEvalsCollection([])
    runs = _FakeRunsCollection()
    benchmarks = _FakeBenchmarksCollection([{"benchmarkId": "bench-1", "email": "user@example.com", "companyId": "company-1", "name": "QA"}])
    tasks = _FakeBenchmarkTasksCollection()
    monkeypatch.setattr(evals_route, "evals_collection", evals)
    monkeypatch.setattr(evals_route, "eval_runs_collection", runs)
    monkeypatch.setattr(evals_route, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(evals_route, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(evals_route, "agents_collection", _FakeAgentsCollection())

    created = await evals_route.create_benchmark_task(
        "bench-1",
        BenchmarkTaskCreateRequest(
            email="user@example.com",
            companyId="company-1",
            prompt="Answer from docs",
            judgeType="llm",
        ),
    )
    run = await evals_route.create_run(created["task"]["evalId"], BenchmarkRunCreateRequest())

    assert tasks.docs[0]["judgeType"] == "llm"
    assert runs.docs[0]["judgeType"] == "llm"
    assert runs.docs[0]["labelSource"] == "llm_pending"

    async def fake_judge_eval_run(**kwargs):
        return {"label": "pass", "confidence": 0.91, "needsHumanReview": False, "reasoning": "met", "judge": "fake"}

    monkeypatch.setattr(evals_route, "judge_eval_run", fake_judge_eval_run)
    judged = await evals_route.judge_run(
        created["task"]["evalId"],
        run["runId"],
        evals_route.JudgeRunRequest(apply=True),
    )
    assert judged["judgement"]["label"] == "pass"
    assert runs.docs[0]["label"] == "pass"
    assert runs.docs[0]["labelSource"] == "llm_judge"

    await evals_route.update_run(
        created["task"]["evalId"],
        run["runId"],
        evals_route.RunUpdateRequest(label="fail"),
    )
    assert runs.docs[0]["label"] == "fail"
    assert runs.docs[0]["labelSource"] == "manual_override"
    assert runs.docs[0]["manualOverride"] is True


@pytest.mark.asyncio
async def test_manual_judge_task_requires_human_review(monkeypatch):
    evals = _FakeEvalsCollection([])
    runs = _FakeRunsCollection()
    benchmarks = _FakeBenchmarksCollection([{"benchmarkId": "bench-1", "email": "user@example.com", "companyId": "company-1", "name": "QA"}])
    tasks = _FakeBenchmarkTasksCollection()
    monkeypatch.setattr(evals_route, "evals_collection", evals)
    monkeypatch.setattr(evals_route, "eval_runs_collection", runs)
    monkeypatch.setattr(evals_route, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(evals_route, "benchmark_tasks_collection", tasks)

    created = await evals_route.create_benchmark_task(
        "bench-1",
        BenchmarkTaskCreateRequest(
            email="user@example.com",
            companyId="company-1",
            prompt="Review manually",
            judgeType="manual",
        ),
    )
    run = await evals_route.create_run(created["task"]["evalId"], BenchmarkRunCreateRequest())

    with pytest.raises(HTTPException) as exc:
        await evals_route.judge_run(
            created["task"]["evalId"],
            run["runId"],
            evals_route.JudgeRunRequest(apply=True),
        )

    assert exc.value.status_code == 400
    assert runs.docs[0]["labelSource"] == "manual_review"
