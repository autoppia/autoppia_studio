import pytest

from app.services import custom_connector_executors, task_harvester


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

    def _matches(self, doc, query):
        for key, value in query.items():
            current = doc.get(key)
            if isinstance(value, dict) and "$in" in value:
                if current not in value["$in"]:
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


class _FakeHarvester:
    name = "fake_task_harvester"

    def __init__(self):
        self.tasks = []

    async def harvest_task(self, agent_config, task):
        self.tasks.append((agent_config, task.data))
        return {"trajectoryId": f"traj-{task.task_id}", "taskId": task.task_id, "status": "harvested"}


class _FakeJudge:
    name = "fake_judge"

    async def judge(self, context):
        return {"label": "pass", "confidence": 0.91, "needsHumanReview": False, "reasoning": "ok", "judge": self.name}


def test_task_harvest_has_implementation_gaps_detects_batch_and_single_results():
    assert task_harvester.task_harvest_has_implementation_gaps({"implementationRequiredCount": 1}) is True
    assert task_harvester.task_harvest_has_implementation_gaps({"status": "implementation_required"}) is True
    assert task_harvester.task_harvest_has_implementation_gaps({"implementationGaps": [{"toolName": "payroll.lookup_employee"}]}) is True
    assert task_harvester.task_harvest_has_implementation_gaps({"results": [{"status": "implementation_required"}]}) is True
    assert task_harvester.task_harvest_has_implementation_gaps({"results": [{"strategy": {"implementationGaps": [{"toolName": "x"}]}}]}) is True
    assert task_harvester.task_harvest_has_implementation_gaps({"harvestedCount": 1, "results": [{"status": "harvested"}]}) is False


