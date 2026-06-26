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


class _Artifacts:
    def __init__(self):
        self.docs = {}

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs.values():
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

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if all(_nested(doc, key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs[doc["artifactId"]] = dict(doc)

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if not doc:
            return
        stored = self.docs[doc["artifactId"]]
        stored.update(update.get("$set", {}))


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


class _Tools:
    def __init__(self):
        self.docs = [
            {"toolId": "tool-1", "name": "crm.lookup"},
            {"toolId": "tool-2", "name": "email.reply"},
        ]

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                actual = doc.get(key)
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


@pytest.mark.asyncio
async def test_create_and_list_work_items(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    approvals = _Approvals()
    sessions = _Sessions()
    artifacts = _Artifacts()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)

    created = await work_items.create_work_item(
        WorkItemCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Check invoices",
            prompt="Review overdue invoices",
            agentId="agent-1",
            runTarget="selected",
            maxCreditsPerRun=1.25,
            allowedDomains=["https://portal.example.com/cases", "portal.example.com"],
        )
    )
    listed = await work_items.list_work_items("user@example.com", "company-1", created["workItem"]["boardId"])

    assert created["success"] is True
    assert created["workItem"]["status"] == "TODO"
    assert created["workItem"]["boardId"]
    assert listed["workItems"][0]["title"] == "Check invoices"
    assert listed["workItems"][0]["maxCreditsPerRun"] == 1.25
    assert listed["workItems"][0]["runTarget"] == "selected"
    assert listed["workItems"][0]["allowedDomains"] == ["portal.example.com"]
    assert listed["workItems"][0]["browserRestrictedByDomain"] is True
    assert listed["workItems"][0]["browserDefaultUse"] == "exception"

    approvals.docs.append(
        {
            "approvalId": "approval-1",
            "title": "Approve work send",
            "status": "pending",
            "action_url": "/approvals?workItemId=work-1",
            "metadata": {"workItemId": created["workItem"]["workItemId"], "sourceKind": "work"},
        }
    )
    listed_with_approval = await work_items.list_work_items("user@example.com", "company-1", created["workItem"]["boardId"])
    approval_contract = listed_with_approval["workItems"][0]["operational"]["orchestration"]["approval"]
    assert approval_contract["pendingApprovalIds"] == ["approval-1"]
    assert approval_contract["pendingApprovals"][0]["actionUrl"] == "/approvals?workItemId=work-1"


@pytest.mark.asyncio
async def test_run_work_item_records_report_and_judge(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    collection = _WorkItems()
    boards = _Boards()
    agents = _Agents()
    approvals = _Approvals()
    sessions = _Sessions()
    artifacts = _Artifacts()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "agents_collection", agents)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)

    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return kwargs

    async def fake_agent_step_result(agent_id, payload):
        return {
            "done": True,
            "content": "Completed task",
            "tool_calls": [],
            "artifacts": [{"artifactType": "markdown", "title": "Draft reply", "content": "Hello client"}],
            "state_out": {"memory": {"ok": True}},
        }

    jobs = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    async def fake_run_credits_spent(run_id):
        return 0.42

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
    persisted_artifacts = await artifacts.find({"metadata.workItemId": work_item_id}).to_list()

    assert started["workItem"]["status"] == "RUNNING"
    assert started["sessionId"]
    assert refreshed["status"] == "DONE"
    assert refreshed["judge"]["label"] == "success"
    assert refreshed["report"]["results"][0]["agentId"] == "agent-1"
    assert refreshed["runHistory"][0]["runId"] == started["runId"]
    assert refreshed["runHistory"][0]["sessionId"] == started["sessionId"]
    assert refreshed["report"]["sessionId"] == started["sessionId"]
    assert refreshed["report"]["creditsSpent"] == 0.42
    assert session_doc["provider"] == "work_orchestration"
    assert session_doc["runtimeState"]["runId"] == started["runId"]
    assert session_doc["runtimeState"]["creditsSpent"] == 0.42
    assert len(persisted_artifacts) == 1
    assert persisted_artifacts[0]["sessionId"] == started["sessionId"]
    assert [item["title"] for item in notifications] == ["Work item started", "Work item done"]
    assert notifications[0]["metadata"]["workItemId"] == work_item_id
    assert notifications[0]["metadata"]["sessionId"] == started["sessionId"]
    assert notifications[0]["metadata"]["sourceKind"] == "work"
    assert notifications[1]["metadata"]["workItemId"] == work_item_id
    assert notifications[1]["metadata"]["sessionId"] == started["sessionId"]
    assert notifications[1]["metadata"]["sourceKind"] == "work"
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
    artifacts = _Artifacts()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "agents_collection", agents)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)

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
    artifacts = _Artifacts()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)

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
    artifacts = _Artifacts()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", sessions)
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)

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
    artifacts = _Artifacts()
    artifacts.docs["artifact-1"] = {
        "artifactId": "artifact-1",
        "sessionId": "session-1",
        "metadata": {"workItemId": "work-1"},
    }
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", boards)
    monkeypatch.setattr(work_items, "approvals_collection", approvals)
    monkeypatch.setattr(work_items, "sessions_collection", _Sessions())
    monkeypatch.setattr(work_items, "artifacts_collection", artifacts)
    monkeypatch.setattr(work_items, "tools_collection", _Tools())

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
            "creditsSpent": 0.42,
            "resultCount": 1,
            "results": [
                {
                    "agentId": "agent-1",
                    "status": "ok",
                    "steps": [{"toolCalls": [{"name": "crm.lookup"}]}],
                    "result": {
                        "artifacts": [{"artifactType": "markdown"}],
                        "state_out": {"matchedSkillId": "skill-1", "matchedSkillName": "Resolve claim"},
                        "capability_match": {"skillId": "skill-1", "trajectoryId": "trajectory-1"},
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
    assert operational["latestMatchedTrajectoryIds"] == ["trajectory-1"]
    assert operational["latestToolNames"] == ["crm.lookup"]
    assert operational["latestToolIds"] == ["tool-1"]
    assert operational["latestCreditsSpent"] == 0.42
    assert operational["persistedArtifactCount"] == 1
    assert operational["reviewBlocked"] is True
    assert operational["orchestration"]["queueState"] == "REVIEW"
    assert operational["orchestration"]["budget"]["maxBudgetCredits"] == 1.0
    assert operational["orchestration"]["budget"]["latestCreditsSpent"] == 0.42
    assert operational["orchestration"]["budget"]["remainingCredits"] == 0.58
    assert operational["orchestration"]["retry"]["runAttempts"] == 1
    assert operational["orchestration"]["retry"]["maxSteps"] == 4
    assert operational["orchestration"]["approval"]["reviewBlocked"] is True
    assert operational["orchestration"]["sla"]["state"] == "blocked"
    assert operational["orchestration"]["sla"]["deadlineState"] == "manual"
    assert operational["orchestration"]["sla"]["needsAttention"] is True
    assert operational["orchestration"]["automationGate"]["state"] == "blocked"
    assert operational["orchestration"]["automationGate"]["canRunUnattended"] is False
    assert operational["orchestration"]["automationGate"]["blockers"] == ["pending_approval"]
    assert operational["orchestration"]["automationGate"]["policy"]["maxSteps"] == 4
    assert operational["orchestration"]["auditTrail"]["uniform"] is True
    assert operational["orchestration"]["auditTrail"]["hasApprovalCheckpoint"] is True
    assert operational["orchestration"]["auditTrail"]["hasBudgetCheckpoint"] is True
    assert operational["orchestration"]["auditTrail"]["eventCount"] == 3
    assert [event["event"] for event in operational["orchestration"]["auditTrail"]["events"]] == [
        "work.queued",
        "work.budget",
        "work.approval_block",
    ]


@pytest.mark.asyncio
async def test_list_work_items_marks_overdue_scheduled_sla(monkeypatch):
    collection = _WorkItems()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", _Boards())
    monkeypatch.setattr(work_items, "approvals_collection", _Approvals())
    monkeypatch.setattr(work_items, "sessions_collection", _Sessions())
    monkeypatch.setattr(work_items, "artifacts_collection", _Artifacts())
    monkeypatch.setattr(work_items, "tools_collection", _Tools())

    collection.docs["work-overdue"] = {
        "workItemId": "work-overdue",
        "email": "user@example.com",
        "companyId": "company-1",
        "boardId": "board-1",
        "title": "Overdue scheduled work",
        "prompt": "Run the scheduled job",
        "runTarget": "all",
        "browserEnabled": False,
        "browserMode": "headless",
        "maxCreditsPerRun": 1.0,
        "maxBudgetCredits": 5.0,
        "maxSteps": 4,
        "triggerType": "scheduled",
        "scheduleFrequency": "daily",
        "scheduleTime": "09:00",
        "scheduleDayOfWeek": 1,
        "nextRunAt": "2000-01-01T00:00:00+00:00",
        "judgeImplementation": "llm",
        "status": "TODO",
        "report": {"creditsSpent": 0.25, "results": []},
        "runHistory": [],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }

    listed = await work_items.list_work_items(
        "user@example.com",
        "company-1",
        "board-1",
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    orchestration = listed["workItems"][0]["operational"]["orchestration"]
    assert orchestration["schedule"]["deadlineState"] == "overdue"
    assert orchestration["sla"]["state"] == "overdue"
    assert orchestration["sla"]["dueAt"] == "2000-01-01T00:00:00+00:00"
    assert orchestration["sla"]["overdueMinutes"] > 0
    assert orchestration["sla"]["needsAttention"] is True
    assert orchestration["automationGate"]["state"] == "scheduled"
    assert orchestration["automationGate"]["canRunUnattended"] is True
    assert orchestration["automationGate"]["nextActions"] == ["Scheduled work is overdue; confirm the worker is healthy or run it manually."]
    assert orchestration["auditTrail"]["hasScheduleCheckpoint"] is True
    assert [event["event"] for event in orchestration["auditTrail"]["events"]] == [
        "work.queued",
        "work.scheduled",
        "work.budget",
    ]


@pytest.mark.asyncio
async def test_scheduled_browser_work_requires_domain_allowlist_for_unattended_gate(monkeypatch):
    collection = _WorkItems()
    monkeypatch.setattr(work_items, "work_items_collection", collection)
    monkeypatch.setattr(work_items, "work_boards_collection", _Boards())
    monkeypatch.setattr(work_items, "approvals_collection", _Approvals())
    monkeypatch.setattr(work_items, "sessions_collection", _Sessions())
    monkeypatch.setattr(work_items, "artifacts_collection", _Artifacts())
    monkeypatch.setattr(work_items, "tools_collection", _Tools())

    collection.docs["work-browser"] = {
        "workItemId": "work-browser",
        "email": "user@example.com",
        "companyId": "company-1",
        "boardId": "board-1",
        "title": "Browser scheduled work",
        "prompt": "Use the browser",
        "runTarget": "selected",
        "agentId": "agent-1",
        "browserEnabled": True,
        "browserMode": "headless",
        "allowedDomains": [],
        "browserRestrictedByDomain": False,
        "browserDefaultUse": "exception",
        "maxCreditsPerRun": 1.0,
        "maxBudgetCredits": 5.0,
        "maxSteps": 4,
        "triggerType": "scheduled",
        "scheduleFrequency": "daily",
        "scheduleTime": "09:00",
        "scheduleDayOfWeek": 1,
        "nextRunAt": "2999-01-01T00:00:00+00:00",
        "judgeImplementation": "llm",
        "status": "TODO",
        "report": {"creditsSpent": 0.0, "results": []},
        "runHistory": [],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }

    listed = await work_items.list_work_items(
        "user@example.com",
        "company-1",
        "board-1",
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    orchestration = listed["workItems"][0]["operational"]["orchestration"]
    assert orchestration["browserPolicy"]["state"] == "unrestricted"
    assert orchestration["browserPolicy"]["defaultUse"] == "exception"
    assert orchestration["browserPolicy"]["allowedDomains"] == []
    assert orchestration["automationGate"]["state"] == "blocked"
    assert orchestration["automationGate"]["canRunUnattended"] is False
    assert orchestration["automationGate"]["blockers"] == ["missing_browser_allowlist"]
    assert orchestration["automationGate"]["policy"]["requiresBrowserAllowlist"] is True
    assert orchestration["auditTrail"]["hasBrowserPolicyCheckpoint"] is True
    assert orchestration["auditTrail"]["events"][-1]["event"] == "work.browser_policy"
