import pytest

from app.connectors.base import ConnectorConfig
from app.connectors.implementations import TelegramConnector
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
async def test_agent_runtime_requests_approval_before_write_tool():
    data = {
        "tool_calls": [{"name": "telegram.send_message", "arguments": {"message": "Hello"}}],
        "done": False,
        "state_out": {},
    }
    agent_config = {"agentId": "op-1", "companyId": "company-1"}

    result = await agent_runtime._execute_connector_tool_calls(agent_config, data, {"state_in": {}})

    assert result["tool_calls"][0]["name"] == "api.human_approval"
    assert result["state_out"]["pendingConnectorToolCall"]["name"] == "telegram.send_message"
