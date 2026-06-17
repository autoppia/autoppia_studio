from datetime import datetime, timezone

import pytest

from app.services import metering


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


class _UsageEvents:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query, projection=None):
        run_id = query.get("runId")
        return _Cursor([doc for doc in self.docs if not run_id or doc.get("runId") == run_id])


@pytest.mark.asyncio
async def test_record_usage_and_run_credits_spent(monkeypatch):
    collection = _UsageEvents()
    monkeypatch.setattr(metering, "usage_events_collection", collection)

    await metering.record_usage(email="user@example.com", run_id="run-1", kind="agent_step", credits=0.1)
    await metering.record_usage(email="user@example.com", run_id="run-1", kind="tool_call", credits=0.03, units=2)
    await metering.record_usage(email="user@example.com", run_id="run-2", kind="agent_step", credits=0.5)

    assert collection.docs[0]["createdAt"].tzinfo is not None
    assert collection.docs[0]["createdAt"] <= datetime.now(timezone.utc)
    assert await metering.run_credits_spent("run-1") == 0.16
