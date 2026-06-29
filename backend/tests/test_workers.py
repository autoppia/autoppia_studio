import pytest

from app.services import workers


class _Locks:
    def __init__(self):
        self.calls = []

    async def find_one_and_update(self, query, update, **kwargs):
        self.calls.append((query, update, kwargs))
        return {"lockId": update["$set"]["lockId"], "ownerId": update["$set"]["ownerId"]}


@pytest.mark.asyncio
async def test_worker_lease_uses_mongo_lock(monkeypatch):
    locks = _Locks()
    monkeypatch.setattr(workers, "worker_locks_collection", locks)

    acquired = await workers.acquire_worker_lease("scheduled_work", ttl_seconds=30)

    assert acquired is True
    query, update, kwargs = locks.calls[0]
    assert query["lockId"] == "scheduled_work"
    assert update["$set"]["ownerId"] == workers.WORKER_OWNER_ID
    assert kwargs["upsert"] is True


@pytest.mark.asyncio
async def test_execute_agent_harvest_job(monkeypatch):
    calls = []

    async def run_harvester_background(**kwargs):
        calls.append(kwargs)

    from app.routes import agent_creation

    monkeypatch.setattr(agent_creation, "_run_harvester_background", run_harvester_background)

    result = await workers.execute_job(
        {
            "type": "agent_harvest",
            "payload": {
                "agentId": "agent-1",
                "jobId": "creation-1",
                "harvesterRunId": "run-1",
                "harvesterName": "test_harvester",
            },
        }
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "agent_id": "agent-1",
            "job_id": "creation-1",
            "harvester_run_id": "run-1",
            "harvester_name": "test_harvester",
        }
    ]


@pytest.mark.asyncio
async def test_execute_task_harvest_job(monkeypatch):
    from app.services import task_harvester

    calls = []

    async def harvest_benchmark_tasks(benchmark_id, **kwargs):
        calls.append((benchmark_id, kwargs))
        return {"benchmarkId": benchmark_id, "count": 2}

    monkeypatch.setattr(task_harvester, "harvest_benchmark_tasks", harvest_benchmark_tasks)

    result = await workers.execute_job(
        {
            "type": "task_harvest",
            "payload": {
                "benchmarkId": "bench-1",
                "taskIds": ["task-1"],
                "harvesterName": "fake",
                "limit": 3,
            },
        }
    )

    assert result == {"benchmarkId": "bench-1", "count": 2}
    assert calls == [("bench-1", {"harvester_name": "fake", "task_ids": ["task-1"], "limit": 3})]


