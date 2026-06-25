import pytest

from app.routes import skills as skills_route


class _Result:
    matched_count = 1
    deleted_count = 1


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def sort(self, *args):
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._iter))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query):
        return _Cursor([doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())])

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
                return _Result()
        result = _Result()
        result.matched_count = 0
        return result

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not all(doc.get(key) == value for key, value in query.items())]
        result = _Result()
        result.deleted_count = before - len(self.docs)
        return result


@pytest.mark.asyncio
async def test_legacy_skills_create_and_list_return_skill_package(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(skills_route, "skills_collection", collection)

    created = await skills_route.create_skill(
        skills_route.SkillCreateRequest(
            email="owner@example.com",
            name="Search claim",
            goal="Find claim status",
            instructions="Open ERP and search {{claim_id}}",
            parameters=[skills_route.SkillParameter(name="claim_id", description="Claim identifier")],
            actions=[{"action": "erp.search_claims", "args": {"claimId": "{{claim_id}}"}}],
        )
    )
    listed = await skills_route.get_skills("owner@example.com")

    skill = created["skill"]
    assert skill["capabilityKind"] == "skill"
    assert skill["promotionStatus"] == "draft"
    assert skill["hardeningStatus"]["checks"]["lineage"] is True
    assert skill["skillPackage"]["format"] == "autoppia.agent_skill"
    assert skill["skillPackage"]["ioContract"]["inputs"]["parameters"][0]["name"] == "claim_id"
    assert skill["skillPackage"]["execution"]["actions"][0]["action"] == "erp.search_claims"
    assert listed["skills"][0]["skillPackage"]["format"] == "autoppia.agent_skill"


@pytest.mark.asyncio
async def test_legacy_skills_update_rebuilds_package(monkeypatch):
    collection = _Collection(
        [
            {
                "skillId": "skill-1",
                "email": "owner@example.com",
                "name": "Old",
                "goal": "Old goal",
                "instructions": "Old instructions",
                "parameters": [],
                "actions": [],
                "version": 1,
                "versionHistory": [],
            }
        ]
    )
    monkeypatch.setattr(skills_route, "skills_collection", collection)

    result = await skills_route.update_skill(
        "skill-1",
        skills_route.SkillCreateRequest(
            email="owner@example.com",
            name="Updated",
            goal="Updated goal",
            instructions="Use updated workflow",
            actions=[{"action": "browser.navigate", "args": {"url": "https://example.com"}}],
        ),
    )

    skill = result["skill"]
    assert skill["name"] == "Updated"
    assert skill["versionHistory"][-1]["reason"] == "legacy_skill_updated"
    assert skill["lineage"]["recordedActions"] == 1
    assert skill["skillPackage"]["metadata"]["name"] == "Updated"
