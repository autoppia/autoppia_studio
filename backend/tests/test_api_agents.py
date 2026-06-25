import pytest

from fastapi import HTTPException

from app.routes import agent_configs
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
        if query.get("companyId") and query.get("companyId") != "company-1":
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


@pytest.mark.asyncio
async def test_selected_agent_run_is_scoped_to_company(monkeypatch):
    monkeypatch.setattr(agent_configs, "agents_collection", _FakeAgentsCollection())

    docs = await agent_configs._agent_docs_for_run(
        agent_configs.AgentRunTaskRequest(
            email="user@example.com",
            companyId="company-1",
            prompt="hello",
            target="selected",
            agentId="agent-1",
        )
    )
    assert docs[0]["agentId"] == "agent-1"

    with pytest.raises(HTTPException) as exc:
        await agent_configs._agent_docs_for_run(
            agent_configs.AgentRunTaskRequest(
                email="user@example.com",
                companyId="company-2",
                prompt="hello",
                target="selected",
                agentId="agent-1",
            )
        )
    assert exc.value.status_code == 404


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
                "riskPolicy": "autonomous",
                "runtimeRequirements": ["browser"],
                "trajectoryIds": ["traj-skill-1"],
                "tasks": [{"name": "Test Skill", "prompt": "Execute approved test skill workflow safely"}],
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
                "runtimeRequirements": ["network"],
            }
        ])


class _FakeTrajectoriesCollection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        trajectory_id_query = query.get("trajectoryId")
        allowed = None
        if isinstance(trajectory_id_query, dict):
            allowed = set(trajectory_id_query.get("$in") or [])
        for doc in self.docs:
            if allowed is not None and doc.get("trajectoryId") not in allowed:
                continue
            status_query = query.get("status")
            if isinstance(status_query, dict) and doc.get("status") not in status_query.get("$in", []):
                continue
            if isinstance(status_query, str) and doc.get("status") != status_query:
                continue
            return dict(doc)
        return None


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
async def test_agent_step_normalizes_browser_search_to_site_navigation(monkeypatch):
    class _AmazonAgentsCollection(_FakeAgentsCollection):
        async def find_one(self, query, projection=None):
            doc = await super().find_one(query, projection)
            if doc:
                doc = {**doc, "websiteUrl": "https://www.amazon.com"}
            return doc

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "tool_calls": [{"name": "browser.search", "arguments": {"query": "ratón rojo", "engine": "duckduckgo"}}],
                "reasoning": "Generalist fallback; no matching skill was selected.",
                "done": False,
                "state_out": {},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return _Response()

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _AmazonAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "busca un ratón rojo", "url": "https://www.amazon.com/dp/test", "step_index": 20, "state_in": {}},
    )

    assert result["tool_calls"] == [{"name": "browser.navigate", "arguments": {"url": "https://www.amazon.com/s?k=rat%C3%B3n+rojo"}}]
    assert result["executionMode"] == "browser_tool"


@pytest.mark.asyncio
async def test_runtime_contract_marks_unavailable_requirements(monkeypatch):
    class _NoNetworkAgentsCollection(_FakeAgentsCollection):
        async def find_one(self, query, projection=None):
            doc = await super().find_one(query, projection)
            if doc:
                doc["runtimeCapabilities"] = {"browser": False, "network": False, "apiCalls": False}
                doc["runtimeSpec"] = {"browserEnabled": False, "tools": {"browser": False, "connectors": False, "skills": True}}
            return doc

    monkeypatch.setattr(agent_runtime, "agents_collection", _NoNetworkAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())

    contract = await agent_runtime.runtime_contract_payload(await agent_runtime.load_agent_config("agent-1"))

    unavailable = {item["name"]: item for item in contract["unavailableToolCalls"]}
    assert "browser.navigate" in unavailable
    assert "telegram.send_message" in unavailable
    assert unavailable["telegram.send_message"]["runtimeAvailability"]["unavailable"] == ["network"]
    assert contract["browserPolicy"]["enabled"] is False
    assert contract["browserPolicy"]["defaultUse"] == "exception"
    assert contract["browserPolicy"]["allowedDomains"] == ["example.com"]


