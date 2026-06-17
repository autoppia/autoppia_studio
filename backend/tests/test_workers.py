import pytest

from app.services import workers


class _Locks:
    def __init__(self):
        self.calls = []

    async def find_one_and_update(self, query, update, **kwargs):
        self.calls.append((query, update, kwargs))
        return {"lockId": update["$set"]["lockId"], "ownerId": update["$set"]["ownerId"]}


@pytest.mark.asyncio
async def test_worker_lease_uses_mongo_lock(monkeypatch):
    locks = _Locks()
    monkeypatch.setattr(workers, "worker_locks_collection", locks)

    acquired = await workers.acquire_worker_lease("scheduled_work", ttl_seconds=30)

    assert acquired is True
    query, update, kwargs = locks.calls[0]
    assert query["lockId"] == "scheduled_work"
    assert update["$set"]["ownerId"] == workers.WORKER_OWNER_ID
    assert kwargs["upsert"] is True