@pytest.mark.asyncio
async def test_task_harvester_consumes_benchmark_tasks_not_trajectory_queue(monkeypatch):
    tasks = _Collection(
        [
            {"taskId": "task-1", "benchmarkId": "bench-1", "companyId": "company-1", "email": "owner@example.com", "prompt": "Use API", "status": "needs_harvest"},
            {"taskId": "task-2", "benchmarkId": "bench-1", "companyId": "company-1", "email": "owner@example.com", "prompt": "Use browser", "status": "draft"},
            {"taskId": "task-3", "benchmarkId": "bench-1", "companyId": "company-1", "email": "owner@example.com", "prompt": "Done", "status": "harvested"},
        ]
    )
    fake = _FakeHarvester()
    monkeypatch.setattr(task_harvester, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(task_harvester, "benchmarks_collection", _Collection([{"benchmarkId": "bench-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "connectors_collection", _Collection([{"connectorId": "conn-api", "companyId": "company-1", "type": "api"}]))
    monkeypatch.setattr(task_harvester, "tools_collection", _Collection([{"toolId": "tool-1", "companyId": "company-1", "name": "crm.search_claims"}]))
    monkeypatch.setattr(task_harvester, "get_agent_harvester", lambda _name=None: fake)

    result = await task_harvester.harvest_benchmark_tasks("bench-1", harvester_name="fake")

    assert result["count"] == 2
    assert result["harvested"] == 2
    assert [task["taskId"] for _, task in fake.tasks] == ["task-1", "task-2"]
    assert fake.tasks[0][0]["runtimeType"] == "task_harvester"
    assert fake.tasks[0][0]["taskHarvesterStrategy"]["strategy"] == "model_agent"


@pytest.mark.asyncio
async def test_task_strategy_prefers_api_connector_tool_knowledge_then_browser(monkeypatch):
    custom_connector_executors.clear_custom_connector_executors()
    custom_connector_executors.register_custom_connector_executor("custom.erp.lookup_invoice", lambda _context: {"success": True})
    monkeypatch.setattr(task_harvester, "connectors_collection", _Collection([
        {"connectorId": "knowledge-1", "companyId": "company-1", "type": "knowledge"},
        {"connectorId": "web-1", "companyId": "company-1", "type": "web"},
    ]))
    monkeypatch.setattr(task_harvester, "tools_collection", _Collection([
        {"toolId": "tool-1", "companyId": "company-1", "name": "crm.search_claims", "executionType": "api_call"},
        {"toolId": "tool-2", "companyId": "company-1", "name": "knowledge.company_docs.search", "executionType": "knowledge_search"},
        {"toolId": "tool-3", "companyId": "company-1", "name": "crm.explore_workflows", "executionType": "browser_automation"},
        {"toolId": "tool-4", "companyId": "company-1", "name": "payroll.lookup_employee", "executionType": "connector_tool"},
        {
            "toolId": "tool-5",
            "companyId": "company-1",
            "name": "erp.lookup_invoice",
            "executionType": "connector_tool",
            "connectorType": "custom",
            "runtimeExecutor": "custom.erp.lookup_invoice",
            "metadata": {"customConnector": True},
        },
    ]))

    api = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"expectedTools": ["crm.search_claims"]}}
    )
    knowledge = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"usesKnowledge": True}}
    )
    browser = await task_harvester.plan_task_strategy(
        {"companyId": "company-2", "metadata": {"requiresBrowser": True}, "allowedSystems": ["https://crm.example.com"]}
    )
    browser_tool = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"expectedTools": ["crm.explore_workflows"]}}
    )
    knowledge_tool = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"expectedTools": ["knowledge.company_docs.search"]}}
    )
    custom_connector_tool = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"expectedTools": ["payroll.lookup_employee"], "customConnector": True}}
    )
    implemented_connector_tool = await task_harvester.plan_task_strategy(
        {"companyId": "company-1", "metadata": {"expectedTools": ["erp.lookup_invoice"], "customConnector": True}}
    )

    assert api["strategy"] == "api_tool"
    assert "connector_runtime" in api["runtimeRequirements"]
    assert api["executionReadiness"] == "ready"
    assert api["canExecuteEndToEnd"] is True
    assert api["matchedTools"][0]["executionReady"] is True
    assert custom_connector_tool["strategy"] == "connector_tool"
    assert custom_connector_tool["runtimeRequirements"] == ["connector_runtime"]
    assert custom_connector_tool["executionReadiness"] == "implementation_required"
    assert custom_connector_tool["canExecuteEndToEnd"] is False
    assert custom_connector_tool["matchedTools"][0]["executionReady"] is False
    assert custom_connector_tool["implementationGaps"] == [
        {
            "kind": "connector_tool_executor_missing",
            "toolId": "tool-4",
            "toolName": "payroll.lookup_employee",
            "connectorId": "",
            "nextAction": "Implement or attach a connector executor before this task can be executed end to end.",
        }
    ]
    assert implemented_connector_tool["strategy"] == "connector_tool"
    assert implemented_connector_tool["executionReadiness"] == "ready"
    assert implemented_connector_tool["canExecuteEndToEnd"] is True
    assert custom_connector_tool["preferenceOrder"] == ["api_tool", "connector_tool", "knowledge", "browser", "model_agent"]
    assert knowledge["strategy"] == "knowledge"
    assert "vectorstore" in knowledge["runtimeRequirements"]
    assert browser["strategy"] == "browser"
    assert browser["runtimeRequirements"] == ["browser"]
    assert browser_tool["strategy"] == "browser"
    assert knowledge_tool["strategy"] == "knowledge"
    custom_connector_executors.clear_custom_connector_executors()


@pytest.mark.asyncio
async def test_harvest_task_persists_connector_implementation_gap_strategy(monkeypatch):
    tasks = _Collection(
        [
            {
                "taskId": "task-custom",
                "benchmarkId": "bench-1",
                "companyId": "company-1",
                "email": "owner@example.com",
                "prompt": "Lookup payroll",
                "status": "needs_harvest",
                "metadata": {"expectedTools": ["payroll.lookup_employee"], "customConnector": True},
            }
        ]
    )
    fake = _FakeHarvester()
    monkeypatch.setattr(task_harvester, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(task_harvester, "benchmarks_collection", _Collection([{"benchmarkId": "bench-1", "companyId": "company-1"}]))
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "connectors_collection", _Collection([{"connectorId": "payroll", "companyId": "company-1", "type": "custom"}]))
    monkeypatch.setattr(task_harvester, "tools_collection", _Collection([
        {
            "toolId": "tool-payroll",
            "companyId": "company-1",
            "connectorId": "payroll",
            "name": "payroll.lookup_employee",
            "executionType": "connector_tool",
        }
    ]))
    monkeypatch.setattr(task_harvester, "get_agent_harvester", lambda _name=None: fake)

    result = await task_harvester.harvest_task("task-custom", harvester_name="fake")
    persisted_strategy = tasks.updates[0][1]["$set"]["harvesterStrategy"]

    assert result["status"] == "implementation_required"
    assert result["trajectoryId"] == ""
    assert result["strategy"]["strategy"] == "connector_tool"
    assert result["strategy"]["executionReadiness"] == "implementation_required"
    assert result["strategy"]["implementationGaps"][0]["connectorId"] == "payroll"
    assert result["implementationGaps"][0]["toolName"] == "payroll.lookup_employee"
    assert persisted_strategy["executionReadiness"] == "implementation_required"
    assert persisted_strategy["canExecuteEndToEnd"] is False
    assert fake.tasks == []
    assert tasks.updates[1][1]["$set"]["status"] == "implementation_required"
    assert tasks.updates[1][1]["$set"]["trajectoryId"] == ""


