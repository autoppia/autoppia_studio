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
