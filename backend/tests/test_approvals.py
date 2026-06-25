import pytest

from app.request_scope import RequestScope
from app.routes import approvals as approvals_route
from app.routes.approvals import ApprovalDecisionRequest
from app.services import approvals


class _Result:
    def __init__(self, modified_count=0):
        self.modified_count = modified_count


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def sort(self, field, direction):
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return self.docs[:length] if length else self.docs


def _matches(doc, query):
    for key, value in query.items():
        current = doc
        for part in key.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current != value:
            return False
    return True


class _Collection:
    def __init__(self, id_key="approvalId"):
        self.docs = {}
        self.id_key = id_key

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs.values() if _matches(doc, query)])

    async def insert_one(self, doc):
        self.docs[doc[self.id_key]] = dict(doc)

    async def update_one(self, query, update):
        for doc_id, doc in self.docs.items():
            if _matches(doc, query):
                self.docs[doc_id].update(update.get("$set", {}))
                return _Result(modified_count=1)
        return _Result()


@pytest.mark.asyncio
async def test_create_list_and_approve_approval(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(approvals, "approvals_collection", collection)
    monkeypatch.setattr(approvals_route, "approvals_collection", collection)
    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return {"notificationId": "notification-1"}

    async def fake_record_runtime_event(**kwargs):
        return {}

    monkeypatch.setattr(approvals, "create_notification", fake_create_notification)
    monkeypatch.setattr(approvals, "record_runtime_event", fake_record_runtime_event)

    created = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="telegram.send_message:0:abc",
        title="Approve send",
        message="Confirm send.",
        proposed_action={"name": "telegram.send_message", "arguments": {"message": "Hello"}},
    )
    default_listed = await approvals_route.list_approvals(
        email="user@example.com",
        companyId="company-1",
        status="pending",
        scope=RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    listed = await approvals_route.list_approvals(
        email="user@example.com",
        companyId="company-1",
        status="pending",
        includeRuntime=True,
        scope=RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    approved = await approvals_route.approve_approval(
        created["approvalId"],
        ApprovalDecisionRequest(email="user@example.com"),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert default_listed["approvals"] == []
    assert listed["approvals"][0]["approvalId"] == created["approvalId"]
    assert listed["approvals"][0]["toolName"] == "telegram.send_message"
    assert listed["approvals"][0]["sourceKind"] == "runtime"
    assert listed["approvals"][0]["auditTrail"][0]["event"] == "requested"
    assert notifications[0]["action_url"] == "/approvals?status=pending"
    assert notifications[0]["metadata"]["approvalId"] == created["approvalId"]
    assert notifications[0]["metadata"]["approvalKey"] == created["approvalKey"]
    assert notifications[0]["metadata"]["sourceKind"] == "runtime"
    assert approved["approval"]["status"] == "approved"
    assert approved["approval"]["auditTrail"][-1]["event"] == "approved"
    assert approved["statePatch"] == {"approvedConnectorToolCalls": ["telegram.send_message:0:abc"]}
    assert approved["sessionResume"]["required"] is False


@pytest.mark.asyncio
async def test_pending_approval_idempotency_is_scoped_to_session(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(approvals, "approvals_collection", collection)
    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return {"notificationId": "notification-1"}

    async def fake_record_runtime_event(**kwargs):
        return {}

    monkeypatch.setattr(approvals, "create_notification", fake_create_notification)
    monkeypatch.setattr(approvals, "record_runtime_event", fake_record_runtime_event)

    first = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="smtp.send_email:0:abc",
        title="Approve send",
        message="Confirm send.",
        proposed_action={"name": "smtp.send_email", "arguments": {"to": "client@example.com"}},
        metadata={"sessionId": "session-1", "sourceKind": "session"},
    )
    same_session = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="smtp.send_email:0:abc",
        title="Approve send",
        message="Confirm send.",
        proposed_action={"name": "smtp.send_email", "arguments": {"to": "client@example.com"}},
        metadata={"sessionId": "session-1", "sourceKind": "session"},
    )
    second_session = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="smtp.send_email:0:abc",
        title="Approve send",
        message="Confirm send.",
        proposed_action={"name": "smtp.send_email", "arguments": {"to": "client@example.com"}},
        metadata={"sessionId": "session-2", "sourceKind": "session"},
    )

    assert same_session["approvalId"] == first["approvalId"]
    assert second_session["approvalId"] != first["approvalId"]
    assert len(collection.docs) == 2
    assert notifications[0]["action_url"] == "/approvals?status=pending&sessionId=session-1"
    assert notifications[1]["action_url"] == "/approvals?status=pending&sessionId=session-2"


@pytest.mark.asyncio
async def test_approving_session_approval_returns_resume_contract(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(approvals, "approvals_collection", collection)
    monkeypatch.setattr(approvals_route, "approvals_collection", collection)
    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return {}

    async def fake_record_runtime_event(**kwargs):
        return {}

    monkeypatch.setattr(approvals, "create_notification", fake_create_notification)
    monkeypatch.setattr(approvals, "record_runtime_event", fake_record_runtime_event)

    created = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="smtp.send_email:0:abc",
        title="Approve send",
        message="Confirm send.",
        proposed_action={"name": "smtp.send_email", "arguments": {"to": "client@example.com"}},
        metadata={
            "sessionId": "session-1",
            "sourceKind": "session",
            "statePatch": {"approvedConnectorToolCalls": ["smtp.send_email:0:abc"]},
        },
    )

    approved = await approvals_route.approve_approval(
        created["approvalId"],
        ApprovalDecisionRequest(email="user@example.com"),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )

    assert approved["resume"] == {"started": False}
    assert approved["sessionResume"]["required"] is True
    assert approved["sessionResume"]["sessionId"] == "session-1"
    assert approved["sessionResume"]["socketEvent"] == "continue-task"
    assert approved["sessionResume"]["runtimeStatePatch"]["approvedConnectorToolCalls"] == ["smtp.send_email:0:abc"]
    assert notifications[0]["metadata"]["sessionId"] == "session-1"
    assert notifications[0]["metadata"]["sourceKind"] == "session"
    assert notifications[0]["action_url"] == "/approvals?status=pending&sessionId=session-1"


@pytest.mark.asyncio
async def test_approving_work_item_approval_restarts_work_item(monkeypatch):
    approvals_collection = _Collection()
    work_collection = _Collection(id_key="workItemId")
    monkeypatch.setattr(approvals, "approvals_collection", approvals_collection)
    monkeypatch.setattr(approvals_route, "approvals_collection", approvals_collection)
    monkeypatch.setattr(approvals_route, "work_items_collection", work_collection)
    notifications = []

    async def fake_create_notification(**kwargs):
        notifications.append(kwargs)
        return {}

    async def fake_record_runtime_event(**kwargs):
        return {}

    monkeypatch.setattr(approvals, "create_notification", fake_create_notification)
    monkeypatch.setattr(approvals, "record_runtime_event", fake_record_runtime_event)

    created = await approvals.create_pending_approval(
        email="user@example.com",
        company_id="company-1",
        agent_id="agent-1",
        approval_key="crm.update:0:abc",
        title="Approve update",
        message="Confirm update.",
        proposed_action={"name": "crm.update", "arguments": {"id": "1"}},
        metadata={
            "workItemId": "work-1",
            "statePatch": {
                "automata_trajectory_progress": {
                    "traj-1": {"index": 0, "approvalPending": False, "approvedActions": ["traj-1:0"]}
                }
            },
        },
    )
    await work_collection.insert_one(
        {
            "workItemId": "work-1",
            "email": "user@example.com",
            "companyId": "company-1",
            "status": "REVIEW",
            "pendingApproval": {"approvalId": created["approvalId"], "approvalKey": created["approvalKey"], "agentId": "agent-1"},
        }
    )

    jobs = []

    async def fake_enqueue_job(job_type, payload, **kwargs):
        jobs.append((job_type, payload, kwargs))
        return {"jobId": "job-1", "type": job_type, "payload": payload}

    monkeypatch.setattr(approvals_route, "enqueue_job", fake_enqueue_job)

    approved = await approvals_route.approve_approval(
        created["approvalId"],
        ApprovalDecisionRequest(email="user@example.com"),
        RequestScope(email="user@example.com", token_email="user@example.com"),
    )
    refreshed = await work_collection.find_one({"workItemId": "work-1"})

    assert approved["resume"]["started"] is True
    assert approved["statePatch"]["automata_trajectory_progress"]["traj-1"]["approvedActions"] == ["traj-1:0"]
    assert refreshed["status"] == "RUNNING"
    assert refreshed["pendingApproval"]["status"] == "approved"
    assert refreshed["pendingApproval"]["statePatch"]["automata_trajectory_progress"]["traj-1"]["approvalPending"] is False
    assert jobs[0][0] == "work_run"
    assert jobs[0][1]["workItemId"] == "work-1"
    assert notifications[0]["metadata"]["workItemId"] == "work-1"
    assert notifications[0]["metadata"]["sourceKind"] == "work"
    assert notifications[0]["action_url"] == "/approvals?status=pending&workItemId=work-1"


def test_stable_approval_key_is_deterministic_and_redacted():
    first = approvals.stable_approval_key("gmail.send_email", 0, {"body": "Hi", "token": "secret"})
    second = approvals.stable_approval_key("gmail.send_email", 0, {"token": "secret", "body": "Hi"})

    assert first == second
    assert first.startswith("gmail.send_email:0:")