@pytest.mark.asyncio
async def test_harvest_benchmark_tasks_counts_implementation_required_without_trajectory(monkeypatch):
    tasks = _Collection(
        [
            {
                "taskId": "task-custom",
                "benchmarkId": "bench-1",
                "companyId": "company-1",
                "email": "owner@example.com",
                "prompt": "Lookup payroll",
                "status": "needs_harvest",
                "metadata": {"expectedTools": ["payroll.lookup_employee"], "customConnector": True},
            },
            {
                "taskId": "task-ready",
                "benchmarkId": "bench-1",
                "companyId": "company-1",
                "email": "owner@example.com",
                "prompt": "Use model",
                "status": "needs_harvest",
            },
        ]
    )
    fake = _FakeHarvester()
    monkeypatch.setattr(task_harvester, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(task_harvester, "benchmarks_collection", _Collection([{"benchmarkId": "bench-1", "companyId": "company-1"}]))
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "connectors_collection", _Collection([{"connectorId": "payroll", "companyId": "company-1", "type": "custom"}]))
    monkeypatch.setattr(task_harvester, "tools_collection", _Collection([
        {
            "toolId": "tool-payroll",
            "companyId": "company-1",
            "connectorId": "payroll",
            "name": "payroll.lookup_employee",
            "executionType": "connector_tool",
            "metadata": {"customConnector": True},
        }
    ]))
    monkeypatch.setattr(task_harvester, "get_agent_harvester", lambda _name=None: fake)

    result = await task_harvester.harvest_benchmark_tasks("bench-1", harvester_name="fake")

    assert result["count"] == 2
    assert result["harvestedCount"] == 1
    assert result["failedCount"] == 0
    assert result["implementationRequiredCount"] == 1
    assert result["harvested"] == 1
    assert result["results"][0]["status"] == "implementation_required"
    assert result["results"][0]["trajectoryId"] == ""
    assert [task["taskId"] for _, task in fake.tasks] == ["task-ready"]


@pytest.mark.asyncio
async def test_harvest_benchmark_tasks_retries_implementation_required_after_executor_registration(monkeypatch):
    custom_connector_executors.clear_custom_connector_executors()
    custom_connector_executors.register_custom_connector_executor("custom.payroll.lookup_employee", lambda _payload: {"success": True})
    tasks = _Collection(
        [
            {
                "taskId": "task-custom",
                "benchmarkId": "bench-1",
                "companyId": "company-1",
                "email": "owner@example.com",
                "prompt": "Lookup payroll",
                "status": "implementation_required",
                "trajectoryId": "",
                "implementationGaps": [{"toolName": "payroll.lookup_employee"}],
                "metadata": {"expectedTools": ["payroll.lookup_employee"], "customConnector": True},
            }
        ]
    )
    fake = _FakeHarvester()
    monkeypatch.setattr(task_harvester, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(task_harvester, "benchmarks_collection", _Collection([{"benchmarkId": "bench-1", "companyId": "company-1"}]))
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "connectors_collection", _Collection([{"connectorId": "payroll", "companyId": "company-1", "type": "custom"}]))
    monkeypatch.setattr(task_harvester, "tools_collection", _Collection([
        {
            "toolId": "tool-payroll",
            "companyId": "company-1",
            "connectorId": "payroll",
            "name": "payroll.lookup_employee",
            "executionType": "connector_tool",
            "runtimeExecutor": "custom.payroll.lookup_employee",
            "metadata": {"customConnector": True},
        }
    ]))
    monkeypatch.setattr(task_harvester, "get_agent_harvester", lambda _name=None: fake)

    try:
        result = await task_harvester.harvest_benchmark_tasks("bench-1", harvester_name="fake")
    finally:
        custom_connector_executors.clear_custom_connector_executors()

    assert result["count"] == 1
    assert result["harvestedCount"] == 1
    assert result["implementationRequiredCount"] == 0
    assert result["results"][0]["status"] == "harvested"
    assert result["results"][0]["trajectoryId"] == "traj-task-custom"
    assert fake.tasks[0][0]["taskHarvesterStrategy"]["executionReadiness"] == "ready"
    assert tasks.updates[1][1]["$set"]["implementationGaps"] == []
    assert tasks.updates[1][1]["$set"]["trajectoryId"] == ""


