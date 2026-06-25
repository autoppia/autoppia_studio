import pytest

from app.routes import work_items
from app.routes.work_items import WorkItemCreateRequest, WorkItemRunRequest
from app.request_scope import RequestScope


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs[:length] if length else self.docs)


class _Result:
    def __init__(self, deleted_count=0):
        self.deleted_count = deleted_count


class _WorkItems:
    def __init__(self):
        self.docs = {}

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                docs.append(dict(doc))
        return _Cursor(docs)

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs[doc["workItemId"]] = dict(doc)

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if not doc:
            return
        stored = self.docs[doc["workItemId"]]
        stored.update(update.get("$set", {}))
        for key, value in update.get("$push", {}).items():
            stored.setdefault(key, []).append(value)

    async def find_one_and_update(self, query, update, projection=None, sort=None, return_document=None):
        def match_value(actual, expected):
            if isinstance(expected, dict):
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                if "$lte" in expected and not (actual <= expected["$lte"]):
                    return False
                return True
            return actual == expected

        matches = [
            doc for doc in self.docs.values()
            if all(match_value(doc.get(key), value) for key, value in query.items())
        ]
        matches.sort(key=lambda item: (item.get("nextRunAt", ""), item.get("createdAt", "")))
        if not matches:
            return None
        stored = self.docs[matches[0]["workItemId"]]
        stored.update(update.get("$set", {}))
        return dict(stored)

    async def delete_one(self, query):
        doc = await self.find_one(query)
        if not doc:
            return _Result(0)
        del self.docs[doc["workItemId"]]
        return _Result(1)


class _Boards(_WorkItems):
    async def insert_one(self, doc):
        self.docs[doc["boardId"]] = dict(doc)


def _nested(doc, path):
    current = doc
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


class _Approvals:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                actual = _nested(doc, key)
                if isinstance(value, dict) and "$in" in value:
                    if actual not in value["$in"]:
                        matched = False
                        break
                elif actual != value:
                    matched = False
                    break
            if matched:
                docs.append(dict(doc))
        return _Cursor(docs)


class _Sessions:
    def __init__(self):
        self.docs = {}

    async def update_one(self, query, update, upsert=False):
        session_id = query.get("sessionId", "")
        existing = dict(self.docs.get(session_id, {"sessionId": session_id}))
        existing.update(update.get("$setOnInsert", {}))
        existing.update(update.get("$set", {}))
        self.docs[session_id] = existing

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


class _Agents:
    def __init__(self):
        self.docs = [
            {
                "agentId": "agent-1",
                "email": "user@example.com",
                "companyId": "company-1",
                "name": "Agent One",
                "websiteUrl": "https://example.com",
            }
        ]

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                docs.append(dict(doc))
        return _Cursor(docs)

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


@pytest.mark.asyncio
async def test_create_and_list_work_items(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    approvals = _Approvals()
    sessions = _Sessions()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Check invoices",
            prompt="Review overdue invoices",
            agentId="agent-1",
            runTarget="selected",
            maxCreditsPerRun=1.25,
        )
    )
    listed = await work_items.list_work_items("user@example.com", "company-1", created["workItem"]["boardId"])

    assert created["success"] is True
    assert created["workItem"]["status"] == "TODO"
    assert created["workItem"]["boardId"]
    assert listed["workItems"][0]["title"] == "Check invoices"
    assert listed["workItems"][0]["maxCreditsPerRun"] == 1.25
    assert listed["workItems"][0]["runTarget"] == "selected"


