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
    return all(doc.get(key) == value for key, value in query.items())


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
    assert updated["artifact"]["artifactType"] == "html"
    assert downloaded.body == b"<h1>Q2</h1>"
    assert downloaded.media_type.startswith("text/html")
    assert deleted == {"success": True}
