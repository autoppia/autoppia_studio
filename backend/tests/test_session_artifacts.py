import pytest

from agent.autoppia_agent import _artifact_from_create_call
from app.routes import session as session_routes


class _Result:
    def __init__(self, deleted_count=0, upserted_id=None):
        self.deleted_count = deleted_count
        self.upserted_id = upserted_id


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

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if _matches(doc, query))

    async def update_one(self, query, update, upsert=False):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                next_doc = dict(doc)
                next_doc.update(update.get("$set", {}))
                self.docs[index] = next_doc
                return _Result()
        if upsert:
            doc = dict(query)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
            return _Result(upserted_id="inserted")
        return _Result()

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return _Result(deleted_count=before - len(self.docs))


def _matches(doc, query):
    return all(doc.get(key) == value for key, value in query.items())


@pytest.mark.asyncio
async def test_get_sessions_filters_by_company(monkeypatch):
    monkeypatch.setattr(session_routes, "artifacts_collection", _Collection())
    monkeypatch.setattr(session_routes, "approvals_collection", _Collection())
    monkeypatch.setattr(
        session_routes,
        "sessions_collection",
        _Collection(
            [
                {"sessionId": "session-1", "email": "user@example.com", "companyId": "company-1", "prompt": "Company one", "createdAt": "2026-06-19T10:00:00Z"},
                {"sessionId": "session-2", "email": "user@example.com", "companyId": "company-2", "prompt": "Company two", "createdAt": "2026-06-19T11:00:00Z"},
                {"sessionId": "session-3", "email": "other@example.com", "companyId": "company-1", "prompt": "Other user", "createdAt": "2026-06-19T12:00:00Z"},
            ]
        ),
    )

    result = await session_routes.get_sessions(email="user@example.com", companyId="company-1")

    assert [item["sessionId"] for item in result["sessions"]] == ["session-1"]
    assert result["sessions"][0]["companyId"] == "company-1"
    assert result["sessions"][0]["actionCount"] == 0
    assert result["sessions"][0]["hasBrowserActivity"] is False


@pytest.mark.asyncio
async def test_get_sessions_exposes_runtime_summary(monkeypatch):
    monkeypatch.setattr(
        session_routes,
        "artifacts_collection",
        _Collection(
            [
                {"artifactId": "artifact-1", "sessionId": "session-1", "email": "user@example.com"},
                {"artifactId": "artifact-2", "sessionId": "session-1", "email": "user@example.com"},
            ]
        ),
    )
    monkeypatch.setattr(
        session_routes,
        "approvals_collection",
        _Collection(
            [
                {"approvalId": "approval-1", "sessionId": "session-1", "email": "user@example.com", "status": "pending"},
            ]
        ),
    )
    monkeypatch.setattr(
        session_routes,
        "sessions_collection",
        _Collection(
            [
                {
                    "sessionId": "session-1",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "prompt": "Review claim status",
                    "initialUrl": "https://erp.example.com/claims/1",
                    "lastUrl": "https://erp.example.com/claims/1/summary",
                    "createdAt": "2026-06-19T10:00:00Z",
                    "agentId": "agent-1",
                    "agentName": "Claims Agent",
                    "provider": "autoppia",
                    "chatHistory": [{"role": "user"}, {"role": "assistant"}],
                    "actionHistory": [
                        {"action": "browser.navigate", "emittedAt": "2026-06-19T10:01:00Z", "elapsedSeconds": 1.25, "traceId": "trace-browser"},
                        {"action": "imap.search_emails", "emittedAt": "2026-06-19T10:02:00Z", "elapsedSeconds": 0.75, "traceId": "trace-email"},
                    ],
                    "runtimeState": {
                        "sourceKind": "work",
                        "workItemId": "work-42",
                        "runId": "run-9",
                        "creditsSpent": 2.5,
                        "matchedSkillId": "skill-1",
                        "matchedSkillName": "Handle claim summary",
                        "pendingConnectorApproval": "smtp.send_email:0:abc",
                        "approvedConnectorToolCalls": ["smtp.send_email:0:abc"],
                    },
                }
            ]
        ),
    )

    result = await session_routes.get_sessions(email="user@example.com", companyId="company-1")

    session = result["sessions"][0]
    assert session["agentName"] == "Claims Agent"
    assert session["lastUrl"] == "https://erp.example.com/claims/1/summary"
    assert session["chatCount"] == 2
    assert session["actionCount"] == 2
    assert session["runtimeKind"] == "hybrid"
    assert session["browserActionCount"] == 1
    assert session["connectorActionCount"] == 1
    assert session["hasBrowserActivity"] is True
    assert session["hasConnectorActivity"] is True
    assert session["matchedSkillId"] == "skill-1"
    assert session["matchedSkillName"] == "Handle claim summary"
    assert session["approvedConnectorToolCalls"] == ["smtp.send_email:0:abc"]
    assert session["approvedConnectorToolCallCount"] == 1
    assert session["pendingConnectorApproval"] == "smtp.send_email:0:abc"
    assert session["artifactCount"] == 2
    assert session["pendingApprovalCount"] == 1
    assert session["sourceKind"] == "work"
    assert session["workItemId"] == "work-42"
    assert session["runId"] == "run-9"
    assert session["runtimeMetrics"]["runtimeKind"] == "hybrid"
    assert session["runtimeMetrics"]["creditsSpent"] == 2.5
    assert session["runtimeMetrics"]["durationSeconds"] == 2.0
    assert session["runtimeMetrics"]["lastStepSeconds"] == 0.75
    assert session["runtimeMetrics"]["traceIds"] == ["run-9", "work-42", "trace-browser", "trace-email"]
    assert session["traceIds"] == ["run-9", "work-42", "trace-browser", "trace-email"]
    assert session["creditsSpent"] == 2.5
    assert session["latestAction"] == "imap.search_emails"
    assert session["latestActivityLabel"] == "imap.search_emails"
    assert session["latestActivityAt"] == "2026-06-19T10:02:00Z"


