import json

import pytest

from app.services import agent_harvesters
from app.services.agent_harvesters import HarvestTask, TopMinerAgentHarvester


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    async def to_list(self, length=100):
        return self.docs[:length]


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.updates = []

    def find(self, query, projection=None):
        return _Cursor([])

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(query)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)

    async def update_many(self, query, update):
        self.updates.append((query, update, False))


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_top_miner_harvester_posts_iwa_task_and_persists_canonical_trajectory(monkeypatch):
    trajectories = _Collection()
    tasks = _Collection([{"taskId": "task-1", "status": "needs_harvest"}])
    monkeypatch.setattr(agent_harvesters, "trajectories_collection", trajectories)
    monkeypatch.setattr(agent_harvesters, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(agent_harvesters, "capabilities_collection", _Collection())
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
        return _Response(
            {
                "trajectory": [
                    {"name": "navigate", "arguments": {"url": "http://localhost:8011/?seed=7"}},
                    {"name": "click", "arguments": {"selector": {"type": "attributeValueSelector", "attribute": "id", "value": "save"}}},
                ]
            }
        )

    monkeypatch.setattr(agent_harvesters.urllib.request, "urlopen", fake_urlopen)

    result = await TopMinerAgentHarvester().harvest_task(
        {"agentId": "agent-1", "companyId": "company-1", "harvesterEndpoint": "http://miner.local", "websiteUrl": "http://fallback"},
        HarvestTask(
            {
                "taskId": "task-1",
                "agentId": "agent-1",
                "prompt": "Save it",
                "metadata": {"iwaProjectId": "autocalendar", "iwaStartUrl": "http://localhost:8011/?seed=7"},
            }
        ),
    )

    assert result["status"] == "harvested"
    assert calls[0][0] == "http://miner.local/find_trayectory"
    assert calls[0][1]["id"] == "task-1"
    assert calls[0][1]["web_project_id"] == "autocalendar"
    assert trajectories.docs[0]["trajectory"][0]["name"] == "navigate"
    assert trajectories.docs[0]["actions"][0]["action"] == "browser.navigate"
