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
    types.SimpleNamespace(
        AutoppiaAgent=object,
        _execute_tool_call=lambda *args, **kwargs: None,
        _artifact_from_create_call=lambda payload, context: {
            **context,
            "artifactId": "artifact-stub",
            "title": payload.get("title", ""),
            "name": payload.get("title", ""),
            "artifactType": payload.get("artifactType", "markdown"),
            "kind": payload.get("artifactType", "markdown"),
            "content": payload.get("content", ""),
            "fileName": f"{str(payload.get('title') or 'artifact').lower().replace(' ', '-')}.{payload.get('artifactType', 'markdown')}",
        },
    ),
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


def test_runtime_action_history_preserves_executed_and_planned_tool_arguments():
    history = sio_app._runtime_action_history(
        {
            "executed_tool_calls": [
                {
                    "name": "bopa.latest_bulletin_pdf",
                    "arguments": {"format": "pdf"},
                    "success": True,
                    "output": {"pdfUrl": "https://example.com/latest.pdf"},
                }
            ],
            "tool_calls": [
                {"name": "browser.navigate", "arguments": {"url": "https://example.com/latest.pdf"}}
            ],
        }
    )

    assert history == [
        {
            "step_index": 0,
            "tool_call": {"name": "bopa.latest_bulletin_pdf", "arguments": {"format": "pdf"}},
            "success": True,
        },
        {
            "step_index": 1,
            "tool_call": {"name": "browser.navigate", "arguments": {"url": "https://example.com/latest.pdf"}},
            "success": True,
            "executed": False,
        },
    ]


def test_runtime_result_content_explains_pending_approval():
    content = sio_app._runtime_result_content(
        {
            "state_out": {
                "pendingConnectorApproval": "approval-key",
                "pendingConnectorToolCall": {"name": "smtp.send_email"},
            }
        },
        0.2,
    )

    assert content == "Waiting for human approval before executing smtp.send_email.\n\nPrepared in 0.2s."


def test_artifacts_from_tool_results_promotes_pdf_url_to_session_artifact():
    sio_app.session_metadata["sid-artifact"] = {
        "sessionId": "session-artifact",
        "email": "user@example.com",
        "companyId": "company-1",
        "agentId": "agent-1",
        "agentName": "BOPA Agent",
    }

    artifacts = sio_app._artifacts_from_tool_results(
        "sid-artifact",
        {
            "tool_results": [
                {
                    "tool": "bopa.latest_bulletin_pdf",
                    "success": True,
                    "output": {
                        "pdfUrl": "https://example.com/bopa/latest.pdf",
                        "numBOPA": "Núm. 68 any 2026",
                        "contentType": "application/pdf",
                    },
                }
            ]
        },
    )

    assert artifacts[0]["artifactType"] == "pdf"
    assert artifacts[0]["url"] == "https://example.com/bopa/latest.pdf"
    assert artifacts[0]["sourceTool"] == "bopa.latest_bulletin_pdf"
    assert artifacts[0]["name"] == "Núm. 68 any 2026"


def test_artifacts_from_tool_results_promotes_inline_csv_and_html_artifacts():
    sio_app.session_metadata["sid-inline-artifact"] = {
        "sessionId": "session-inline",
        "email": "user@example.com",
        "companyId": "company-1",
        "agentId": "agent-1",
    }

    artifacts = sio_app._artifacts_from_tool_results(
        "sid-inline-artifact",
        {
            "tool_results": [
                {
                    "tool": "report.csv",
                    "success": True,
                    "output": {
                        "fileName": "mailbox-summary.csv",
                        "contentType": "text/csv",
                        "content": "subject,from\nInvoice,client@example.com",
                    },
                },
                {
                    "tool": "report.html",
                    "success": True,
                    "output": {
                        "title": "Digest",
                        "artifactType": "html",
                        "content": "<h1>Digest</h1>",
                    },
                },
            ]
        },
    )

    assert artifacts[0]["artifactType"] == "csv"
    assert artifacts[0]["content"] == "subject,from\nInvoice,client@example.com"
    assert artifacts[0]["fileName"] == "mailbox-summary.csv"
    assert artifacts[0]["artifactId"].startswith("artifact_")
    assert artifacts[1]["artifactType"] == "html"
    assert artifacts[1]["content"] == "<h1>Digest</h1>"