@pytest.mark.asyncio
async def test_save_session_persists_company_id(monkeypatch):
    sessions = _Collection()
    monkeypatch.setattr(session_routes, "sessions_collection", sessions)

    result = await session_routes.save_session(
        session_routes.SessionSaveRequest(
            sessionId="session-1",
            email="user@example.com",
            companyId="company-1",
            prompt="Handle payroll email",
            chatHistory=[],
        )
    )

    assert result["created"] is True
    assert sessions.docs[0]["companyId"] == "company-1"


@pytest.mark.asyncio
async def test_get_session_rejects_wrong_company(monkeypatch):
    monkeypatch.setattr(
        session_routes,
        "sessions_collection",
        _Collection([{"sessionId": "session-1", "email": "user@example.com", "companyId": "company-1", "prompt": "Company one"}]),
    )

    with pytest.raises(Exception) as exc:
        await session_routes.get_session("session-1", email="user@example.com", companyId="company-2")

    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_get_session_exposes_runtime_summary(monkeypatch):
    monkeypatch.setattr(
        session_routes,
        "artifacts_collection",
        _Collection(
            [
                {"artifactId": "artifact-1", "sessionId": "session-1", "email": "user@example.com"},
                {"artifactId": "artifact-2", "sessionId": "session-1", "email": "user@example.com"},
            ]
        ),
    )
    monkeypatch.setattr(
        session_routes,
        "approvals_collection",
        _Collection(
            [
                {"approvalId": "approval-1", "sessionId": "session-1", "email": "user@example.com", "status": "pending"},
            ]
        ),
    )
    monkeypatch.setattr(
        session_routes,
        "sessions_collection",
        _Collection(
            [
                {
                    "sessionId": "session-1",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "prompt": "Review claim status",
                    "initialUrl": "https://erp.example.com/claims/1",
                    "lastUrl": "https://erp.example.com/claims/1/summary",
                    "createdAt": "2026-06-19T10:00:00Z",
                    "agentId": "agent-1",
                    "agentName": "Claims Agent",
                    "provider": "autoppia",
                    "chatHistory": [{"role": "user"}, {"role": "assistant"}],
                    "actionHistory": [
                        {"action": "browser.navigate", "emittedAt": "2026-06-19T10:01:00Z"},
                        {"action": "imap.search_emails", "emittedAt": "2026-06-19T10:02:00Z"},
                    ],
                    "runtimeState": {
                        "sourceKind": "work",
                        "workItemId": "work-42",
                        "runId": "run-9",
                        "creditsSpent": 2.5,
                        "matchedSkillId": "skill-1",
                        "matchedSkillName": "Handle claim summary",
                        "pendingConnectorApproval": "smtp.send_email:0:abc",
                        "approvedConnectorToolCalls": ["smtp.send_email:0:abc"],
                    },
                }
            ]
        ),
    )

    result = await session_routes.get_session("session-1", email="user@example.com", companyId="company-1")

    session = result["session"]
    assert session["agentName"] == "Claims Agent"
    assert session["chatCount"] == 2
    assert session["actionCount"] == 2
    assert session["runtimeKind"] == "hybrid"
    assert session["browserActionCount"] == 1
    assert session["connectorActionCount"] == 1
    assert session["hasBrowserActivity"] is True
    assert session["hasConnectorActivity"] is True
    assert session["matchedSkillId"] == "skill-1"
    assert session["matchedSkillName"] == "Handle claim summary"
    assert session["approvedConnectorToolCalls"] == ["smtp.send_email:0:abc"]
    assert session["approvedConnectorToolCallCount"] == 1
    assert session["pendingConnectorApproval"] == "smtp.send_email:0:abc"
    assert session["artifactCount"] == 2
    assert session["pendingApprovalCount"] == 1
    assert session["sourceKind"] == "work"
    assert session["workItemId"] == "work-42"
    assert session["runId"] == "run-9"
    assert session["creditsSpent"] == 2.5
    assert session["latestAction"] == "imap.search_emails"
    assert session["latestActivityLabel"] == "imap.search_emails"
    assert session["latestActivityAt"] == "2026-06-19T10:02:00Z"


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
            metadata={"skillId": "skill-1", "trajectoryId": "trajectory-1", "toolId": "tool-1", "workItemId": "work-1"},
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
    assert created["artifact"]["skillId"] == "skill-1"
    assert created["artifact"]["capabilityRefs"]["linked"] is True
    assert listed["artifacts"][0]["title"] == "Renewal report"
    assert listed["artifacts"][0]["trajectoryId"] == "trajectory-1"
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
