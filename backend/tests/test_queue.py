import pytest

from app.services import queue


class _Result:
    modified_count = 1


def _matches(doc, query):
    for key, value in query.items():
        current = doc.get(key)
        if key == "$or":
            if not any(_matches(doc, option) for option in value):
                return False
            continue
        if isinstance(value, dict):
            if "$in" in value and current not in value["$in"]:
                return False
            if "$lte" in value and not (current is not None and current <= value["$lte"]):
                return False
            if "$exists" in value and (key in doc) != bool(value["$exists"]):
                return False
            continue
        if current != value:
            return False
    return True


class _Jobs:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if _matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs[doc["jobId"]] = dict(doc)

    async def find_one_and_update(self, query, update, **kwargs):
        docs = [doc for doc in self.docs.values() if _matches(doc, query)]
        docs.sort(key=lambda item: (item.get("runAt"), item.get("createdAt")))
        if not docs:
            return None
        stored = self.docs[docs[0]["jobId"]]
        stored.update(update.get("$set", {}))
        for key, value in update.get("$inc", {}).items():
            stored[key] = stored.get(key, 0) + value
        return dict(stored)

    async def update_one(self, query, update):
        for job_id, doc in self.docs.items():
            if _matches(doc, query):
                self.docs[job_id].update(update.get("$set", {}))
                return _Result()
        return _Result()


@pytest.mark.asyncio
async def test_enqueue_claim_and_complete_job(monkeypatch):
    jobs = _Jobs()
    monkeypatch.setattr(queue, "jobs_collection", jobs)

    first = await queue.enqueue_job("work_run", {"workItemId": "work-1"}, dedupe_key="work:1")
    second = await queue.enqueue_job("work_run", {"workItemId": "work-1"}, dedupe_key="work:1")
    claimed = await queue.claim_next_job(worker_id="worker-1")
    await queue.complete_job(claimed["jobId"], {"ok": True})

    assert first["jobId"] == second["jobId"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert jobs.docs[first["jobId"]]["status"] == "done"
    assert jobs.docs[first["jobId"]]["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_fail_job_requeues_until_max_attempts(monkeypatch):
    jobs = _Jobs()
    monkeypatch.setattr(queue, "jobs_collection", jobs)

    job = await queue.enqueue_job("knowledge_index", {"documentId": "doc-1"}, max_attempts=2)
    claimed = await queue.claim_next_job(worker_id="worker-1")
    await queue.fail_job(claimed, "temporary")

    assert jobs.docs[job["jobId"]]["status"] == "queued"
    jobs.docs[job["jobId"]]["attempts"] = 2
    await queue.fail_job(jobs.docs[job["jobId"]], "permanent")

    assert jobs.docs[job["jobId"]]["status"] == "failed"
