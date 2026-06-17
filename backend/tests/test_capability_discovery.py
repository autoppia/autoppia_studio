import pytest

from app.services import capability_discovery


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                if "$addToSet" in update:
                    for key, value in update["$addToSet"].items():
                        doc.setdefault(key, [])
                        if value not in doc[key]:
                            doc[key].append(value)
                if "$push" in update:
                    for key, value in update["$push"].items():
                        if isinstance(value, dict) and "$each" in value:
                            doc.setdefault(key, []).extend(value["$each"])
                        else:
                            doc.setdefault(key, []).append(value)
                return _Result()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            self.docs.append(new_doc)
        return _Result(matched_count=0)


def _matches(doc, query):
    for key, value in query.items():
        if doc.get(key) != value:
            return False
    return True


def _bopa_connector():
    return {
        "connectorId": "conn-bopa",
        "companyId": "co-1",
        "email": "user@example.com",
        "name": "BOPA",
        "type": "bopa",
        "status": "connected",
        "provider": "official",
        "config": {"baseUrl": "https://www.bopa.ad/"},
    }


def _custom_web_connector():
    return {
        "connectorId": "conn-web",
        "companyId": "co-1",
        "email": "user@example.com",
        "name": "Example",
        "type": "web",
        "status": "connected",
        "provider": "custom",
        "surface": "webapp",
        "config": {"baseUrl": "https://example.com", "startUrl": "https://example.com"},
    }


@pytest.mark.asyncio
async def test_task_scoped_discovery_publishes_tools_without_skills(monkeypatch):
    tools = _Collection()
    runs = _Collection()
    trajectories = _Collection()
    monkeypatch.setattr(capability_discovery, "tools_collection", tools)
    monkeypatch.setattr(capability_discovery, "harvester_runs_collection", runs)
    monkeypatch.setattr(capability_discovery, "trajectories_collection", trajectories)
    monkeypatch.setattr(capability_discovery, "approve_trajectory_as_skill", lambda *args, **kwargs: "should-not-run")

    result = await capability_discovery.run_capability_discovery(
        {
            "agentId": "agent-1",
            "companyId": "co-1",
            "email": "user@example.com",
            "capabilityDiscovery": {"mode": "task_scoped"},
            "tasks": [{"name": "Download latest PDF", "prompt": "Descargar el PDF del ultimo boletin BOPA"}],
        },
        [_bopa_connector()],
    )

    assert result["discovererName"] == "default_toolkit_discoverer"
    assert result["discovererVersion"] == "v1"
    assert result["mode"] == "task_scoped"
    assert {tool["name"] for tool in result["tools"]} == {"bopa.latest_bulletin_pdf"}
    assert result["tools"][0]["discoveryScope"] == "task_scoped"
    assert result["tools"][0]["discoveryRelevance"]["reason"] == "matches_latest_pdf_task"
    assert result["tools"][0]["discoveryEvidence"][0]["kind"] == "connector_toolkit"
    assert result["targetTasks"][0]["name"] == "Download latest PDF"
    assert result["skills"] == []
    assert trajectories.docs == []


@pytest.mark.asyncio
async def test_broad_discovery_promotes_safe_atomic_tools(monkeypatch):
    tools = _Collection()
    runs = _Collection()
    trajectories = _Collection()
    promoted = []

    async def _approve(trajectory, judge=None):
        promoted.append((trajectory["trajectoryId"], judge))
        return f"skill:{trajectory['trajectoryId']}"

    monkeypatch.setattr(capability_discovery, "tools_collection", tools)
    monkeypatch.setattr(capability_discovery, "harvester_runs_collection", runs)
    monkeypatch.setattr(capability_discovery, "trajectories_collection", trajectories)
    monkeypatch.setattr(capability_discovery, "approve_trajectory_as_skill", _approve)

    result = await capability_discovery.run_capability_discovery(
        {
            "agentId": "agent-1",
            "companyId": "co-1",
            "email": "user@example.com",
            "capabilityDiscovery": {"mode": "broad_autodiscovery"},
            "tasks": [{"name": "Download latest PDF", "prompt": "Descargar el PDF del ultimo boletin BOPA"}],
        },
        [_bopa_connector()],
    )

    assert result["mode"] == "broad_autodiscovery"
    assert len(result["tools"]) == 3
    assert len(result["skills"]) == 3
    assert len(promoted) == 3
    assert {doc["trajectory"][0]["name"] for doc in trajectories.docs} == {
        "bopa.latest_bulletin_pdf",
        "bopa.latest_bulletin",
        "bopa.list_bulletins",
    }
    assert all(doc["metadata"]["discovererVersion"] == "v1" for doc in trajectories.docs)


@pytest.mark.asyncio
async def test_broad_discovery_publishes_custom_web_tools_without_generic_skills(monkeypatch):
    tools = _Collection()
    runs = _Collection()
    trajectories = _Collection()
    promoted = []

    async def _approve(trajectory, judge=None):
        promoted.append(trajectory)
        return "unexpected"

    monkeypatch.setattr(capability_discovery, "tools_collection", tools)
    monkeypatch.setattr(capability_discovery, "harvester_runs_collection", runs)
    monkeypatch.setattr(capability_discovery, "trajectories_collection", trajectories)
    monkeypatch.setattr(capability_discovery, "approve_trajectory_as_skill", _approve)

    result = await capability_discovery.run_capability_discovery(
        {
            "agentId": "agent-1",
            "companyId": "co-1",
            "email": "user@example.com",
            "capabilityDiscovery": {"mode": "broad_autodiscovery"},
            "tasks": [{"name": "Download PDF", "prompt": "Download the latest public PDF"}],
        },
        [_custom_web_connector()],
    )

    assert {tool["name"] for tool in result["tools"]} == {"web.fetch", "browser.navigate"}
    assert result["skills"] == []
    assert promoted == []
    assert trajectories.docs == []