@pytest.mark.asyncio
async def test_run_work_item_records_report_and_judge(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    agents = _Agents()
    approvals = _Approvals()
    sessions = _Sessions()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "agents_collection", agents)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)

    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return kwargs

    async def fake_agent_step_result(agent_id, payload):
        return {
            "done": True,
            "content": "Completed task",
            "tool_calls": [],
            "state_out": {"memory": {"ok": True}},
        }

    jobs = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    async def fake_run_credits_spent(run_id):
        return 0.0

    monkeypatch.setattr(work_items, "agent_step_result", fake_agent_step_result)
    monkeypatch.setattr(work_items, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(work_items, "create_notification", fake_create_notification)
    monkeypatch.setattr(work_items, "run_credits_spent", fake_run_credits_spent)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Run task",
            prompt="Do the work",
            agentId="agent-1",
            runTarget="selected",
            browserEnabled=False,
            judgeImplementation="deterministic_runtime_result",
        )
    )
    work_item_id = created["workItem"]["workItemId"]
    started = await work_items.run_work_item(
        work_item_id,
        WorkItemRunRequest(),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    await work_items._run_work_item(work_item_id, started["runId"])
    refreshed = await collection.find_one({"workItemId": work_item_id})
    session_doc = await sessions.find_one({"sessionId": started["sessionId"]})

    assert started["workItem"]["status"] == "RUNNING"
    assert started["sessionId"]
    assert refreshed["status"] == "DONE"
    assert refreshed["judge"]["label"] == "success"
    assert refreshed["report"]["results"][0]["agentId"] == "agent-1"
    assert refreshed["runHistory"][0]["runId"] == started["runId"]
    assert refreshed["runHistory"][0]["sessionId"] == started["sessionId"]
    assert refreshed["report"]["sessionId"] == started["sessionId"]
    assert session_doc["provider"] == "work_orchestration"
    assert session_doc["runtimeState"]["runId"] == started["runId"]
    assert [item["title"] for item in notifications] == ["Work item started", "Work item done"]
    assert jobs[0][0] == "work_run"


@pytest.mark.asyncio
async def test_run_agent_work_steps_stops_when_budget_exhausted(monkeypatch):
    called = False

    async def fake_agent_step_result(agent_id, payload):
        nonlocal called
        called = True
        return {"done": True, "content": "should not run", "tool_calls": []}

    async def fake_run_credits_spent(run_id):
        return 1.0

    monkeypatch.setattr(work_items, "agent_step_result", fake_agent_step_result)
    monkeypatch.setattr(work_items, "run_credits_spent", fake_run_credits_spent)

    result = await work_items._run_agent_work_steps(
        {
            "prompt": "Do work",
            "browserEnabled": False,
            "maxSteps": 3,
            "maxBudgetCredits": 1.0,
            "maxCreditsPerRun": 1.0,
            "workItemId": "work-1",
        },
        {"agentId": "agent-1", "name": "Agent One", "websiteUrl": "https://example.com"},
        "run-1",
    )

    assert called is False
    assert result["status"] == "budget_exhausted"
    assert result["creditsSpent"] == 1.0
    assert result["stepCount"] == 0


@pytest.mark.asyncio
async def test_run_work_item_pauses_on_human_approval(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    agents = _Agents()
    approvals = _Approvals()
    sessions = _Sessions()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "agents_collection", agents)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)

    async def fake_create_notification(**kwargs):
        return kwargs

    async def fake_agent_step_result(agent_id, payload):
        return {
            "done": False,
            "content": None,
            "reasoning": "Approval required",
            "tool_calls": [
                {
                    "name": "api.human_approval",
                    "arguments": {
                        "approvalId": "approval-1",
                        "approvalKey": "crm.update:0:abc",
                        "proposedAction": {"name": "crm.update", "arguments": {"id": "1"}},
                    },
                }
            ],
            "state_out": {"pendingConnectorApproval": "crm.update:0:abc"},
        }

    jobs = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    async def fake_run_credits_spent(run_id):
        return 0.0

    monkeypatch.setattr(work_items, "agent_step_result", fake_agent_step_result)
    monkeypatch.setattr(work_items, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(work_items, "create_notification", fake_create_notification)
    monkeypatch.setattr(work_items, "run_credits_spent", fake_run_credits_spent)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Approval task",
            prompt="Update CRM",
            agentId="agent-1",
            runTarget="selected",
            browserEnabled=False,
        )
    )
    work_item_id = created["workItem"]["workItemId"]
    started = await work_items.run_work_item(
        work_item_id,
        WorkItemRunRequest(),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    await work_items._run_work_item(work_item_id, started["runId"])
    refreshed = await collection.find_one({"workItemId": work_item_id})

    assert refreshed["status"] == "REVIEW"
    assert refreshed["pendingApproval"]["approvalId"] == "approval-1"
    assert refreshed["pendingApproval"]["approvalKey"] == "crm.update:0:abc"
    assert refreshed["runHistory"][0]["status"] == "WAITING_APPROVAL"
    assert started["runId"] == refreshed["pendingApproval"]["runId"]
    assert jobs[0][0] == "work_run"


@pytest.mark.asyncio
async def test_scheduled_work_item_gets_next_run(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    approvals = _Approvals()
    sessions = _Sessions()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Daily check",
            prompt="Run daily",
            runTarget="all",
            triggerType="scheduled",
            scheduleFrequency="daily",
            scheduleTime="09:30",
        )
    )

    assert created["workItem"]["runTarget"] == "all"
    assert created["workItem"]["triggerType"] == "scheduled"
    assert created["workItem"]["nextRunAt"]


