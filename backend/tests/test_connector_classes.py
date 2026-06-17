import pytest

from app.connectors.base import ConnectorConfig
from app.connectors.implementations import BOPAConnector, HoldedConnector, SMTPConnector, TelegramConnector, WebConnector
from app.connectors import registry
from app.services import agent_runtime


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    async def __aiter__(self):
        for doc in self.docs:
            yield doc

    async def to_list(self, length=None):
        return self.docs[:length] if length else self.docs


class _FakeConnectorsCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        docs = [doc for doc in self.docs if doc.get("companyId") == query.get("companyId")]
        return _FakeCursor(docs)


@pytest.mark.asyncio
async def test_telegram_connector_send_message(monkeypatch):
    calls = []

    async def fake_request(self, method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setattr(TelegramConnector, "_request", fake_request)
    connector = TelegramConnector(
        ConnectorConfig(
            connector_id="conn-1",
            company_id="company-1",
            email="user@example.com",
            name="Telegram",
            type="telegram",
            status="connected",
            config={"botToken": "bot-secret", "chatId": "123"},
        )
    )

    result = await connector.execute("telegram.send_message", {"message": "Hello"})

    assert result.success is True
    assert result.output == {"messageId": 42, "chatId": "123"}
    assert calls[0][0] == "POST"
    assert "botbot-secret/sendMessage" in calls[0][1]


@pytest.mark.asyncio
async def test_telegram_connector_get_chat(monkeypatch):
    async def fake_request(self, method, url, **kwargs):
        return {"ok": True, "result": {"id": 123, "title": "Ops", "type": "group", "username": "ops"}}

    monkeypatch.setattr(TelegramConnector, "_request", fake_request)
    connector = TelegramConnector(
        ConnectorConfig(
            connector_id="conn-1",
            company_id="company-1",
            email="user@example.com",
            name="Telegram",
            type="telegram",
            status="connected",
            config={"botToken": "bot-secret", "chatId": "123"},
        )
    )

    result = await connector.execute("telegram.get_chat", {})

    assert result.success is True
    assert result.output == {"chatId": "123", "title": "Ops", "type": "group", "username": "ops"}


@pytest.mark.asyncio
async def test_smtp_connector_draft_email_does_not_send():
    connector = SMTPConnector(
        ConnectorConfig(
            connector_id="smtp-1",
            company_id="company-1",
            email="user@example.com",
            name="SMTP",
            type="smtp",
            status="connected",
            config={"email": "from@example.com"},
        )
    )

    result = await connector.execute("smtp.draft_email", {"to": "to@example.com", "subject": "Hi", "body": "Body"})

    assert result.success is True
    assert result.output["readyToSend"] is True
    assert result.output["from"] == "from@example.com"


@pytest.mark.asyncio
async def test_holded_connector_lists_and_searches_invoices(monkeypatch):
    async def fake_request(self, method, url, **kwargs):
        if url.endswith("/contacts"):
            return [{"name": "Alice"}, {"name": "Bob"}]
        if url.endswith("/documents/invoice"):
            return [{"id": "inv-1", "contactName": "Alice", "status": "paid"}, {"id": "inv-2", "contactName": "Bob", "status": "pending"}]
        return {}

    monkeypatch.setattr(HoldedConnector, "_request", fake_request)
    connector = HoldedConnector(
        ConnectorConfig(
            connector_id="holded-1",
            company_id="company-1",
            email="user@example.com",
            name="Holded",
            type="holded",
            status="connected",
            config={"apiKey": "secret"},
        )
    )

    clients = await connector.execute("holded.list_clients", {"limit": 1})
    invoices = await connector.execute("holded.search_invoices", {"query": "alice", "limit": 5})

    assert clients.output == [{"name": "Alice"}]
    assert invoices.output == [{"id": "inv-1", "contactName": "Alice", "status": "paid"}]


@pytest.mark.asyncio
async def test_web_connector_fetch_text_and_extract_links(monkeypatch):
    class Response:
        status_code = 200
        text = "<html><head><style>.x{}</style></head><body><h1>Hello</h1><a href='/docs'>Docs</a><a href='https://example.com/pricing'>Pricing</a></body></html>"
        headers = {"content-type": "text/html"}
        url = "https://example.com/"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    connector = WebConnector(
        ConnectorConfig(
            connector_id="web-1",
            company_id="company-1",
            email="user@example.com",
            name="Web",
            type="web",
            status="connected",
            config={},
        )
    )

    text = await connector.execute("web.fetch_text", {"url": "https://example.com/"})
    links = await connector.execute("web.extract_links", {"url": "https://example.com/", "limit": 5})

    assert "Hello" in text.output["text"]
    assert links.output["links"] == [
        {"url": "https://example.com/docs", "text": "Docs"},
        {"url": "https://example.com/pricing", "text": "Pricing"},
    ]


@pytest.mark.asyncio
async def test_bopa_connector_latest_bulletin_pdf(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.implementations.latest_bopa_pdf",
        lambda: {
            "pdfUrl": "https://bopadocuments.blob.core.windows.net/bopa-documents/sumaris/038/038058.pdf",
            "numBOPA": "Núm. 58 any 2026",
        },
    )
    connector = BOPAConnector(
        ConnectorConfig(
            connector_id="bopa-1",
            company_id="company-1",
            email="user@example.com",
            name="BOPA",
            type="bopa",
            status="connected",
            config={},
        )
    )

    result = await connector.execute("bopa.latest_bulletin_pdf", {})

    assert result.success is True
    assert result.tool == "bopa.latest_bulletin_pdf"
    assert result.output["numBOPA"] == "Núm. 58 any 2026"
    assert result.output["pdfUrl"].endswith("/038/038058.pdf")


@pytest.mark.asyncio
async def test_registry_dispatches_tool_to_matching_connector(monkeypatch):
    monkeypatch.setattr(registry, "connectors_collection", _FakeConnectorsCollection([
        {
            "connectorId": "conn-1",
            "companyId": "company-1",
            "email": "user@example.com",
            "name": "Telegram",
            "type": "telegram",
            "status": "connected",
            "config": {"botToken": "bot-secret", "chatId": "123"},
        }
    ]))
    async def fake_resolve_secret_refs(refs):
        return {}

    monkeypatch.setattr(registry, "resolve_secret_refs", fake_resolve_secret_refs)

    async def fake_execute(self, tool_name, arguments):
        return self.result(tool_name, {"sent": arguments["message"]})

    monkeypatch.setattr(TelegramConnector, "execute", fake_execute)

    result = await registry.execute_connector_tool(
        company_id="company-1",
        tool_name="telegram.send_message",
        arguments={"message": "Hello"},
    )

    assert result["success"] is True
    assert result["connectorName"] == "Telegram"
    assert result["output"] == {"sent": "Hello"}


@pytest.mark.asyncio
async def test_connector_registry_resolves_deep_secret_refs(monkeypatch):
    resolved_config = {}

    async def fake_resolve_secret_refs(refs):
        return {}

    async def fake_resolve_secret_refs_deep(config):
        assert config["nested"]["botToken"] == "secret://credential/token-1"
        return {"botToken": "resolved-token", "chatId": "123"}

    monkeypatch.setattr(registry, "resolve_secret_refs", fake_resolve_secret_refs)
    monkeypatch.setattr(registry, "resolve_secret_refs_deep", fake_resolve_secret_refs_deep)

    connector = await registry.connector_for(
        {
            "connectorId": "conn-1",
            "companyId": "company-1",
            "email": "user@example.com",
            "name": "Telegram",
            "type": "telegram",
            "status": "connected",
            "config": {"nested": {"botToken": "secret://credential/token-1"}},
        }
    )

    resolved_config.update(connector.config.config)
    assert resolved_config["botToken"] == "resolved-token"
    assert resolved_config["chatId"] == "123"


@pytest.mark.asyncio
async def test_agent_runtime_requests_approval_before_write_tool(monkeypatch):
    approvals = []

    async def fake_create_pending_approval(**kwargs):
        approvals.append(kwargs)
        return {"approvalId": "approval-1", "approvalKey": kwargs["approval_key"]}

    data = {
        "tool_calls": [{"name": "telegram.send_message", "arguments": {"message": "Hello"}}],
        "done": False,
        "state_out": {},
    }
    agent_config = {"agentId": "op-1", "companyId": "company-1", "email": "user@example.com"}
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeConnectorsCollection([
        {
            "toolId": "tool-1",
            "companyId": "company-1",
            "name": "telegram.send_message",
            "runtimeRequirements": ["network"],
            "sideEffects": "writes",
        }
    ]))
    monkeypatch.setattr(agent_runtime, "create_pending_approval", fake_create_pending_approval)

    result = await agent_runtime._execute_connector_tool_calls(agent_config, data, {"state_in": {}})

    assert result["tool_calls"][0]["name"] == "api.human_approval"
    assert result["tool_calls"][0]["arguments"]["approvalId"] == "approval-1"
    assert result["state_out"]["pendingConnectorToolCall"]["name"] == "telegram.send_message"
    assert approvals[0]["proposed_action"]["name"] == "telegram.send_message"


