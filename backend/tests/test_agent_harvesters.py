import json

import pytest

from app.services import agent_harvesters
from app.services.agent_harvesters import HarvestTask, TopMinerAgentHarvester, get_agent_harvester, get_official_agent_harvester, list_agent_harvesters


def test_default_agent_harvester_is_decoupled_autoppia_service(monkeypatch):
    monkeypatch.delenv("AUTOMATA_AGENT_HARVESTER", raising=False)
    assert get_agent_harvester().name == "autoppia_harvester"


def test_top_miner_is_legacy_alias_for_autoppia_harvester():
    assert get_agent_harvester("top_miner").name == "autoppia_harvester"


def test_public_harvester_list_exposes_only_backend_selected_official(monkeypatch):
    monkeypatch.delenv("AUTOMATA_AGENT_HARVESTER", raising=False)
    names = {item["name"] for item in list_agent_harvesters()}
    assert names == {"autoppia_harvester"}


def test_official_harvester_uses_backend_env_only(monkeypatch):
    monkeypatch.setenv("AUTOMATA_AGENT_HARVESTER", "claude_cli")
    assert get_official_agent_harvester().name == "claude_cli"


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

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

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
    monkeypatch.setattr(agent_harvesters, "agents_collection", _Collection())
    monkeypatch.setattr(agent_harvesters, "tools_collection", _Collection())
    monkeypatch.setattr(agent_harvesters, "connectors_collection", _Collection())
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

    assert result["status"] == "harvested", result
    assert calls[0][0] == "http://miner.local/find_trayectory"
    assert calls[0][1]["id"] == "task-1"
    assert calls[0][1]["web_project_id"] == "autocalendar"
    assert trajectories.docs[0]["trajectory"][0]["name"] == "navigate"
    assert trajectories.docs[0]["actions"][0]["action"] == "browser.navigate"


@pytest.mark.asyncio
async def test_autoppia_harvester_alias_uses_iwa_contract(monkeypatch):
    trajectories = _Collection()
    tasks = _Collection([{"taskId": "task-1", "status": "needs_harvest"}])
    monkeypatch.setattr(agent_harvesters, "trajectories_collection", trajectories)
    monkeypatch.setattr(agent_harvesters, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(agent_harvesters, "capabilities_collection", _Collection())
    monkeypatch.setattr(agent_harvesters, "agents_collection", _Collection())
    monkeypatch.setattr(agent_harvesters, "tools_collection", _Collection())
    monkeypatch.setattr(agent_harvesters, "connectors_collection", _Collection())
    monkeypatch.setenv("AUTOMATA_AUTOPPIA_HARVESTER_ENDPOINT", "http://autoppia-harvester.local")
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
        return _Response({"trajectory": [{"name": "navigate", "arguments": {"url": "http://localhost:8011/?seed=7"}}]})

    monkeypatch.setattr(agent_harvesters.urllib.request, "urlopen", fake_urlopen)

    harvester = get_agent_harvester("autoppia_harvester")
    result = await harvester.harvest_task(
        {"agentId": "agent-1", "companyId": "company-1", "websiteUrl": "http://fallback"},
        HarvestTask(
            {
                "taskId": "task-1",
                "agentId": "agent-1",
                "prompt": "Open it",
                "metadata": {"iwaProjectId": "autocalendar", "iwaStartUrl": "http://localhost:8011/?seed=7"},
            }
        ),
    )

    assert harvester.name == "autoppia_harvester"
    assert result["status"] == "harvested", result
    assert calls[0][0] == "http://autoppia-harvester.local/find_trayectory"
    assert calls[0][1]["id"] == "task-1"
    assert calls[0][1]["web_project_id"] == "autocalendar"


@pytest.mark.asyncio
async def test_harvester_discovered_tools_keep_discovery_evidence(monkeypatch):
    tools = _Collection()
    connectors = _Collection([
        {"connectorId": "conn-1", "companyId": "company-1", "name": "Reports", "type": "reports"}
    ])
    monkeypatch.setattr(agent_harvesters, "tools_collection", tools)
    monkeypatch.setattr(agent_harvesters, "connectors_collection", connectors)

    result = await agent_harvesters._upsert_discovered_tools(
        "company-1",
        "user@example.com",
        [
            {
                "name": "reports.latest_pdf",
                "description": "Get latest report PDF.",
                "discoveryEvidence": [{"kind": "http_probe", "url": "https://example.com/api/latest"}],
                "discoveryRelevance": {"reason": "matches_pdf_task", "score": 0.9},
                "discovererName": "claude_cli",
                "discovererVersion": "v1",
            }
        ],
    )

    assert result[0]["discoveryEvidence"][0]["kind"] == "http_probe"
    assert result[0]["discoveryRelevance"]["score"] == 0.9
    assert result[0]["discovererName"] == "claude_cli"
    assert tools.docs[0]["discoveryScope"] == "task_scoped"