@pytest.mark.asyncio
async def test_execute_task_harvest_job_blocks_promotion_when_benchmark_needs_connector_implementation(monkeypatch):
    from app.services import agent_builder, task_harvester

    async def harvest_benchmark_tasks(benchmark_id, **kwargs):
        return {
            "benchmarkId": benchmark_id,
            "count": 1,
            "implementationRequiredCount": 1,
            "results": [{"taskId": "task-1", "status": "implementation_required"}],
        }

    async def judge_and_promote_benchmark_trajectories(*_args, **_kwargs):
        raise AssertionError("Promotion should be blocked")

    async def build_company_agents(**_kwargs):
        raise AssertionError("Agent build should be blocked")

    monkeypatch.setattr(task_harvester, "harvest_benchmark_tasks", harvest_benchmark_tasks)
    monkeypatch.setattr(task_harvester, "judge_and_promote_benchmark_trajectories", judge_and_promote_benchmark_trajectories)
    monkeypatch.setattr(agent_builder, "build_company_agents", build_company_agents)

    result = await workers.execute_job(
        {
            "type": "task_harvest",
            "payload": {
                "benchmarkId": "bench-1",
                "promoteSkills": True,
                "buildAgents": True,
                "companyId": "company-1",
            },
        }
    )

    assert result == {
        "harvest": {
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
async def test_execute_task_harvest_job_blocks_promotion_when_single_task_needs_connector_implementation(monkeypatch):
    from app.services import task_harvester

    async def harvest_task(task_id, **kwargs):
        return {
            "taskId": task_id,
            "benchmarkId": "bench-1",
            "status": "implementation_required",
            "implementationGaps": [{"toolName": "payroll.lookup_employee"}],
        }

    async def judge_and_promote_benchmark_trajectories(*_args, **_kwargs):
        raise AssertionError("Promotion should be blocked")

    monkeypatch.setattr(task_harvester, "harvest_task", harvest_task)
    monkeypatch.setattr(task_harvester, "judge_and_promote_benchmark_trajectories", judge_and_promote_benchmark_trajectories)

    result = await workers.execute_job(
        {
            "type": "task_harvest",
            "payload": {
                "taskId": "task-1",
                "benchmarkId": "bench-1",
                "promoteSkills": True,
            },
        }
    )

    assert result["harvest"]["status"] == "implementation_required"
    assert result["blockedActions"] == [
        {
            "kind": "promote_or_build_agents",
            "reason": "task_harvest_requires_connector_implementation",
            "benchmarkId": "bench-1",
        }
    ]


@pytest.mark.asyncio
async def test_execute_agent_build_job(monkeypatch):
    from app.services import agent_builder

    calls = []

    async def build_company_agents(**kwargs):
        calls.append(kwargs)
        return {"agentCount": 3}

    monkeypatch.setattr(agent_builder, "build_company_agents", build_company_agents)

    result = await workers.execute_job(
        {
            "type": "agent_build",
            "payload": {
                "email": "owner@example.com",
                "companyId": "company-1",
                "companyName": "Celeris",
                "benchmarkId": "bench-1",
                "runtimeKinds": ["model_agent", "codex"],
                "runtimeProfiles": {"model_agent": {"provider": "anthropic", "model": "claude-sonnet"}},
            },
        }
    )

    assert result == {"agentCount": 3}
    assert calls == [
        {
            "email": "owner@example.com",
            "company_id": "company-1",
            "company_name": "Celeris",
            "benchmark_id": "bench-1",
            "runtime_kinds": ["model_agent", "codex"],
            "runtime_profiles": {"model_agent": {"provider": "anthropic", "model": "claude-sonnet"}},
        }
    ]


@pytest.mark.asyncio
async def test_execute_company_harvest_job_records_full_pipeline(monkeypatch):
    from app.services import agent_builder, company_harvester, task_harvester

    async def process_company_harvest_run(run_id):
        return {
            "runId": run_id,
            "email": "owner@example.com",
            "companyId": "company-1",
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {"knowledgeDocumentIds": ["doc-1"]},
            "nextAction": {"benchmarkId": "bench-1"},
        }

    async def harvest_benchmark_tasks(benchmark_id, **kwargs):
        return {"benchmarkId": benchmark_id, "harvestedCount": 2}

    async def judge_and_promote_benchmark_trajectories(benchmark_id, **kwargs):
        return {"benchmarkId": benchmark_id, "promotedCount": 1}

    async def build_company_agents(**kwargs):
        return {"companyId": kwargs["company_id"], "agentCount": 2, "agentIds": ["agent-1", "agent-2"], "skillCount": 1, "toolCount": 3}

    async def record_company_harvest_results(run_id, **kwargs):
        return {"runId": run_id, "status": "ready", "recorded": kwargs}

    async def enqueue_job(job_type, payload, **kwargs):
        return {"type": job_type, "payload": payload, **kwargs}

    monkeypatch.setattr(company_harvester, "process_company_harvest_run", process_company_harvest_run)
    monkeypatch.setattr(company_harvester, "record_company_harvest_results", record_company_harvest_results)
    monkeypatch.setattr(task_harvester, "harvest_benchmark_tasks", harvest_benchmark_tasks)
    monkeypatch.setattr(task_harvester, "judge_and_promote_benchmark_trajectories", judge_and_promote_benchmark_trajectories)
    monkeypatch.setattr(agent_builder, "build_company_agents", build_company_agents)
    monkeypatch.setattr(workers, "enqueue_job", enqueue_job)

    result = await workers.execute_job(
        {
            "type": "company_harvest",
            "payload": {
                "runId": "run-1",
                "autoSolveTasks": True,
                "autoPromoteSkills": True,
                "buildAgents": True,
                "companyName": "Celeris",
                "runtimeKinds": ["model_agent", "codex"],
            },
        }
    )

    assert result["taskHarvest"] == {"benchmarkId": "bench-1", "harvestedCount": 2}
    assert result["promotion"] == {"benchmarkId": "bench-1", "promotedCount": 1}
    assert result["agentBuild"]["agentIds"] == ["agent-1", "agent-2"]
    assert result["knowledgeIndexJobs"] == [
        {
            "type": "knowledge_index",
            "payload": {"documentId": "doc-1"},
            "dedupe_key": "knowledge_index:doc-1",
            "max_attempts": 3,
        }
    ]
    assert result["companyHarvest"]["status"] == "ready"
    assert result["companyHarvest"]["recorded"]["knowledge_index_jobs"][0]["payload"]["documentId"] == "doc-1"
    assert result["companyHarvest"]["recorded"]["task_harvest"]["harvestedCount"] == 2
    assert result["companyHarvest"]["recorded"]["promotion"]["promotedCount"] == 1
    assert result["companyHarvest"]["recorded"]["agent_build"]["agentCount"] == 2


@pytest.mark.asyncio
async def test_execute_company_harvest_job_indexes_discovered_knowledge_documents(monkeypatch):
    from app.services import company_harvester

    async def process_company_harvest_run(run_id):
        return {
            "runId": run_id,
            "email": "owner@example.com",
            "companyId": "company-1",
            "normalSummary": {
                "benchmarkId": "bench-1",
                "knowledgeDocumentIds": ["doc-normal"],
            },
            "devSummary": {
                "knowledgeDocumentIds": ["doc-1", "doc-2"],
            },
            "nextAction": {"benchmarkId": "bench-1"},
        }

    async def record_company_harvest_results(run_id, **kwargs):
        return {"runId": run_id, "recorded": kwargs}

    async def enqueue_job(job_type, payload, **kwargs):
        return {"type": job_type, "payload": payload, **kwargs}

    monkeypatch.setattr(company_harvester, "process_company_harvest_run", process_company_harvest_run)
    monkeypatch.setattr(company_harvester, "record_company_harvest_results", record_company_harvest_results)
    monkeypatch.setattr(workers, "enqueue_job", enqueue_job)

    result = await workers.execute_job(
        {
            "type": "company_harvest",
            "payload": {
                "runId": "run-1",
                "autoSolveTasks": False,
                "buildAgents": False,
            },
        }
    )

    assert result["knowledgeIndexJobs"] == [
        {
            "type": "knowledge_index",
            "payload": {"documentId": "doc-1"},
            "dedupe_key": "knowledge_index:doc-1",
            "max_attempts": 3,
        },
        {
            "type": "knowledge_index",
            "payload": {"documentId": "doc-2"},
            "dedupe_key": "knowledge_index:doc-2",
            "max_attempts": 3,
        },
    ]
    assert result["companyHarvest"]["recorded"]["knowledge_index_jobs"] == result["knowledgeIndexJobs"]


@pytest.mark.asyncio
async def test_execute_company_harvest_job_does_not_auto_solve_when_connectors_need_implementation(monkeypatch):
    from app.services import company_harvester, task_harvester

    async def process_company_harvest_run(run_id):
        return {
            "runId": run_id,
            "email": "owner@example.com",
            "companyId": "company-1",
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {},
            "status": "solving_tasks",
            "nextAction": {
                "kind": "implement_connectors",
                "label": "Implement missing connector executors",
                "benchmarkId": "bench-1",
                "toolNames": ["payroll.lookup_employee"],
            },
        }

    async def harvest_benchmark_tasks(*_args, **_kwargs):
        raise AssertionError("TaskHarvester should not run while connector executors are missing")

    async def record_company_harvest_results(run_id, **kwargs):
        return {"runId": run_id, "status": "solving_tasks", "recorded": kwargs}

    monkeypatch.setattr(company_harvester, "process_company_harvest_run", process_company_harvest_run)
    monkeypatch.setattr(company_harvester, "record_company_harvest_results", record_company_harvest_results)
    monkeypatch.setattr(task_harvester, "harvest_benchmark_tasks", harvest_benchmark_tasks)

    result = await workers.execute_job(
        {
            "type": "company_harvest",
            "payload": {
                "runId": "run-1",
                "autoIndexKnowledge": False,
                "autoSolveTasks": True,
                "autoPromoteSkills": True,
                "buildAgents": False,
            },
        }
    )

    assert "taskHarvest" not in result
    assert "promotion" not in result
    assert result["blockedActions"] == [
        {
            "kind": "auto_solve_tasks",
            "reason": "company_harvest_next_action_requires_connector_implementation",
            "nextAction": {
                "kind": "implement_connectors",
                "label": "Implement missing connector executors",
                "benchmarkId": "bench-1",
                "toolNames": ["payroll.lookup_employee"],
            },
        }
    ]
    assert result["companyHarvest"]["recorded"]["task_harvest"] is None
    assert result["companyHarvest"]["recorded"]["promotion"] is None


@pytest.mark.asyncio
async def test_execute_company_harvest_job_does_not_promote_or_build_when_task_harvest_finds_implementation_gaps(monkeypatch):
    from app.services import agent_builder, company_harvester, task_harvester

    async def process_company_harvest_run(run_id):
        return {
            "runId": run_id,
            "email": "owner@example.com",
            "companyId": "company-1",
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {},
            "status": "solving_tasks",
            "nextAction": {"kind": "run_task_harvester", "benchmarkId": "bench-1"},
        }

    async def harvest_benchmark_tasks(benchmark_id, **kwargs):
        return {
            "benchmarkId": benchmark_id,
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
                        "implementationGaps": [
                            {"toolName": "payroll.lookup_employee", "connectorId": "payroll"}
                        ]
                    },
                }
            ],
        }

    async def judge_and_promote_benchmark_trajectories(*_args, **_kwargs):
        raise AssertionError("Promotion should wait until connector implementation gaps are resolved")

    async def build_company_agents(**_kwargs):
        raise AssertionError("Agent build should wait until connector implementation gaps are resolved")

    async def record_company_harvest_results(run_id, **kwargs):
        return {"runId": run_id, "status": "solving_tasks", "recorded": kwargs}

    monkeypatch.setattr(company_harvester, "process_company_harvest_run", process_company_harvest_run)
    monkeypatch.setattr(company_harvester, "record_company_harvest_results", record_company_harvest_results)
    monkeypatch.setattr(task_harvester, "harvest_benchmark_tasks", harvest_benchmark_tasks)
    monkeypatch.setattr(task_harvester, "judge_and_promote_benchmark_trajectories", judge_and_promote_benchmark_trajectories)
    monkeypatch.setattr(agent_builder, "build_company_agents", build_company_agents)

    result = await workers.execute_job(
        {
            "type": "company_harvest",
            "payload": {
                "runId": "run-1",
                "autoIndexKnowledge": False,
                "autoSolveTasks": True,
                "autoPromoteSkills": True,
                "buildAgents": True,
            },
        }
    )

    assert result["taskHarvest"]["implementationRequiredCount"] == 1
    assert "promotion" not in result
    assert "agentBuild" not in result
    assert result["blockedActions"] == [
        {
            "kind": "auto_promote_or_build_agents",
            "reason": "task_harvest_requires_connector_implementation",
            "benchmarkId": "bench-1",
        }
    ]
    assert result["companyHarvest"]["recorded"]["promotion"] is None
    assert result["companyHarvest"]["recorded"]["agent_build"] is None