@pytest.mark.asyncio
async def test_agent_runtime_respects_never_approval_tool_override(monkeypatch):
    executed = []

    async def fake_execute_connector_tool(company_id, tool_name, arguments):
        executed.append((company_id, tool_name, arguments))
        return {"tool": tool_name, "success": True, "output": {"ok": True}}

    async def fake_record_runtime_event(**kwargs):
        return {}

    data = {
        "tool_calls": [{"name": "crm.update_note", "arguments": {"note": "Reviewed"}}],
        "done": False,
        "state_out": {},
    }
    agent_config = {"agentId": "agent-1", "companyId": "company-1", "email": "user@example.com"}
    monkeypatch.setattr(agent_runtime, "tools_collection", _FakeConnectorsCollection([
        {
            "toolId": "tool-1",
            "companyId": "company-1",
            "name": "crm.update_note",
            "runtimeRequirements": [],
            "sideEffects": "writes",
            "permissions": {"approval": "never"},
        }
    ]))
    monkeypatch.setattr(agent_runtime, "execute_connector_tool", fake_execute_connector_tool)
    monkeypatch.setattr(agent_runtime, "record_runtime_event", fake_record_runtime_event)

    result = await agent_runtime._execute_connector_tool_calls(agent_config, data, {"state_in": {}})

    assert result["tool_calls"] == []
    assert result["tool_results"][0]["success"] is True
    assert executed[0][1] == "crm.update_note"


