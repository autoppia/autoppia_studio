import pytest

from app.services import agent_builder, company_harvester, custom_connector_executors, skills, task_harvester


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

    def _set(self, doc, key, value):
        current = doc
        parts = str(key).split(".")
        for part in parts[:-1]:
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

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

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return None

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
                for key, value in update.get("$set", {}).items():
                    self._set(doc, key, value)
                for key, value in update.get("$setOnInsert", {}).items():
                    if self._get(doc, key) is None:
                        self._set(doc, key, value)
                return None
        if upsert:
            doc = dict(query)
            for key, value in update.get("$setOnInsert", {}).items():
                self._set(doc, key, value)
            for key, value in update.get("$set", {}).items():
                self._set(doc, key, value)
            self.docs.append(doc)
        return None

    async def update_many(self, query, update, upsert=False):
        matched = False
        for doc in self.docs:
            if self._matches(doc, query):
                matched = True
                for key, value in update.get("$set", {}).items():
                    self._set(doc, key, value)
        if upsert and not matched:
            await self.update_one(query, update, upsert=True)
        return None


class _FakeHarvester:
    name = "backend_smoke_harvester"

    async def harvest_task(self, agent_config, task):
        expected_tools = task.data.get("metadata", {}).get("expectedTools") or ["knowledge.company_docs.search"]
        tool_name = expected_tools[0]
        trajectory_id = f"traj-{task.task_id}"
        trajectory = {
            "trajectoryId": trajectory_id,
            "taskId": task.task_id,
            "agentId": task.data.get("agentId") or agent_config.get("agentId", ""),
            "companyId": task.data.get("companyId") or agent_config.get("companyId", ""),
            "email": task.data.get("email") or agent_config.get("email", ""),
            "benchmarkId": task.data.get("benchmarkId", ""),
            "taskName": task.task_name,
            "prompt": task.prompt,
            "successCriteria": task.success_criteria,
            "status": "harvested",
            "trajectory": [{"name": tool_name, "arguments": {"instruction": task.prompt}}],
            "actions": [{"name": tool_name, "arguments": {"instruction": task.prompt}}],
            "toolIds": [],
            "connectorIds": [],
            "runtimeRequirements": agent_config.get("taskHarvesterStrategy", {}).get("runtimeRequirements", []),
            "metadata": task.data.get("metadata", {}),
            "harvester": {"adapter": self.name, "status": "success", "confidence": 0.95, "summary": "Smoke trajectory."},
        }
        await task_harvester.trajectories_collection.update_one({"trajectoryId": trajectory_id}, {"$set": trajectory}, upsert=True)
        await task_harvester.benchmark_tasks_collection.update_one(
            {"taskId": task.task_id},
            {"$set": {"status": "harvested", "trajectoryId": trajectory_id}},
        )
        return {"trajectoryId": trajectory_id, "taskId": task.task_id, "status": "harvested", "summary": "Smoke trajectory."}


class _PassingJudge:
    name = "backend_smoke_rules"

    async def judge(self, context):
        return {"label": "pass", "confidence": 0.95, "needsHumanReview": False, "reasoning": "smoke pass", "judge": self.name}


