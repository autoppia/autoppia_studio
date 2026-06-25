import pytest

from app.routes import agent_assets


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return


@pytest.mark.asyncio
async def test_create_agent_capability_creates_packaged_skill(monkeypatch):
    agents = _Collection([{"agentId": "agent-1", "companyId": "co-1", "email": "owner@example.com"}])
    capabilities = _Collection()
    monkeypatch.setattr(agent_assets, "agents_collection", agents)
    monkeypatch.setattr(agent_assets, "capabilities_collection", capabilities)

    result = await agent_assets.create_agent_capability(
        "agent-1",
        agent_assets.CapabilityCreateRequest(
            email="owner@example.com",
            name="Handle claim status",
            description="Search claim state and draft the customer reply.",
            trajectoryIds=["traj-1"],
            expectedArtifacts=["draft_email"],
            inputEntities=["Claim"],
            outputEntity="Draft email",
        ),
    )

    skill = result["capability"]
    assert skill["capabilityKind"] == "skill"
    assert skill["companyId"] == "co-1"
    assert skill["status"] == "ready"
    assert skill["promotionStatus"] == "ready"
    assert skill["lineage"]["trajectoryIds"] == ["traj-1"]
    assert skill["hardeningStatus"]["checks"]["lineage"] is True
    assert skill["skillPackage"]["format"] == "autoppia.agent_skill"
    assert skill["skillPackage"]["metadata"]["promotionStatus"] == "ready"
    assert skill["skillPackage"]["ioContract"]["outputs"]["artifacts"] == ["draft_email"]
    assert skill["versionHistory"][-1]["reason"] == "manual_skill_created"