@pytest.mark.asyncio
async def test_skill_replay_requests_durable_approval_with_state_patch(monkeypatch):
    approvals = []

    async def fake_load_skill_trajectory(skill):
        return {
            "trajectoryId": "traj-1",
            "status": "approved",
            "actions": [{"name": "crm.update", "arguments": {"id": "1"}}],
        }

    async def fake_create_pending_approval(**kwargs):
        approvals.append(kwargs)
        return {
            "approvalId": "approval-1",
            "approvalKey": kwargs["approval_key"],
            "title": kwargs["title"],
            "message": kwargs["message"],
            "proposedAction": kwargs["proposed_action"],
        }

    monkeypatch.setattr(agent_runtime, "_load_skill_trajectory", fake_load_skill_trajectory)
    monkeypatch.setattr(agent_runtime, "create_pending_approval", fake_create_pending_approval)

    result = await agent_runtime._web_skill_response(
        {"agentId": "agent-1", "companyId": "company-1", "email": "user@example.com"},
        {"capabilityId": "skill-1", "name": "Update CRM"},
        "update crm",
        {"state_in": {}, "context": {"workItemId": "work-1", "runId": "run-1"}},
    )

    args = result["tool_calls"][0]["arguments"]
    assert result["tool_calls"][0]["name"] == "api.human_approval"
    assert args["approvalId"] == "approval-1"
    assert args["approvalKey"] == "traj-1:0"
    assert args["statePatch"]["automata_trajectory_progress"]["traj-1"]["approvedActions"] == ["traj-1:0"]
    assert approvals[0]["metadata"]["approvalKind"] == "skill_action"
    assert approvals[0]["metadata"]["workItemId"] == "work-1"


