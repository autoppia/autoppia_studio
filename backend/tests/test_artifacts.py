import pytest

from app.request_scope import RequestScope
from app.routes import artifacts


class _Result:
    def __init__(self, deleted_count=0):
        self.deleted_count = deleted_count


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def sort(self, field, direction):
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=direction < 0)
        return self

    async def to_list(self, length=500):
        return [dict(doc) for doc in self.docs[:length]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return _Result()
        return _Result()

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return _Result(deleted_count=before - len(self.docs))


def _matches(doc, query):
    return all(_lookup(doc, key) == value for key, value in query.items())


def _lookup(doc, key):
    value = doc
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


@pytest.mark.asyncio
async def test_artifact_crud_and_download(monkeypatch):
    monkeypatch.setattr(artifacts, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    artifact_collection = _Collection()
    monkeypatch.setattr(artifacts, "artifacts_collection", artifact_collection)
    scope = RequestScope(email="user@example.com", token_email="user@example.com")

    created = await artifacts.create_company_artifact(
        "co-1",
        artifacts.ArtifactCreateRequest(
            email="user@example.com",
            title="Q2 Report",
            artifactType="markdown",
            content="# Q2\n\nRevenue is up.",
        ),
        scope,
    )

    listed = await artifacts.list_company_artifacts("co-1", email="user@example.com", scope=scope)
    updated = await artifacts.update_artifact(
        created["artifact"]["artifactId"],
        artifacts.ArtifactUpdateRequest(title="Q2 Board Report", artifactType="html", content="<h1>Q2</h1>"),
        scope,
    )
    downloaded = await artifacts.download_artifact(created["artifact"]["artifactId"], email="user@example.com", scope=scope)
    deleted = await artifacts.delete_artifact(created["artifact"]["artifactId"], scope)

    assert listed["artifacts"][0]["title"] == "Q2 Report"
    assert listed["artifacts"][0]["artifactContract"]["businessOutput"] is True
    assert listed["artifacts"][0]["artifactContract"]["separatedFromTrace"] is True
    assert listed["artifacts"][0]["artifactContract"]["governance"]["knowledgeReady"] is True
    assert updated["artifact"]["artifactType"] == "html"
    assert downloaded.body == b"<h1>Q2</h1>"
    assert downloaded.media_type.startswith("text/html")
    assert deleted == {"success": True}


@pytest.mark.asyncio
async def test_artifact_listing_supports_capability_filters(monkeypatch):
    monkeypatch.setattr(artifacts, "companies_collection", _Collection([{"companyId": "co-1", "email": "user@example.com"}]))
    artifact_collection = _Collection([
        {
            "artifactId": "artifact-skill",
            "companyId": "co-1",
            "email": "user@example.com",
            "title": "Skill artifact",
            "artifactType": "markdown",
            "content": "# Skill",
            "sessionId": "session-1",
            "metadata": {
                "skillId": "skill-1",
                "trajectoryId": "trajectory-1",
                "toolId": "tool-1",
                "workItemId": "work-1",
                "approvalId": "approval-1",
                "approvalKey": "smtp.send_email:0:abc",
                "approvalState": "pending",
                "approvalBoundary": "send",
            },
            "updatedAt": "2026-06-25T10:00:00+00:00",
        },
        {
            "artifactId": "artifact-other",
            "companyId": "co-1",
            "email": "user@example.com",
            "title": "Other artifact",
            "artifactType": "markdown",
            "content": "# Other",
            "sessionId": "session-2",
            "metadata": {"skillId": "skill-2", "trajectoryId": "trajectory-2", "toolId": "tool-2"},
            "updatedAt": "2026-06-25T09:00:00+00:00",
        },
    ])
    monkeypatch.setattr(artifacts, "artifacts_collection", artifact_collection)
    scope = RequestScope(email="user@example.com", token_email="user@example.com")

    by_skill = await artifacts.list_company_artifacts("co-1", email="user@example.com", skillId="skill-1", scope=scope)
    by_trajectory = await artifacts.list_company_artifacts("co-1", email="user@example.com", trajectoryId="trajectory-1", scope=scope)
    by_tool = await artifacts.list_company_artifacts("co-1", email="user@example.com", toolId="tool-1", scope=scope)
    by_work_item = await artifacts.list_company_artifacts("co-1", email="user@example.com", workItemId="work-1", scope=scope)

    assert [item["artifactId"] for item in by_skill["artifacts"]] == ["artifact-skill"]
    assert [item["artifactId"] for item in by_trajectory["artifacts"]] == ["artifact-skill"]
    assert [item["artifactId"] for item in by_tool["artifacts"]] == ["artifact-skill"]
    assert [item["artifactId"] for item in by_work_item["artifacts"]] == ["artifact-skill"]
    artifact = by_skill["artifacts"][0]
    assert artifact["skillId"] == "skill-1"
    assert artifact["trajectoryId"] == "trajectory-1"
    assert artifact["toolId"] == "tool-1"
    assert artifact["workItemId"] == "work-1"
    assert artifact["capabilityRefs"]["linked"] is True
    assert artifact["approvalRelation"]["linked"] is True
    assert artifact["approvalRelation"]["approvalId"] == "approval-1"
    assert artifact["approvalRelation"]["approvalKey"] == "smtp.send_email:0:abc"
    assert artifact["approvalRelation"]["state"] == "pending"
    assert artifact["approvalRelation"]["boundary"] == "send"
    assert artifact["artifactContract"]["governance"]["approvalRelation"]["requiresReview"] is True
