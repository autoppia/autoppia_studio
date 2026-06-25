import pytest

from app.services import skills
from app.services.skills import approve_trajectory_as_skill, skill_slug


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(query)
            doc.update(update.get("$set", {}))
            self.docs.append(doc)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, item) for item in value):
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


def test_skill_slug_normalizes_accents_to_ascii():
    assert skill_slug("Descargar PDF último boletín") == "descargar_pdf_ultimo_boletin"


@pytest.mark.asyncio
async def test_approve_trajectory_as_skill_persists_ready_skill_package(monkeypatch):
    agents = _Collection([{"agentId": "agent-1", "companyId": "co-1", "email": "owner@example.com"}])
    trajectories = _Collection(
        [
            {
                "trajectoryId": "traj-1",
                "agentId": "agent-1",
                "companyId": "co-1",
                "email": "owner@example.com",
                "benchmarkId": "bench-1",
                "evalId": "task-1",
                "taskName": "Reply to claim",
                "prompt": "Read the claim, draft a customer answer, and stop before sending.",
                "connectorIds": ["imap", "insurance-erp"],
                "toolIds": ["imap.read_email", "erp.search_claims", "smtp.draft_email"],
                "runtimeRequirements": ["network"],
                "actions": [{"name": "smtp.draft_email", "arguments": {}}],
                "inputEntities": ["Claim"],
                "outputEntity": "Draft email",
                "source": "harvester",
            }
        ]
    )
    capabilities = _Collection()
    monkeypatch.setattr(skills, "agents_collection", agents)
    monkeypatch.setattr(skills, "trajectories_collection", trajectories)
    monkeypatch.setattr(skills, "capabilities_collection", capabilities)

    capability_id = await approve_trajectory_as_skill(
        trajectories.docs[0],
        judge={"label": "pass", "confidence": 0.92},
    )

    skill = capabilities.docs[0]
    assert capability_id == "agent-1:reply_to_claim"
    assert trajectories.docs[0]["status"] == "approved"
    assert skill["status"] == "ready"
    assert skill["promotionStatus"] == "ready"
    assert skill["trajectoryIds"] == ["traj-1"]
    assert skill["lineage"]["benchmarkIds"] == ["bench-1"]
    assert skill["lineage"]["evalIds"] == ["task-1"]
    assert skill["hardeningStatus"]["checks"]["lineage"] is True
    assert skill["hardeningStatus"]["checks"]["regression"] is True
    assert skill["hardeningStatus"]["checks"]["publishableRegression"] is False
    assert skill["permissions"]["approval"] == "always"
    assert skill["versionHistory"][-1]["reason"] == "trajectory_approved"
    assert skill["skillPackage"]["format"] == "autoppia.agent_skill"
    assert skill["skillPackage"]["metadata"]["promotionStatus"] == "ready"
    assert skill["skillPackage"]["execution"]["trajectoryIds"] == ["traj-1"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["benchmarkIds"] == ["bench-1"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["publishable"] is False
