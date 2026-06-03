import pytest

from fastapi import HTTPException

from app.routes.api import agents as api_agents
from app.routes.api.agents import AgentStepRequest, _step_url
from app.services import agent_runtime


def test_step_url_normalizes_runtime_endpoint():
    assert _step_url("") == ""
    assert _step_url("http://localhost:5060") == "http://localhost:5060/step"
    assert _step_url("http://localhost:5060/step") == "http://localhost:5060/step"
    assert _step_url("http://localhost:5060/") == "http://localhost:5060/step"


def test_agent_step_request_does_not_share_mutable_defaults():
    first = AgentStepRequest()
    second = AgentStepRequest()

    first.history.append({"role": "user"})
    first.context["x"] = 1

    assert second.history == []
    assert second.context == {}


class _FakeListCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def to_list(self, length=None):
        return self.docs[:length] if length else self.docs


class _FakeAgentsCollection:
    async def find_one(self, query, projection=None):
        if query.get("agentId") != "agent-1":
            return None
        if query.get("email") and query.get("email") != "user@example.com":
            return None
        return {
            "agentId": "agent-1",
            "name": "Celeris Agent",
            "email": "user@example.com",
            "companyId": "company-1",
            "websiteUrl": "https://example.com",
            "baseRuntimeEndpoint": "http://runtime.local",
            "runtimeCapabilities": {"humanApprovalForWrites": True},
            "tasks": [{"name": "Test Skill", "prompt": "Use test skill"}],
        }

    def find(self, query, projection=None):
        if query.get("email") != "user@example.com":
            return _FakeListCursor([])
        return _FakeListCursor([
            {
                "agentId": "agent-1",
                "name": "Celeris Agent",
                "email": "user@example.com",
                "companyId": "company-1",
                "websiteUrl": "https://example.com",
                "baseRuntimeEndpoint": "http://runtime.local",
                "runtimeCapabilities": {"humanApprovalForWrites": True},
                "tasks": [{"name": "Test Skill", "prompt": "Use test skill"}],
            }
        ])


class _FakeCapabilitiesCollection:
    def find(self, query, projection=None):
        return _FakeListCursor([
            {
                "capabilityId": "skill-1",
                "capabilityKind": "skill",
                "agentId": "agent-1",
                "companyId": "company-1",
                "name": "Test Skill",
                "toolName": "skill.test_skill",
                "description": "Use test skill",
                "runtime": "skill_tool",
                "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}},
            }
        ])


class _FakeToolsCollection:
    def find(self, query, projection=None):
        return _FakeListCursor([
            {
                "toolId": "tool-1",
                "companyId": "company-1",
                "connectorId": "conn-1",
                "name": "telegram.send_message",
                "description": "Send a Telegram message",
                "sideEffects": "writes",
                "riskLevel": "medium",
                "executionType": "api_call",
            }
        ])


@pytest.mark.asyncio
async def test_agent_step_injects_agent_config_and_records_runtime_events(monkeypatch):
    posted = {}
    events = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"tool_calls": [], "done": True, "state_out": {"memory": {"last": "ok"}}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _Response()

    async def fake_record_runtime_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(agent_runtime, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "hello", "state_in": {"memory": {"seen": 1}}, "step_index": 2},
    )

    assert posted["url"] == "http://runtime.local/step"
    agent_config = posted["json"]["agentConfig"]
    assert agent_config["schemaVersion"] == "agent_config/v1"
    assert agent_config["agentId"] == "agent-1"
    assert agent_config["memory"] == {"seen": 1}
    assert any(item["name"] == "skill.test_skill" for item in agent_config["skills"])
    assert any(item["name"] == "telegram.send_message" for item in agent_config["tools"])
    assert posted["json"]["context"]["agentConfig"]["agentId"] == "agent-1"
    assert result["state_out"]["memory"] == {"seen": 1, "last": "ok"}
    assert [event["event_type"] for event in events] == ["agent.step.request", "agent.step.result"]


@pytest.mark.asyncio
async def test_agent_step_matches_skill_before_external_runtime(monkeypatch):
    events = []

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise AssertionError("matched skills should not call the external runtime on the first step")

    async def fake_record_runtime_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(agent_runtime, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "Use test skill now", "step_index": 0},
    )

    assert result["tool_calls"] == [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}]
    assert result["capability_match"]["name"] == "Test Skill"
    assert result["state_out"]["matchedSkillId"] == "skill-1"
    assert [event["event_type"] for event in events] == ["agent.step.request", "agent.step.result"]


@pytest.mark.asyncio
async def test_agent_step_keeps_matched_skill_state_local(monkeypatch):
    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise AssertionError("matched skill state should not fall back to the external runtime")

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {
            "prompt": "Use test skill now",
            "step_index": 1,
            "state_in": {"matchedSkillId": "skill-1"},
        },
    )

    assert result["done"] is True
    assert result["tool_calls"] == []
    assert "no approved executable trajectory" in result["content"]


@pytest.mark.asyncio
async def test_api_lists_agents_for_api_key_owner(monkeypatch):
    monkeypatch.setattr(api_agents, "agents_collection", _FakeAgentsCollection())

    result = await api_agents.list_agents(api_key={"email": "user@example.com"})

    assert len(result["agents"]) == 1
    assert result["agents"][0]["agentId"] == "agent-1"
    assert result["agents"][0]["email"] == "user@example.com"
    assert result["agents"][0]["tasks"][0]["name"] == "Test Skill"


@pytest.mark.asyncio
async def test_api_rejects_agent_from_other_api_key_owner(monkeypatch):
    async def fake_load_agent_config(agent_id):
        return await _FakeAgentsCollection().find_one({"agentId": agent_id})

    monkeypatch.setattr(api_agents, "load_agent_config", fake_load_agent_config)

    with pytest.raises(HTTPException) as exc:
        await api_agents.get_agent("agent-1", api_key={"email": "other@example.com"})

    assert exc.value.status_code == 404
