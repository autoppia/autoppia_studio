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


def _matches_query(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches_query(doc, item) for item in value):
                return False
            continue
        current = doc.get(key)
        if isinstance(value, dict) and "$in" in value:
            if current not in value["$in"]:
                return False
            continue
        if current != value:
            return False
    return True


class _SimpleCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query, projection=None):
        return _FakeCursor([doc for doc in self.docs if _matches_query(doc, query)])


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
            businessIntent="Answer a policy question with citations",
            allowedSystems=["knowledge", "email"],
            expectedArtifacts=["answer_summary"],
            riskClass="read",
            initialState={"documentSet": "travel-policy"},
        ),
    )

    assert created["success"] is True
    assert created["benchmark"]["name"] == "Knowledge QA"
    assert created["benchmark"]["agentName"] == "Second Agent"
    assert tasks.docs[0]["benchmarkId"] == benchmark_id
    assert tasks.docs[0]["metadata"]["startUrl"] == "https://example.com/start"
    assert tasks.docs[0]["metadata"]["businessIntent"] == "Answer a policy question with citations"
    assert tasks.docs[0]["metadata"]["allowedSystems"] == ["knowledge", "email"]
    assert tasks.docs[0]["metadata"]["expectedArtifacts"] == ["answer_summary"]
    assert tasks.docs[0]["metadata"]["riskClass"] == "read"
    assert tasks.docs[0]["metadata"]["initialState"] == {"documentSet": "travel-policy"}
    assert tasks.docs[0]["judgeType"] == "manual"
    assert task["task"]["agentTaskName"] == "Answer policy question"
    assert task["task"]["initialUrl"] == "https://example.com/start"
    assert task["task"]["taskContract"]["businessIntent"] == "Answer a policy question with citations"
    assert task["task"]["taskContract"]["allowedSystems"] == ["knowledge", "email"]
    assert task["task"]["taskContract"]["expectedArtifacts"] == ["answer_summary"]
    assert task["task"]["taskContract"]["riskClass"] == "read"
    assert task["task"]["taskContract"]["completeness"]["state"] == "complete"
    assert task["task"]["taskContract"]["completeness"]["passedChecks"] == 6
    assert task["task"]["evaluationHarness"]["strategy"] == "layered"
    assert task["task"]["evaluationHarness"]["deterministicFirst"] is True
    assert task["task"]["evaluationHarness"]["statefulReplay"] is True
    assert task["task"]["evaluationHarness"]["llmAsComplement"] is False
    assert task["task"]["evaluationHarness"]["preferredOrder"] == ["deterministic", "stateful", "manual"]