@pytest.mark.asyncio
async def test_skill_replay_executes_connector_tool_and_returns_result(monkeypatch):
    class _BopaCapabilitiesCollection:
        def find(self, query, projection=None):
            return _FakeListCursor([
                {
                    "capabilityId": "skill-bopa",
                    "capabilityKind": "skill",
                    "agentId": "agent-1",
                    "companyId": "company-1",
                    "name": "Descargar PDF último boletín",
                    "toolName": "skill.descargar_pdf_ultimo_boletin",
                    "description": "Descargar PDF último boletín BOPA",
                    "runtime": "trajectory_replay_with_recovery",
                    "trajectoryIds": ["traj-bopa"],
                    "runtimeRequirements": ["network"],
                    "tasks": [{"name": "Download latest BOPA PDF", "prompt": "Descargar documento oficial boletín BOPA Andorra"}],
                }
            ])

    class _BopaToolsCollection:
        def find(self, query, projection=None):
            return _FakeListCursor([
                {
                    "toolId": "tool-bopa",
                    "companyId": "company-1",
                    "connectorId": "conn-bopa",
                    "name": "bopa.latest_bulletin_pdf",
                    "description": "Latest BOPA PDF",
                    "sideEffects": "reads",
                    "riskLevel": "low",
                    "executionType": "api_call",
                    "runtimeRequirements": ["network"],
                }
            ])

    async def fake_execute_connector_tool(company_id, tool_name, arguments):
        return {
            "tool": tool_name,
            "success": True,
            "output": {
                "pdfUrl": "https://bopadocuments.blob.core.windows.net/bopa-documents/sumaris/038/038058.pdf",
                "numBOPA": "Núm. 58 any 2026",
                "publishedAt": "2026-06-04T22:00:00+00:00",
            },
        }

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _BopaCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _BopaToolsCollection())
    monkeypatch.setattr(agent_runtime, "trajectories_collection", _FakeTrajectoriesCollection([
        {
            "trajectoryId": "traj-bopa",
            "status": "approved",
            "trajectory": [{"name": "bopa.latest_bulletin_pdf", "arguments": {}}],
        }
    ]))
    monkeypatch.setattr(agent_runtime, "execute_connector_tool", fake_execute_connector_tool)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "Descargar documento oficial boletín BOPA Andorra", "state_in": {}, "step_index": 0},
    )

    assert result["done"] is True
    assert result["tool_calls"] == []
    assert result["tool_results"][0]["tool"] == "bopa.latest_bulletin_pdf"
    assert result["executed_tool_calls"][0]["name"] == "bopa.latest_bulletin_pdf"
    assert result["executed_tool_calls"][0]["arguments"] == {}
    assert result["executed_tool_calls"][0]["success"] is True
    assert result["tool_results"][0]["output"]["pdfUrl"].endswith("/038/038058.pdf")
    assert "Núm. 58 any 2026" in result["content"]


@pytest.mark.asyncio
async def test_agent_step_ignores_mismatched_external_runtime_without_skill_match(monkeypatch):
    class _AmazonAgentsCollection(_FakeAgentsCollection):
        async def find_one(self, query, projection=None):
            doc = await super().find_one(query, projection)
            if doc:
                doc = {**doc, "websiteUrl": "https://www.amazon.com"}
            return doc

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "tool_calls": [{"name": "browser.click", "arguments": {"selector": {"type": "cssSelector", "value": "#movie"}}}],
                "reasoning": "CUSTOM OPERATOR INSTRUCTIONS: You are operating the Autocinema website.",
                "done": False,
                "state_out": {},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return _Response()

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _AmazonAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "busca un ratón rojo", "url": "https://www.amazon.com/dp/test", "step_index": 20, "state_in": {}},
    )

    assert result["tool_calls"] == [{"name": "browser.navigate", "arguments": {"url": "https://www.amazon.com/s?k=rat%C3%B3n+rojo"}}]
    assert "mismatched external runtime" in result["reasoning"]


