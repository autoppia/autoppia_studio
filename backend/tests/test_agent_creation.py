import pytest

from app.routes import agent_creation


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=500):
        return self.docs[:length]


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.updates = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if doc.get(key) != value:
                    matched = False
                    break
            if matched:
                docs.append(dict(doc))
        return _Cursor(docs)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                if "$push" in update:
                    for field, value in update["$push"].items():
                        doc.setdefault(field, []).append(value)
                return

    async def update_many(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                current = doc.get(key)
                if isinstance(value, dict) and "$in" in value:
                    if current not in value["$in"]:
                        matched = False
                        break
                elif current != value:
                    matched = False
                    break
            if matched:
                doc.update(update.get("$set", {}))


class _Harvester:
    name = "test_harvester"


@pytest.mark.asyncio
async def test_validate_agent_creation_warns_on_connector_auth(monkeypatch):
    monkeypatch.setattr(
        agent_creation,
        "agents_collection",
        _Collection([{"agentId": "op-1", "companyId": "co-1", "email": "user@example.com"}]),
    )
    monkeypatch.setattr(
        agent_creation,
        "connectors_collection",
        _Collection([{"companyId": "co-1", "name": "Holded", "type": "holded", "status": "needs_auth"}]),
    )
    jobs = _Collection()
    monkeypatch.setattr(agent_creation, "agent_creation_jobs_collection", jobs)

    job = await agent_creation.validate_agent_creation("op-1")

    assert job["status"] == "ready_for_harvest"
    assert job["currentStep"] == "run_harvester"
    validate_step = next(step for step in job["steps"] if step["key"] == "validate_connectors")
    harvest_step = next(step for step in job["steps"] if step["key"] == "run_harvester")
    assert validate_step["status"] == "ready"
    assert "Holded" in validate_step["message"]
    assert harvest_step["status"] == "ready"


@pytest.mark.asyncio
async def test_validate_agent_creation_marks_harvester_ready(monkeypatch):
    monkeypatch.setattr(
        agent_creation,
        "agents_collection",
        _Collection([{"agentId": "op-1", "companyId": "co-1", "email": "user@example.com"}]),
    )
    monkeypatch.setattr(
        agent_creation,
        "connectors_collection",
        _Collection([{"companyId": "co-1", "name": "BOPA", "type": "web", "status": "connected"}]),
    )
    jobs = _Collection()
    monkeypatch.setattr(agent_creation, "agent_creation_jobs_collection", jobs)

    job = await agent_creation.validate_agent_creation("op-1")

    assert job["status"] == "ready_for_harvest"
    validate_step = next(step for step in job["steps"] if step["key"] == "validate_connectors")
    harvest_step = next(step for step in job["steps"] if step["key"] == "run_harvester")
    assert validate_step["status"] == "done"
    assert harvest_step["status"] == "ready"


@pytest.mark.asyncio
async def test_start_harvester_enqueues_agent_harvest_job(monkeypatch):
    agent_id = "agent-1"
    jobs = []
    setup_steps = agent_creation._new_steps()
    monkeypatch.setattr(
        agent_creation,
        "agents_collection",
        _Collection([{"agentId": agent_id, "companyId": "co-1", "email": "user@example.com"}]),
    )
    monkeypatch.setattr(
        agent_creation,
        "agent_creation_jobs_collection",
        _Collection(
            [
                {
                    "jobId": "creation-1",
                    "agentId": agent_id,
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "status": "ready_for_harvest",
                    "currentStep": "run_harvester",
                    "steps": setup_steps,
                    "events": [],
                }
            ]
        ),
    )
    monkeypatch.setattr(agent_creation, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(agent_creation, "trajectories_collection", _Collection())
    monkeypatch.setattr(agent_creation, "get_official_agent_harvester", lambda: _Harvester())

    async def enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1"}

    monkeypatch.setattr(agent_creation, "enqueue_job", enqueue_job)

    result = await agent_creation.start_harvester(agent_id)

    assert result["status"] == "harvesting"
    assert jobs[0][0] == "agent_harvest"
    assert jobs[0][1]["agentId"] == agent_id
    assert jobs[0][1]["jobId"] == "creation-1"
    assert jobs[0][1]["harvesterName"] == "test_harvester"
    assert jobs[0][2]["dedupe_key"].startswith("agent_harvest:agent-1:")
