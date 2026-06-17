import pytest
import sys
import types


class _SocketIoModule(types.SimpleNamespace):
    class AsyncServer:
        def __init__(self, *args, **kwargs):
            pass

        def on(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        async def emit(self, *args, **kwargs):
            return None


sys.modules.setdefault("socketio", _SocketIoModule())
sys.modules.setdefault(
    "agent.autoppia_agent",
    types.SimpleNamespace(AutoppiaAgent=object, _execute_tool_call=lambda *args, **kwargs: None),
)
sys.modules.setdefault("agent.browser_executor", types.SimpleNamespace(BrowserExecutor=object))

from app import sio_app


class _FakeAgent:
    instances = []

    def __init__(self):
        self.history = []
        self.step_index = 0
        self._state = {}
        self.initialize_calls = []
        self.browser_executor = None
        _FakeAgent.instances.append(self)

    async def initialize(
        self,
        task,
        initial_url=None,
        storage_state_path=None,
        context_id="",
        agent_base_url="",
        browser_mode="",
    ):
        self.initialize_calls.append(
            {
                "task": task,
                "initial_url": initial_url,
                "storage_state_path": storage_state_path,
                "context_id": context_id,
                "agent_base_url": agent_base_url,
                "browser_mode": browser_mode,
            }
        )

    def get_live_url(self):
        return ""


class _FakeAgentsCollection:
    async def find_one(self, query, projection=None):
        if query.get("agentId") != "agent-1":
            return None
        return {"agentId": "agent-1", "runtimeEndpoint": "http://127.0.0.1:8080/runtime/agents/agent-1/step"}


@pytest.fixture(autouse=True)
def clear_fake_agents():
    _FakeAgent.instances = []


@pytest.fixture
def sio_resume_patches(monkeypatch):
    emitted = []
    scheduled = []

    async def fake_emit(event, data=None, to=None):
        emitted.append({"event": event, "data": data, "to": to})

    async def fake_emit_tabs(sid, agent_config):
        emitted.append({"event": "tabs", "data": {"tabs": []}, "to": sid})

    async def fake_perform_task(sid):
        return None

    def fake_create_task(coro):
        coro.close()
        scheduled.append(coro)
        return object()

    monkeypatch.setattr(sio_app, "AutoppiaAgent", _FakeAgent)
    monkeypatch.setattr(sio_app, "agents_collection", _FakeAgentsCollection())
    monkeypatch.setattr(sio_app.sio, "emit", fake_emit)
    monkeypatch.setattr(sio_app, "_emit_tabs", fake_emit_tabs)
    monkeypatch.setattr(sio_app, "_perform_task", fake_perform_task)
    monkeypatch.setattr(sio_app.asyncio, "create_task", fake_create_task)
    return emitted, scheduled


@pytest.mark.asyncio
async def test_resume_task_uses_selected_agent_runtime_and_restores_state(sio_resume_patches):
    await sio_app.resume_task(
        "sid-1",
        {
            "task": "find a red mouse",
            "lastUrl": "https://amazon.com/dp/test",
            "actionHistory": [{"step_index": 0, "tool_call": {"name": "browser.navigate"}}],
            "runtimeState": {"matchedSkillId": "skill-1", "automata_trajectory_progress": {"t1": {"index": 2}}},
            "context_id": "ctx-1",
            "agent_id": "agent-1",
            "browser_mode": "local",
        },
    )

    agent = _FakeAgent.instances[-1]
    assert agent.initialize_calls[0]["agent_base_url"] == "http://127.0.0.1:8080/runtime/agents/agent-1/step"
    assert agent.initialize_calls[0]["context_id"] == "ctx-1"
    assert agent.initialize_calls[0]["browser_mode"] == "local"
    assert agent.history == [{"step_index": 0, "tool_call": {"name": "browser.navigate"}}]
    assert agent.step_index == 1
    assert agent._state["matchedSkillId"] == "skill-1"
    assert sio_app.sessions["sid-1"] is agent


@pytest.mark.asyncio
async def test_resume_task_preserves_legacy_global_runtime_fallback(sio_resume_patches):
    await sio_app.resume_task(
        "sid-2",
        {
            "task": "continue",
            "lastUrl": "https://example.com",
            "actionHistory": [],
        },
    )

    agent = _FakeAgent.instances[-1]
    assert agent.initialize_calls[0]["agent_base_url"] == ""
    assert agent.step_index == 0
    assert agent._state == {}