@pytest.mark.asyncio
async def test_agent_step_blocks_browser_tools_when_browser_disabled(monkeypatch):
    class _NoBrowserAgentsCollection(_FakeAgentsCollection):
        async def find_one(self, query, projection=None):
            doc = await super().find_one(query, projection)
            if doc:
                doc = {
                    **doc,
                    "runtimeCapabilities": {"browser": False, "humanApprovalForWrites": True},
                    "runtimeSpec": {
                        "browserEnabled": False,
                        "browserMode": "headless",
                        "maxCreditsPerRun": 1.5,
                        "tools": {"browser": False, "connectors": True, "skills": True, "knowledge": False},
                    },
                }
            return doc

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "tool_calls": [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}],
                "reasoning": "Use browser.",
                "done": False,
                "state_out": {"x": 1},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return _Response()

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _NoBrowserAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "hello", "step_index": 2, "state_in": {"memory": {"seen": 1}}},
    )

    assert result["tool_calls"] == []
    assert result["done"] is True
    assert "Browser access is disabled" in result["content"]


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
    monkeypatch.setattr(agent_runtime, "trajectories_collection", _FakeTrajectoriesCollection([
        {
            "trajectoryId": "traj-skill-1",
            "status": "approved",
            "trajectory": [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}],
        }
    ]))
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {"prompt": "Execute approved test skill workflow safely", "step_index": 0},
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
    monkeypatch.setattr(agent_runtime, "trajectories_collection", _FakeTrajectoriesCollection([
        {
            "trajectoryId": "traj-skill-1",
            "status": "approved",
            "trajectory": [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}],
        }
    ]))
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {
            "prompt": "Execute approved test skill workflow safely",
            "step_index": 1,
            "state_in": {"matchedSkillId": "skill-1"},
        },
    )

    assert result["tool_calls"] == [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}]
    assert result["state_out"]["matchedSkillId"] == "skill-1"


@pytest.mark.asyncio
async def test_agent_step_can_match_skill_on_resume_with_empty_state(monkeypatch):
    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise AssertionError("matched skills should not call the external runtime when resume state is empty")

    async def fake_record_runtime_event(**kwargs):
        return None

    monkeypatch.setattr(agent_runtime, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(agent_runtime, "capabilities_collection", _FakeCapabilitiesCollection())
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeToolsCollection())
    monkeypatch.setattr(agent_runtime, "trajectories_collection", _FakeTrajectoriesCollection([
        {
            "trajectoryId": "traj-skill-1",
            "status": "approved",
            "trajectory": [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}],
        }
    ]))
    monkeypatch.setattr(agent_runtime.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime.agent_step_result(
        "agent-1",
        {
            "prompt": "Execute approved test skill workflow safely",
            "step_index": 3,
            "state_in": {},
        },
    )

    assert result["tool_calls"] == [{"name": "browser.navigate", "arguments": {"url": "https://example.com"}}]
    assert result["state_out"]["matchedSkillId"] == "skill-1"


@pytest.mark.asyncio
async def test_api_lists_agents_for_api_key_owner(monkeypatch):
    monkeypatch.setattr(api_agents, "agents_collection", _FakeAgentsCollection())

    result = await api_agents.list_agents(api_key={"email": "user@example.com"})

    assert len(result["agents"]) == 1
    assert result["agents"][0]["agentId"] == "agent-1"
    assert result["agents"][0]["email"] == "user@example.com"
    assert result["agents"][0]["tasks"][0]["name"] == "Test Skill"


@pytest.mark.asyncio
async def test_api_lists_agent_skills_with_runtime_policy(monkeypatch):
    monkeypatch.setattr(api_agents, "load_agent_config", lambda agent_id: _FakeAgentsCollection().find_one({"agentId": agent_id}))
    monkeypatch.setattr(api_agents, "capabilities_collection", _FakeCapabilitiesCollection())

    result = await api_agents.list_agent_skills("agent-1", api_key={"email": "user@example.com"})

    assert result["skills"][0]["runtimePolicy"]["policy"] == "autonomous"
    assert result["skills"][0]["runtimePolicy"]["approvalMode"] == "never"
    assert result["skills"][0]["runtimePolicy"]["approvalRequiredFor"] == []
    assert result["skills"][0]["runtimePolicy"]["runtimeClass"] == "browser"


@pytest.mark.asyncio
async def test_api_rejects_agent_from_other_api_key_owner(monkeypatch):
    async def fake_load_agent_config(agent_id):
        return await _FakeAgentsCollection().find_one({"agentId": agent_id})

    monkeypatch.setattr(api_agents, "load_agent_config", fake_load_agent_config)

    with pytest.raises(HTTPException) as exc:
        await api_agents.get_agent("agent-1", api_key={"email": "other@example.com"})

    assert exc.value.status_code == 404