@pytest.mark.asyncio
async def test_judge_and_promote_harvested_trajectories(monkeypatch):
    trajectories = _Collection([
        {
            "trajectoryId": "traj-1",
            "taskId": "task-1",
            "benchmarkId": "bench-1",
            "companyId": "company-1",
            "email": "owner@example.com",
            "taskName": "Search claims",
            "prompt": "Search claims",
            "status": "harvested",
            "trajectory": [{"name": "crm.search_claims", "arguments": {"query": "Alice"}}],
            "harvester": {"confidence": 0.95},
        }
    ])
    promoted = []

    async def approve(trajectory, *, judge=None):
        promoted.append((trajectory["trajectoryId"], judge))
        return "capability-1"

    monkeypatch.setattr(task_harvester, "trajectories_collection", trajectories)
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "get_trajectory_judge", lambda _name=None: _FakeJudge())
    monkeypatch.setattr(task_harvester, "approve_trajectory_as_skill", approve)

    result = await task_harvester.judge_and_promote_benchmark_trajectories("bench-1", judge_name="fake")

    assert result["count"] == 1
    assert result["promoted"] == 1
    assert result["pendingReview"] == 0
    assert result["results"][0]["capabilityId"] == "capability-1"
    assert promoted[0][0] == "traj-1"
    assert trajectories.updates[0][1]["$set"]["needsHumanReview"] is False
    assert trajectories.updates[0][1]["$set"]["status"] == "approved"
    assert trajectories.updates[0][1]["$set"]["capabilityId"] == "capability-1"


@pytest.mark.asyncio
async def test_judge_and_promote_does_not_approve_trajectory_if_skill_promotion_fails(monkeypatch):
    trajectories = _Collection([
        {
            "trajectoryId": "traj-1",
            "taskId": "task-1",
            "benchmarkId": "bench-1",
            "companyId": "company-1",
            "status": "harvested",
            "trajectory": [{"name": "crm.search_claims", "arguments": {"query": "Alice"}}],
        }
    ])

    async def approve(*_args, **_kwargs):
        raise RuntimeError("skill write failed")

    monkeypatch.setattr(task_harvester, "trajectories_collection", trajectories)
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "get_trajectory_judge", lambda _name=None: _FakeJudge())
    monkeypatch.setattr(task_harvester, "approve_trajectory_as_skill", approve)

    with pytest.raises(RuntimeError, match="skill write failed"):
        await task_harvester.judge_and_promote_benchmark_trajectories("bench-1", judge_name="fake")

    assert trajectories.updates == []


@pytest.mark.asyncio
async def test_judge_and_promote_marks_failed_trajectory_for_review(monkeypatch):
    trajectories = _Collection([
        {
            "trajectoryId": "traj-1",
            "taskId": "task-1",
            "benchmarkId": "bench-1",
            "companyId": "company-1",
            "status": "harvested",
            "trajectory": [{"name": "crm.search_claims", "arguments": {"query": "Alice"}}],
        }
    ])

    class _FailingJudge:
        name = "failing_judge"

        async def judge(self, context):
            return {"label": "fail", "confidence": 0.95, "needsHumanReview": True, "reasoning": "missing evidence"}

    async def approve(*_args, **_kwargs):
        raise AssertionError("Failing trajectories should not be promoted")

    monkeypatch.setattr(task_harvester, "trajectories_collection", trajectories)
    monkeypatch.setattr(task_harvester, "agents_collection", _Collection())
    monkeypatch.setattr(task_harvester, "get_trajectory_judge", lambda _name=None: _FailingJudge())
    monkeypatch.setattr(task_harvester, "approve_trajectory_as_skill", approve)

    result = await task_harvester.judge_and_promote_benchmark_trajectories("bench-1", judge_name="failing")

    assert result["promoted"] == 0
    assert result["pendingReview"] == 1
    assert result["results"][0]["promoted"] is False
    assert trajectories.updates[0][1]["$set"]["needsHumanReview"] is True
    assert trajectories.updates[0][1]["$set"]["status"] == "review_required"
