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


@pytest.mark.asyncio
async def test_execute_agent_harvest_job(monkeypatch):
    calls = []

    async def run_harvester_background(**kwargs):
        calls.append(kwargs)

    from app.routes import agent_creation

    monkeypatch.setattr(agent_creation, "_run_harvester_background", run_harvester_background)

    result = await workers.execute_job(
        {
            "type": "agent_harvest",
            "payload": {
                "agentId": "agent-1",
                "jobId": "creation-1",
                "harvesterRunId": "run-1",
                "harvesterName": "test_harvester",
            },
        }
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "agent_id": "agent-1",
            "job_id": "creation-1",
            "harvester_run_id": "run-1",
            "harvester_name": "test_harvester",
        }
    ]
