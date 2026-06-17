import pytest

from agent.autoppia_agent import _artifact_from_create_call
from app.routes import session as session_routes


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

    async def __aiter__(self):
        for doc in self.docs:
            yield dict(doc)


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

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return _Result(deleted_count=before - len(self.docs))


def _matches(doc, query):
    return all(doc.get(key) == value for key, value in query.items())


@pytest.mark.asyncio
async def test_session_artifact_create_list_and_download(monkeypatch):
    monkeypatch.setattr(
        session_routes,
        "sessions_collection",
        _Collection([{"sessionId": "session-1", "email": "user@example.com"}]),
    )
    artifacts = _Collection()
    monkeypatch.setattr(session_routes, "artifacts_collection", artifacts)

    created = await session_routes.create_session_artifact(
        "session-1",
        session_routes.SessionArtifactCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Renewal report",
            artifactType="markdown",
            content="# Renewals\n\n- Policy A",
        ),
    )
    listed = await session_routes.list_session_artifacts("session-1", email="user@example.com")
    downloaded = await session_routes.download_session_artifact(
        "session-1",
        created["artifact"]["artifactId"],
        email="user@example.com",
    )

    assert created["artifact"]["sessionId"] == "session-1"
    assert created["artifact"]["companyId"] == "company-1"
    assert listed["artifacts"][0]["title"] == "Renewal report"
    assert downloaded.body == b"# Renewals\n\n- Policy A"
    assert downloaded.media_type.startswith("text/markdown")


def test_artifacts_create_tool_payload_becomes_session_artifact():
    artifact = _artifact_from_create_call(
        {
            "title": "Client summary",
            "artifactType": "html",
            "content": "<h1>Client</h1>",
        },
        {"sessionId": "session-1", "email": "user@example.com", "companyId": "company-1", "agentId": "agent-1"},
    )

    assert artifact["sessionId"] == "session-1"
    assert artifact["email"] == "user@example.com"
    assert artifact["companyId"] == "company-1"
    assert artifact["agentId"] == "agent-1"
    assert artifact["artifactType"] == "html"
    assert artifact["content"] == "<h1>Client</h1>"
    assert artifact["fileName"].endswith(".html")