@pytest.mark.asyncio
async def test_list_benchmarks_includes_coverage_summary(monkeypatch):
    monkeypatch.setattr(
        evals_route,
        "benchmarks_collection",
        _SimpleCollection([{"benchmarkId": "bench-1", "email": "user@example.com", "companyId": "company-1", "name": "Claims QA"}]),
    )
    monkeypatch.setattr(
        evals_route,
        "benchmark_tasks_collection",
        _SimpleCollection(
            [
                {
                    "taskId": "task-1",
                    "benchmarkId": "bench-1",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "prompt": "Answer claim status",
                    "successCriteria": "Draft includes claim status.",
                    "metadata": {
                        "allowedSystems": ["email", "erp"],
                        "expectedArtifacts": ["draft_email"],
                        "riskClass": "draft",
                        "businessIntent": "Respond to claim status request",
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        evals_route,
        "capabilities_collection",
        _SimpleCollection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "benchmarkId": "bench-1",
                    "status": "published",
                    "connectorIds": ["email-1", "erp-1"],
                    "inputEntities": ["Claim", "Customer"],
                    "outputEntity": "DraftEmail",
                    "expectedArtifacts": ["claim_summary"],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        evals_route,
        "eval_runs_collection",
        _SimpleCollection([{"runId": "run-1", "evalId": "task-1", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"}]),
    )

    result = await evals_route.list_benchmarks(email="user@example.com", companyId="company-1")
    coverage = result["benchmarks"][0]["coverage"]

    assert coverage["taskCount"] == 1
    assert coverage["taskContractCoverage"]["complete"] == 0
    assert coverage["taskContractCoverage"]["total"] == 1
    assert coverage["taskContractCoverage"]["averageScore"] == 0.833
    assert coverage["systems"] == ["email", "erp"]
    assert coverage["expectedArtifacts"] == ["draft_email", "claim_summary"]
    assert coverage["riskClasses"] == ["draft"]
    assert coverage["connectorIds"] == ["email-1", "erp-1"]
    assert coverage["entityNames"] == ["Claim", "Customer", "DraftEmail"]
    assert coverage["skillCoverage"]["total"] == 1
    assert coverage["skillCoverage"]["published"] == 1
    assert coverage["runCoverage"]["pass"] == 1
    assert coverage["runCoverage"]["latestRunId"] == "run-1"
    assert coverage["promotionGate"]["state"] == "blocked"
    assert coverage["promotionGate"]["canPromote"] is False
    assert coverage["promotionGate"]["blockers"] == ["incomplete_task_contracts"]
    portfolio = result["coveragePortfolio"]
    assert portfolio["benchmarks"] == 1
    assert portfolio["tasks"] == 1
    assert portfolio["taskContracts"]["coverageRatio"] == 0.0
    assert portfolio["connectors"] == ["email-1", "erp-1"]
    assert portfolio["systems"] == ["email", "erp"]
    assert portfolio["entities"] == ["Claim", "Customer", "DraftEmail"]
    assert portfolio["artifacts"] == ["draft_email", "claim_summary"]
    assert portfolio["skills"]["total"] == 1
    assert portfolio["skills"]["published"] == 1
    assert portfolio["regressions"]["passRatio"] == 1.0
    assert portfolio["regressions"]["latest"][0]["runId"] == "run-1"
    assert portfolio["promotionGate"]["state"] == "blocked"
    assert portfolio["promotionGate"]["blockers"] == ["incomplete_task_contracts"]
    matrix = portfolio["coverageMatrix"]
    assert matrix["connectors"][0]["id"] == "email-1"
    assert matrix["connectors"][0]["kind"] == "connector"
    assert matrix["connectors"][0]["state"] == "passing"
    assert matrix["connectors"][0]["regressions"]["pass"] == 1
    assert matrix["entities"][0]["id"] == "Claim"
    assert matrix["entities"][0]["covered"] is True
    assert matrix["skills"][0]["id"] == "skill-1"
    assert matrix["skills"][0]["state"] == "published"
    assert matrix["skills"][0]["benchmarkCount"] == 1


@pytest.mark.asyncio
async def test_list_benchmarks_exposes_vertical_demo_readiness(monkeypatch):
    vertical_demo = {
        "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
        "runtimePath": "hybrid_api_first",
        "coverage": [
            {"key": "email_read", "label": "Email read", "evidence": "imap.search_emails"},
            {"key": "erp_lookup", "label": "ERP lookup", "evidence": "erp.search_claims"},
            {"key": "document_grounding", "label": "Document grounding", "evidence": "knowledge.search"},
            {"key": "draft_artifact", "label": "Draft artifact", "evidence": "draft_email artifact"},
            {"key": "approval_boundary", "label": "Approval boundary", "evidence": "send_requires_human_approval"},
            {"key": "benchmark", "label": "Benchmark", "evidence": "connector-insurance_claims tasks"},
            {"key": "trajectory", "label": "Trajectory", "evidence": "runtime trace/tool calls"},
            {"key": "skill_promotion", "label": "Skill promotion", "evidence": "hardened skill package"},
            {"key": "runtime_replay", "label": "Runtime replay", "evidence": "router matched approved trajectory"},
        ],
    }
    monkeypatch.setattr(
        evals_route,
        "benchmarks_collection",
        _SimpleCollection(
            [
                {
                    "benchmarkId": "bench-insurance",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "name": "Insurance Claims",
                    "metadata": {"vertical": "insurance", "verticalDemo": vertical_demo},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        evals_route,
        "benchmark_tasks_collection",
        _SimpleCollection(
            [
                {
                    "taskId": "task-draft",
                    "benchmarkId": "bench-insurance",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "prompt": "Draft claim status response",
                    "successCriteria": "Draft exists and is not sent.",
                    "metadata": {
                        "expectedTools": ["imap.search_emails", "erp.search_claims", "knowledge.search", "smtp.draft_email"],
                        "allowedSystems": ["email", "insurance_erp", "knowledge"],
                        "expectedArtifacts": ["draft_email", "claim_summary"],
                        "riskClass": "draft",
                        "businessIntent": "Respond to claim status",
                        "initialState": {"approvalBoundary": "send_requires_human_approval"},
                    },
                },
                {
                    "taskId": "task-send",
                    "benchmarkId": "bench-insurance",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "prompt": "Send only after approval",
                    "successCriteria": "Human approval requested before send.",
                    "metadata": {
                        "expectedTools": ["api.human_approval"],
                        "allowedSystems": ["email", "approvals"],
                        "expectedArtifacts": ["approval_request"],
                        "riskClass": "send",
                        "businessIntent": "Protect claim response send",
                        "initialState": {"approvalBoundary": "send"},
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(
        evals_route,
        "capabilities_collection",
        _SimpleCollection(
            [
                {
                    "capabilityId": "skill-claim",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "benchmarkId": "bench-insurance",
                    "status": "published",
                    "trajectoryIds": ["traj-claim"],
                    "skillPackage": {"format": "autoppia.agent_skill"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        evals_route,
        "eval_runs_collection",
        _SimpleCollection([{"runId": "run-claim", "evalId": "task-draft", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"}]),
    )

    result = await evals_route.list_benchmarks(email="user@example.com", companyId="company-1")
    readiness = result["benchmarks"][0]["verticalDemoReadiness"]

    assert readiness["state"] == "ready"
    assert readiness["readyCount"] == 9
    assert readiness["total"] == 9
    assert readiness["runtimePath"] == "hybrid_api_first"
    assert readiness["evidence"]["trajectoryIds"] == ["traj-claim"]
    assert readiness["evidence"]["passingRuns"] == 1
    assert {item["key"] for item in readiness["coverage"] if item["ready"]} == {
        "email_read",
        "erp_lookup",
        "document_grounding",
        "draft_artifact",
        "approval_boundary",
        "benchmark",
        "trajectory",
        "skill_promotion",
        "runtime_replay",
    }


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