@pytest.mark.asyncio
async def test_execute_company_harvest_job_builds_agents_without_auto_promote(monkeypatch):
    from app.services import agent_builder, company_harvester

    async def process_company_harvest_run(run_id):
        return {
            "runId": run_id,
            "email": "owner@example.com",
            "companyId": "company-1",
            "normalSummary": {"benchmarkId": "bench-1"},
            "devSummary": {},
            "nextAction": {"benchmarkId": "bench-1"},
        }

    async def build_company_agents(**kwargs):
        return {"companyId": kwargs["company_id"], "agentCount": 3, "agentIds": ["agent-1", "agent-2", "agent-3"], "toolCount": 2, "skillCount": 0}

    async def record_company_harvest_results(run_id, **kwargs):
        return {"runId": run_id, "status": "ready", "recorded": kwargs}

    monkeypatch.setattr(company_harvester, "process_company_harvest_run", process_company_harvest_run)
    monkeypatch.setattr(company_harvester, "record_company_harvest_results", record_company_harvest_results)
    monkeypatch.setattr(agent_builder, "build_company_agents", build_company_agents)

    result = await workers.execute_job(
        {
            "type": "company_harvest",
            "payload": {
                "runId": "run-1",
                "autoIndexKnowledge": False,
                "autoSolveTasks": False,
                "autoPromoteSkills": False,
                "buildAgents": True,
                "companyName": "Celeris",
                "runtimeKinds": ["model_agent", "codex", "claude_code"],
            },
        }
    )

    assert "taskHarvest" not in result
    assert "promotion" not in result
    assert result["agentBuild"]["agentCount"] == 3
    assert result["companyHarvest"]["recorded"]["task_harvest"] is None
    assert result["companyHarvest"]["recorded"]["promotion"] is None
    assert result["companyHarvest"]["recorded"]["agent_build"]["toolCount"] == 2
