import pytest

from app.routes import notifications
from app.routes.notifications import NotificationCreateRequest


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs[:length] if length else self.docs)


class _Result:
    def __init__(self, matched_count=0, modified_count=0, deleted_count=0):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.deleted_count = deleted_count


def _matches(doc, query):
    for key, value in query.items():
        current = doc.get(key)
        if isinstance(value, dict):
            if "$in" in value and current not in value["$in"]:
                return False
            if "$ne" in value and current == value["$ne"]:
                return False
            if "$lte" in value and not (current <= value["$lte"]):
                return False
            if "$gt" in value and not (current > value["$gt"]):
                return False
            continue
        if current != value:
            return False
    return True


class _Collection:
    def __init__(self, docs=None, id_key="notificationId"):
        self.docs = {doc[id_key]: dict(doc) for doc in docs or []}
        self.id_key = id_key

    def find(self, query, projection=None):
        return _Cursor([dict(doc) for doc in self.docs.values() if _matches(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if _matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs[doc[self.id_key]] = dict(doc)

    async def update_one(self, query, update):
        for key, doc in self.docs.items():
            if _matches(doc, query):
                self.docs[key].update(update.get("$set", {}))
                return _Result(matched_count=1, modified_count=1)
        return _Result()

    async def update_many(self, query, update):
        modified = 0
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                self.docs[key].update(update.get("$set", {}))
                modified += 1
        return _Result(matched_count=modified, modified_count=modified)

    async def count_documents(self, query):
        return len([doc for doc in self.docs.values() if _matches(doc, query)])

    async def delete_one(self, query):
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                del self.docs[key]
                return _Result(deleted_count=1)
        return _Result()

    async def delete_many(self, query):
        deleted = 0
        for key, doc in list(self.docs.items()):
            if _matches(doc, query):
                del self.docs[key]
                deleted += 1
        return _Result(deleted_count=deleted)


@pytest.mark.asyncio
async def test_create_list_and_mark_notification_read(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(notifications, "notifications_collection", collection)

    created = await notifications.create_notification_route(
        NotificationCreateRequest(
            email="user@example.com",
            companyId="company-1",
            title="Work item done",
            message="The run succeeded.",
            level="success",
            source="work",
            entityType="work_item",
            entityId="work-1",
        )
    )
    listed = await notifications.list_notifications("user@example.com", "company-1")
    marked = await notifications.mark_notification_read(created["notification"]["notificationId"])
    listed_after = await notifications.list_notifications("user@example.com", "company-1")

    assert created["success"] is True
    assert listed["unreadCount"] == 1
    assert listed["notifications"][0]["title"] == "Work item done"
    assert marked["notification"]["read"] is True
    assert listed_after["unreadCount"] == 0


@pytest.mark.asyncio
async def test_activity_summary_counts_work_and_unread_notifications(monkeypatch):
    notifications_collection = _Collection(
        [
            {
                "notificationId": "notification-1",
                "email": "user@example.com",
                "companyId": "company-1",
                "title": "Running",
                "read": False,
                "createdAt": "2026-06-03T10:00:00+00:00",
            }
        ]
    )
    work_collection = _Collection(
        [
            {
                "workItemId": "work-1",
                "email": "user@example.com",
                "companyId": "company-1",
                "title": "Running work",
                "status": "RUNNING",
                "triggerType": "manual",
                "startedAt": "2026-06-03T10:00:00+00:00",
            },
            {
                "workItemId": "work-2",
                "email": "user@example.com",
                "companyId": "company-1",
                "title": "Review work",
                "status": "REVIEW",
                "triggerType": "manual",
            },
        ],
        id_key="workItemId",
    )
    monkeypatch.setattr(notifications, "notifications_collection", notifications_collection)
    monkeypatch.setattr(notifications, "work_items_collection", work_collection)
    monkeypatch.setattr(notifications, "eval_runs_collection", _Collection([], id_key="runId"))
    monkeypatch.setattr(notifications, "harvester_runs_collection", _Collection([], id_key="harvesterRunId"))

    summary = await notifications.activity_summary("user@example.com", "company-1")

    assert summary["status"]["runningTasks"] == 1
    assert summary["status"]["reviewTasks"] == 1
    assert summary["notifications"]["unreadCount"] == 1
    assert summary["running"][0]["title"] == "Running work"


@pytest.mark.asyncio
async def test_delete_clear_and_cleanup_notifications(monkeypatch):
    collection = _Collection(
        [
            {
                "notificationId": "notification-1",
                "email": "user@example.com",
                "companyId": "company-1",
                "title": "Old read",
                "read": True,
                "readAt": "2026-04-01T10:00:00+00:00",
                "createdAt": "2026-04-01T10:00:00+00:00",
            },
            {
                "notificationId": "notification-2",
                "email": "user@example.com",
                "companyId": "company-1",
                "title": "Unread",
                "read": False,
                "createdAt": "2026-06-03T10:00:00+00:00",
            },
        ]
    )
    monkeypatch.setattr(notifications, "notifications_collection", collection)

    cleanup = await notifications.cleanup_notifications(email="user@example.com", company_id="company-1", read_older_than_days=7)
    deleted = await notifications.delete_notification("notification-2")

    assert cleanup["deletedOld"] == 1
    assert deleted["success"] is True
    assert await collection.count_documents({"email": "user@example.com"}) == 0


@pytest.mark.asyncio
async def test_activity_summary_counts_evals_and_harvesters(monkeypatch):
    monkeypatch.setattr(notifications, "notifications_collection", _Collection())
    monkeypatch.setattr(notifications, "work_items_collection", _Collection([], id_key="workItemId"))
    monkeypatch.setattr(
        notifications,
        "eval_runs_collection",
        _Collection(
            [
                {"runId": "eval-1", "email": "user@example.com", "companyId": "company-1", "label": "pending"},
                {"runId": "eval-2", "email": "user@example.com", "companyId": "company-1", "label": "fail"},
            ],
            id_key="runId",
        ),
    )
    monkeypatch.setattr(
        notifications,
        "harvester_runs_collection",
        _Collection(
            [
                {"harvesterRunId": "harvest-1", "email": "user@example.com", "companyId": "company-1", "status": "running"},
                {"harvesterRunId": "harvest-2", "email": "user@example.com", "companyId": "company-1", "status": "harvest_failed"},
            ],
            id_key="harvesterRunId",
        ),
    )

    summary = await notifications.activity_summary("user@example.com", "company-1")

    assert summary["status"]["evalRunsPending"] == 1
    assert summary["status"]["evalRunsFailed"] == 1
    assert summary["status"]["harvestersRunning"] == 1
    assert summary["status"]["harvestersFailed"] == 1
