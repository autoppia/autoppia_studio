import pytest

from app.routes import agent_configs
from app.routes.agent_configs import AgentRuntimeSettingsRequest
from app.request_scope import RequestScope


class _AgentsCollection:
    def __init__(self):
        self.doc = {
            "agentId": "agent-1",
            "email": "user@example.com",
            "name": "Demo Agent",
            "websiteUrl": "https://example.com",
            "runtimeCapabilities": {"browser": True, "apiCalls": True, "humanApprovalForWrites": True},
            "runtimeSpec": {
                "browserEnabled": True,
                "browserMode": "visible",
                "maxCreditsPerRun": 5,
                "tools": {"browser": True, "connectors": True, "skills": True, "knowledge": False},
            },
        }

    async def find_one(self, query, projection=None):
        if query.get("agentId") == self.doc["agentId"]:
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        if query.get("agentId") == self.doc["agentId"]:
            self.doc.update(update.get("$set", {}))


@pytest.mark.asyncio
async def test_update_agent_runtime_settings_persists_runtime_spec(monkeypatch):
    agents = _AgentsCollection()
    monkeypatch.setattr(agent_configs, "agents_collection", agents)

    result = await agent_configs.update_agent_runtime_settings(
        "agent-1",
        AgentRuntimeSettingsRequest(browserEnabled=False, browserMode="headless", maxCreditsPerRun=2.25),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert result["success"] is True
    assert result["agent"]["runtimeCapabilities"]["browser"] is False
    assert result["agent"]["runtimeSpec"]["browserEnabled"] is False
    assert result["agent"]["runtimeSpec"]["browserMode"] == "headless"
    assert result["agent"]["runtimeSpec"]["maxCreditsPerRun"] == 2.25
    assert result["agent"]["runtimeSpec"]["tools"]["browser"] is False