@pytest.mark.asyncio
async def test_persist_session_artifacts_adds_context_and_timestamps(monkeypatch):
    class _Artifacts:
        def __init__(self):
            self.docs = []

        async def find_one(self, query, projection=None):
            return None

        async def insert_one(self, doc):
            self.docs.append(dict(doc))

    collection = _Artifacts()
    monkeypatch.setattr(sio_app, "artifacts_collection", collection)
    sio_app.session_metadata["sid-persist"] = {
        "sessionId": "session-persist",
        "email": "user@example.com",
        "companyId": "company-1",
        "agentId": "agent-1",
    }

    persisted = await sio_app._persist_session_artifacts(
        "sid-persist",
        [{"artifactId": "artifact-1", "name": "Report", "artifactType": "pdf", "url": "https://example.com/report.pdf"}],
    )

    assert persisted[0]["sessionId"] == "session-persist"
    assert persisted[0]["email"] == "user@example.com"
    assert persisted[0]["createdAt"]
    assert persisted[0]["updatedAt"]
    assert collection.docs[0]["artifactId"] == "artifact-1"


@pytest.mark.asyncio
async def test_tool_only_session_passes_runtime_context_to_agent_step(monkeypatch):
    emitted = []
    captured = {}

    async def fake_emit(event, data=None, to=None):
        emitted.append({"event": event, "data": data, "to": to})

    async def fake_agent_step_result(agent_id, payload):
        captured["agent_id"] = agent_id
        captured["payload"] = payload
        return {
            "protocol_version": "1.0",
            "router_trace": {"decision": "skill_routing_disabled"},
            "tool_results": [{"tool": "bopa.latest_bulletin_pdf", "success": True, "output": {"pdfUrl": "https://example.com/latest.pdf"}}],
            "content": "ok",
            "done": True,
            "state_out": {},
        }

    async def fake_persist_session_artifacts(sid, artifacts):
        return artifacts

    monkeypatch.setattr(sio_app.sio, "emit", fake_emit)
    monkeypatch.setattr(sio_app, "agent_step_result", fake_agent_step_result)
    monkeypatch.setattr(sio_app, "_persist_session_artifacts", fake_persist_session_artifacts)
    sio_app.session_metadata["sid-tool"] = {
        "sessionId": "session-tool",
        "email": "user@example.com",
        "companyId": "company-1",
        "agentId": "agent-1",
    }

    await sio_app._perform_tool_only_task(
        "sid-tool",
        {
            "session_id": "session-tool",
            "email": "user@example.com",
            "companyId": "company-1",
            "benchmarkId": "bench-1",
            "taskId": "bench-1:latest_pdf_artifact",
            "disableSkillRouting": True,
        },
        "agent-1",
        "Consigue el PDF del ultimo BOPA",
    )

    assert captured["agent_id"] == "agent-1"
    assert captured["payload"]["disableSkillRouting"] is True
    assert captured["payload"]["context"]["benchmarkId"] == "bench-1"
    assert captured["payload"]["context"]["taskId"] == "bench-1:latest_pdf_artifact"
    assert captured["payload"]["context"]["disableSkillRouting"] is True
    assert any(event["event"] == "result" and event["data"]["success"] is True for event in emitted)
    action_events = [event["data"] for event in emitted if event["event"] == "action"]
    assert action_events
    assert all("elapsedSeconds" in event for event in action_events)
    assert all("emittedAt" in event for event in action_events)


@pytest.mark.asyncio
async def test_start_task_passes_runtime_state_to_tool_only_agent(monkeypatch):
    captured = {}

    class _ToolOnlyAgentsCollection:
        async def find_one(self, query, projection=None):
            return {
                "agentId": query.get("agentId"),
                "runtimeType": "local_email_agent",
                "runtimeSpec": {"browserEnabled": False},
                "runtimeEndpoint": "local",
            }

    async def fake_perform_tool_only_task(sid, data, agent_id, task, runtime_state=None):
        captured["sid"] = sid
        captured["agent_id"] = agent_id
        captured["task"] = task
        captured["runtime_state"] = runtime_state

    class _Task:
        def __init__(self, coro):
            self.coro = coro

    def fake_create_task(coro):
        return _Task(coro)

    monkeypatch.setattr(sio_app, "agents_collection", _ToolOnlyAgentsCollection())
    monkeypatch.setattr(sio_app, "_perform_tool_only_task", fake_perform_tool_only_task)
    monkeypatch.setattr(sio_app.asyncio, "create_task", fake_create_task)

    await sio_app.start_task(
        "sid-start-tool",
        {
            "task": "continue approved send",
            "agent_id": "agent-email",
            "runtimeState": {"approvedConnectorToolCalls": ["smtp.send_email:0:abc"]},
        },
    )
    task = sio_app.running_tasks.pop("sid-start-tool")
    await task.coro

    assert captured["agent_id"] == "agent-email"
    assert captured["runtime_state"] == {"approvedConnectorToolCalls": ["smtp.send_email:0:abc"]}


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