@pytest.mark.asyncio
async def test_skill_replay_respects_never_approval_override(monkeypatch):
    async def fake_load_skill_trajectory(skill):
        return {
            "trajectoryId": "traj-1",
            "status": "approved",
            "actions": [{"name": "crm.update", "arguments": {"id": "1"}}],
        }

    monkeypatch.setattr(agent_runtime, "_load_skill_trajectory", fake_load_skill_trajectory)

    result = await agent_runtime._web_skill_response(
        {"agentId": "agent-1", "companyId": "company-1", "email": "user@example.com"},
        {"capabilityId": "skill-1", "name": "Update CRM", "permissions": {"approval": "never"}},
        "update crm",
        {"state_in": {}, "context": {"workItemId": "work-1", "runId": "run-1"}},
    )

    assert result["tool_calls"] == [{"name": "crm.update", "arguments": {"id": "1"}}]
    assert result["state_out"]["automata_trajectory_progress"]["traj-1"]["approvalPending"] is False


@pytest.mark.asyncio
async def test_skill_replay_runs_first_recovery_step_after_failed_action(monkeypatch):
    async def fake_load_skill_trajectory(skill):
        return {
            "trajectoryId": "traj-1",
            "status": "approved",
            "actions": [
                {"name": "browser.click", "arguments": {"selector": "#submit"}},
                {"name": "browser.extract", "arguments": {"selector": "body"}},
            ],
            "recoverySteps": [
                {"name": "browser.wait", "arguments": {"seconds": 1}, "reasoning": "Wait for UI recovery."},
            ],
        }

    monkeypatch.setattr(agent_runtime, "_load_skill_trajectory", fake_load_skill_trajectory)

    result = await agent_runtime._web_skill_response(
        {"agentId": "agent-1", "companyId": "company-1", "email": "user@example.com"},
        {"capabilityId": "skill-1", "name": "Submit form", "permissions": {"approval": "never"}},
        "submit form",
        {
            "state_in": {
                "matchedSkillId": "skill-1",
                "automata_last_tool_results": [{"tool": "browser.click", "success": False, "error": "Element detached"}],
                "automata_trajectory_progress": {"traj-1": {"index": 1, "approvalPending": False, "approvedActions": []}},
            },
        },
    )

    assert result["tool_calls"] == [{"name": "browser.wait", "arguments": {"seconds": 1}}]
    progress = result["state_out"]["automata_trajectory_progress"]["traj-1"]
    assert progress["recoveredFailures"] == ["0:browser.click"]
    assert "recoveryIndex" not in progress


@pytest.mark.asyncio
async def test_skill_replay_continues_multi_step_recovery(monkeypatch):
    async def fake_load_skill_trajectory(skill):
        return {
            "trajectoryId": "traj-1",
            "status": "approved",
            "actions": [
                {"name": "browser.click", "arguments": {"selector": "#submit"}},
                {"name": "browser.extract", "arguments": {"selector": "body"}},
            ],
            "recoverySteps": [
                {"name": "browser.wait", "arguments": {"seconds": 1}, "reasoning": "Wait for UI recovery."},
                {"name": "browser.click", "arguments": {"selector": "#retry"}, "reasoning": "Retry the failed action."},
            ],
        }

    monkeypatch.setattr(agent_runtime, "_load_skill_trajectory", fake_load_skill_trajectory)

    result = await agent_runtime._web_skill_response(
        {"agentId": "agent-1", "companyId": "company-1", "email": "user@example.com"},
        {"capabilityId": "skill-1", "name": "Submit form", "permissions": {"approval": "never"}},
        "submit form",
        {
            "state_in": {
                "matchedSkillId": "skill-1",
                "automata_last_tool_results": [{"tool": "browser.click", "success": False, "error": "Element detached"}],
                "automata_trajectory_progress": {
                    "traj-1": {
                        "index": 1,
                        "approvalPending": False,
                        "approvedActions": [],
                        "recoveryIndex": 1,
                        "recoveringFailure": "0:browser.click",
                    }
                },
            },
        },
    )

    assert result["tool_calls"] == [{"name": "browser.click", "arguments": {"selector": "#retry"}}]
    progress = result["state_out"]["automata_trajectory_progress"]["traj-1"]
    assert "recoveryIndex" not in progress
    assert progress["recoveredFailures"] == ["0:browser.click"]