@pytest.mark.asyncio
async def test_due_scheduled_work_claims_atomically(monkeypatch):
    collection = _WorkItems()
    boards = _Boards()
    approvals = _Approvals()
    sessions = _Sessions()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Due work",
            prompt="Run due",
            runTarget="all",
            triggerType="scheduled",
            scheduleFrequency="daily",
        )
    )
    work_item_id = created["workItem"]["workItemId"]
    collection.docs[work_item_id]["nextRunAt"] = "2000-01-01T00:00:00+00:00"
    jobs = []
    notifications = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    async def fake_run_work_item(work_item_id, run_id):
        return None

    async def fake_notify(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(work_items, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(work_items, "_run_work_item", fake_run_work_item)
    monkeypatch.setattr(work_items, "_notify_work_item", fake_notify)

    started = await work_items.run_due_scheduled_work_items_once()

    assert started == 1
    assert collection.docs[work_item_id]["status"] == "RUNNING"
    assert collection.docs[work_item_id]["lastRunId"]
    assert len(jobs) == 1
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_list_work_items_includes_operational_summary(monkeypatch):
    collection = _WorkItems()
    boards = _Boards()
    approvals = _Approvals([
        {
            "approvalId": "approval-1",
            "status": "pending",
            "metadata": {"workItemId": "work-1"},
        },
        {
            "approvalId": "approval-2",
            "status": "approved",
            "metadata": {"workItemId": "work-1"},
        },
    ])
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", _Sessions())

    collection.docs["work-1"] = {
        "workItemId": "work-1",
        "email": "user@example.com",
        "companyId": "company-1",
        "boardId": "board-1",
        "title": "Operational summary",
        "prompt": "Run a skill-backed task",
        "runTarget": "selected",
        "browserEnabled": False,
        "browserMode": "headless",
        "maxCreditsPerRun": 1.0,
        "maxBudgetCredits": 1.0,
        "maxSteps": 4,
        "triggerType": "manual",
        "scheduleFrequency": "none",
        "scheduleTime": "09:00",
        "scheduleDayOfWeek": 1,
        "judgeImplementation": "llm",
        "status": "REVIEW",
        "pendingApproval": {"approvalId": "approval-1"},
        "report": {
            "runId": "run-1",
            "resultCount": 1,
            "results": [
                {
                    "agentId": "agent-1",
                    "status": "ok",
                    "steps": [{"toolCalls": [{"name": "crm.lookup"}]}],
                    "result": {
                        "artifacts": [{"artifactType": "markdown"}],
                        "state_out": {"matchedSkillId": "skill-1", "matchedSkillName": "Resolve claim"},
                    },
                }
            ],
        },
        "runHistory": [{"runId": "run-1", "status": "WAITING_APPROVAL"}],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }

    listed = await work_items.list_work_items(
        "user@example.com",
        "company-1",
        "board-1",
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    operational = listed["workItems"][0]["operational"]
    assert operational["approvalCount"] == 2
    assert operational["pendingApprovalCount"] == 1
    assert operational["latestArtifactCount"] == 1
    assert operational["latestToolCallCount"] == 1
    assert operational["latestMatchedSkillIds"] == ["skill-1"]
    assert operational["latestMatchedSkillNames"] == ["Resolve claim"]
    assert operational["reviewBlocked"] is True
