from datetime import datetime, timedelta, timezone

import pytest

from app.routes import analytics as analytics_route


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


class _FakeSessionsCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        cutoff = query["createdAt"]["$gte"]
        return _FakeCursor([doc for doc in self.docs if doc["email"] == query["email"] and doc["createdAt"] >= cutoff])


class _FakeUsageEventsCollection(_FakeSessionsCollection):
    pass


def test_analytics_buckets_have_expected_window_sizes():
    now = datetime(2026, 6, 1, 15, 42, tzinfo=timezone.utc)

    assert len(analytics_route._empty_buckets("24h", now)) == 24
    assert analytics_route._empty_buckets("24h", now)[-1] == "2026-06-01T15:00"
    assert len(analytics_route._empty_buckets("7d", now)) == 7
    assert analytics_route._empty_buckets("7d", now)[0] == "2026-05-26"
    assert analytics_route._empty_buckets("7d", now)[-1] == "2026-06-01"
    assert len(analytics_route._empty_buckets("30d", now)) == 30
    assert len(analytics_route._empty_buckets("90d", now)) == 90


@pytest.mark.asyncio
async def test_analytics_current_hour_sessions_appear_in_chart(monkeypatch):
    now = datetime.now(timezone.utc)
    current_bucket = analytics_route._bucket_key(now, "24h")
    old_doc = {
        "email": "user@example.com",
        "createdAt": now - timedelta(hours=30),
        "actionHistory": [{"type": "click"}],
    }
    docs = [
        {
            "email": "user@example.com",
            "createdAt": now,
            "actionHistory": [{"type": "click"}, {"type": "type"}],
        },
        {
            "email": "user@example.com",
            "createdAt": now,
            "actionHistory": [],
        },
        old_doc,
    ]
    monkeypatch.setattr(analytics_route, "sessions_collection", _FakeSessionsCollection(docs))
    monkeypatch.setattr(analytics_route, "usage_events_collection", _FakeUsageEventsCollection([]))

    result = await analytics_route.get_analytics("user@example.com", "24h")

    assert result["sessions"]["total"] == 2
    assert result["sessions"]["with_no_tasks"] == 1
    assert result["sessions"]["avg_tasks_per_session"] == 1.0
    current = next(point for point in result["sessions"]["over_time"] if point["bucket"] == current_bucket)
    assert current == {"bucket": current_bucket, "with_tasks": 1, "no_tasks": 1}


@pytest.mark.asyncio
async def test_analytics_includes_usage_events(monkeypatch):
    now = datetime.now(timezone.utc)
    current_bucket = analytics_route._bucket_key(now, "24h")
    monkeypatch.setattr(analytics_route, "sessions_collection", _FakeSessionsCollection([]))
    monkeypatch.setattr(
        analytics_route,
        "usage_events_collection",
        _FakeUsageEventsCollection(
            [
                {"email": "user@example.com", "createdAt": now, "credits": 0.05, "source": "agent_step"},
                {"email": "user@example.com", "createdAt": now, "credits": 0.02, "source": "crm.search"},
                {"email": "other@example.com", "createdAt": now, "credits": 10.0, "source": "agent_step"},
                {"email": "user@example.com", "createdAt": now - timedelta(hours=30), "credits": 1.0, "source": "old"},
            ]
        ),
    )

    result = await analytics_route.get_analytics("user@example.com", "24h")

    assert result["credits"]["available"] is True
    assert result["credits"]["total_usage"] == 0.07
    assert result["credits"]["breakdown_by_source"] == [
        {"source": "agent_step", "usage": 0.05},
        {"source": "crm.search", "usage": 0.02},
    ]
    current = next(point for point in result["credits"]["usage_over_time"] if point["bucket"] == current_bucket)
    assert current == {"bucket": current_bucket, "usage": 0.07}