@pytest.mark.asyncio
async def test_backend_company_harvest_end_to_end_builds_usable_agents(monkeypatch):
    intakes = _Collection()
    runs = _Collection()
    connectors = _Collection()
    tools = _Collection()
    knowledge_docs = _Collection()
    benchmarks = _Collection()
    benchmark_tasks = _Collection()
    entities = _Collection()
    trajectories = _Collection()
    capabilities = _Collection()
    agents = _Collection()

    for module in (company_harvester,):
        monkeypatch.setattr(module, "company_intakes_collection", intakes)
        monkeypatch.setattr(module, "company_harvest_runs_collection", runs)
        monkeypatch.setattr(module, "connectors_collection", connectors)
        monkeypatch.setattr(module, "tools_collection", tools)
        monkeypatch.setattr(module, "knowledge_documents_collection", knowledge_docs)
        monkeypatch.setattr(module, "benchmarks_collection", benchmarks)
        monkeypatch.setattr(module, "benchmark_tasks_collection", benchmark_tasks)
        monkeypatch.setattr(module, "entities_collection", entities)
    monkeypatch.setattr(task_harvester, "benchmark_tasks_collection", benchmark_tasks)
    monkeypatch.setattr(task_harvester, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(task_harvester, "connectors_collection", connectors)
    monkeypatch.setattr(task_harvester, "tools_collection", tools)
    monkeypatch.setattr(task_harvester, "trajectories_collection", trajectories)
    monkeypatch.setattr(task_harvester, "agents_collection", agents)
    monkeypatch.setattr(task_harvester, "get_agent_harvester", lambda _name=None: _FakeHarvester())
    monkeypatch.setattr(task_harvester, "get_trajectory_judge", lambda _name=None: _PassingJudge())
    monkeypatch.setattr(skills, "capabilities_collection", capabilities)
    monkeypatch.setattr(skills, "trajectories_collection", trajectories)
    monkeypatch.setattr(skills, "agents_collection", agents)
    monkeypatch.setattr(agent_builder, "capabilities_collection", capabilities)
    monkeypatch.setattr(agent_builder, "tools_collection", tools)
    monkeypatch.setattr(agent_builder, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(agent_builder, "entities_collection", entities)
    monkeypatch.setattr(agent_builder, "agents_collection", agents)
    custom_connector_executors.clear_custom_connector_executors()
    custom_connector_executors.register_custom_connector_executor("smoke.payroll.lookup_employee", lambda _context: {"success": True})

    intake = await company_harvester.create_company_intake(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        materials=[
            {
                "kind": "knowledge_note",
                "name": "Operations context",
                "content": "Celeris support teams look up payroll and claim context for employees.",
                "metadata": {
                    "systems": [
                        {
                            "name": "Payroll ERP",
                            "surface": "custom",
                            "description": "Payroll system with a smoke executor attached.",
                            "tools": [
                                {
                                    "name": "payroll.lookup_employee",
                                    "description": "Look up employee payroll status.",
                                    "runtimeExecutor": "smoke.payroll.lookup_employee",
                                    "implementationStatus": "ready",
                                    "inputSchema": {"type": "object", "properties": {"employeeEmail": {"type": "string"}}, "required": ["employeeEmail"]},
                                    "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
                                    "sideEffects": "reads",
                                }
                            ],
                            "tasks": [
                                {
                                    "name": "Check payroll status",
                                    "prompt": "Look up an employee payroll status and summarize the HR follow-up.",
                                    "successCriteria": "Payroll status is found and summarized.",
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
    discovered = await company_harvester.process_company_harvest_run(run["runId"])
    benchmark_id = discovered["normalSummary"]["benchmarkId"]

    task_harvest = await task_harvester.harvest_benchmark_tasks(benchmark_id, harvester_name="smoke")
    promotion = await task_harvester.judge_and_promote_benchmark_trajectories(benchmark_id, judge_name="smoke")
    agent_build = await agent_builder.build_company_agents(
        email="owner@example.com",
        company_id="company-1",
        company_name="Celeris",
        benchmark_id=benchmark_id,
        runtime_kinds=["model_agent", "codex", "claude_code"],
    )
    recorded = await company_harvester.record_company_harvest_results(
        run["runId"],
        task_harvest=task_harvest,
        promotion=promotion,
        agent_build=agent_build,
    )
    normal = await company_harvester.company_harvest_status(run["runId"], mode="normal", email="owner@example.com")

    assert discovered["status"] == "solving_tasks"
    assert task_harvest["count"] == len(benchmark_tasks.docs)
    assert task_harvest["harvested"] == len(benchmark_tasks.docs)
    assert promotion["promoted"] == len(benchmark_tasks.docs)
    assert len(capabilities.docs) == len(benchmark_tasks.docs)
    assert recorded["status"] == "ready"
    assert normal["status"] == "ready"
    assert normal["nextAction"]["kind"] == "use_agents"
    assert normal["summary"]["taskImplementationGaps"] == 0
    assert normal["summary"]["skillsReady"] == len(benchmark_tasks.docs)
    assert normal["summary"]["agentsReady"] == 3
    assert normal["delivery"]["surfaces"] == {"chat": True, "api": True, "widget": True}
    assert {agent["runtimeKind"] for agent in agents.docs} == {"model_agent", "codex", "claude_code"}
    assert all(agent["deliverySurfaces"]["api"]["endpoint"] == f"/runtime/agents/{agent['agentId']}/step" for agent in agents.docs)
    assert all(agent["skills"] for agent in agents.docs)
    custom_connector_executors.clear_custom_connector_executors()
