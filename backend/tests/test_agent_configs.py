import pytest

from app.routes import agent_configs
from app.routes.agent_configs import AgentConfigCreateRequest, AgentRuntimeSettingsRequest, AgentTask
from app.request_scope import RequestScope


class _UpdateResult:
    def __init__(self, upserted_id=None):
        self.upserted_id = upserted_id


class _AgentsCollection:
    def __init__(self):
        self.doc = {
            "agentId": "agent-1",
            "email": "user@example.com",
            "name": "Demo Agent",
            "websiteUrl": "https://example.com",
            "runtimeCapabilities": {"browser": True, "apiCalls": True, "humanApprovalForWrites": True},
            "runtimeSpec": {
                "browserEnabled": True,
                "browserMode": "visible",
                "maxCreditsPerRun": 5,
                "tools": {"browser": True, "connectors": True, "skills": True, "knowledge": False},
            },
        }

    async def find_one(self, query, projection=None):
        if query.get("agentId") == self.doc["agentId"]:
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        if query.get("agentId") == self.doc["agentId"]:
            self.doc.update(update.get("$set", {}))


class _Collection:
    def __init__(self):
        self.docs = []
        self.updates = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _UpdateResult("inserted")

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return _UpdateResult()
        if upsert:
            doc = {**query, **update.get("$setOnInsert", {}), **update.get("$set", {})}
            self.docs.append(doc)
            return _UpdateResult(doc.get("taskId") or doc.get("evalId") or "upserted")
        return _UpdateResult()

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


class _NoTrajectoryCollection:
    async def insert_one(self, doc):
        raise AssertionError("pending agent tasks must not be inserted into trajectories")


@pytest.mark.asyncio
async def test_update_agent_runtime_settings_persists_runtime_spec(monkeypatch):
    agents = _AgentsCollection()
    monkeypatch.setattr(agent_configs, "agents_collection", agents)

    result = await agent_configs.update_agent_runtime_settings(
        "agent-1",
        AgentRuntimeSettingsRequest(browserEnabled=False, browserMode="headless", maxCreditsPerRun=2.25),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert result["success"] is True
    assert result["agent"]["runtimeCapabilities"]["browser"] is False
    assert result["agent"]["runtimeSpec"]["browserEnabled"] is False
    assert result["agent"]["runtimeSpec"]["browserMode"] == "headless"
    assert result["agent"]["runtimeSpec"]["maxCreditsPerRun"] == 2.25
    assert result["agent"]["runtimeSpec"]["tools"]["browser"] is False
    assert result["agent"]["runtimeSpec"]["allowedDomains"] == ["example.com"]
    assert result["agent"]["runtimeSpec"]["browserRestrictedByDomain"] is True
    assert result["agent"]["runtimeSpec"]["browserDefaultUse"] == "exception"
    assert result["agent"]["runtimeSpec"]["approvalRequiredFor"] == ["write", "send"]
    assert "api_runtime" in result["agent"]["runtimeSpec"]["runtimeClasses"]
    assert "browser_runtime" not in result["agent"]["runtimeSpec"]["runtimeClasses"]


@pytest.mark.asyncio
async def test_create_agent_seeds_benchmark_tasks_instead_of_pending_trajectories(monkeypatch):
    agents = _Collection()
    webs = _Collection()
    evals = _Collection()
    tasks = _Collection()
    monkeypatch.setattr(agent_configs, "agents_collection", agents)
    monkeypatch.setattr(agent_configs, "agent_webs_collection", webs)
    monkeypatch.setattr(agent_configs, "evals_collection", evals)
    monkeypatch.setattr(agent_configs, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(agent_configs, "trajectories_collection", _NoTrajectoryCollection())

    async def ensure_job(doc):
        return {"jobId": "job-1", "agentId": doc["agentId"]}

    monkeypatch.setattr(agent_configs, "ensure_agent_creation_job", ensure_job)

    result = await agent_configs.create_agent(
        AgentConfigCreateRequest(
            email="user@example.com",
            companyId="company-1",
            name="Claims Agent",
            websiteUrl="https://erp.example.com",
            tasks=[
                AgentTask(
                    name="Summarize claim",
                    prompt="Find the latest claim status and draft a response.",
                    successCriteria="A draft artifact cites the ERP claim status.",
                )
            ],
        ),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert result["trajectoryIds"] == []
    assert len(result["taskIds"]) == 1
    assert agents.docs[0]["trainingStatus"] == "needs_harvest"
    assert len(tasks.docs) == 1
    task_doc = tasks.docs[0]
    assert task_doc["status"] == "needs_harvest"
    assert task_doc["trajectoryId"] == ""
    assert task_doc["businessIntent"] == "Find the latest claim status and draft a response."
    assert task_doc["riskClass"] == "low"
    assert task_doc["metadata"]["taskContract"]["businessIntent"] == "Find the latest claim status and draft a response."
    assert "https://erp.example.com" in task_doc["metadata"]["taskContract"]["allowedSystems"]
    assert task_doc["metadata"]["taskContract"]["expectedArtifacts"] == ["trajectory_trace"]
