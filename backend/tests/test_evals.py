import pytest

from app.routes import evals as evals_route
from app.routes.evals import BenchmarkRunCreateRequest


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    async def to_list(self, length):
        return list(self.docs)[:length]


class _FakeEvalsCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        benchmark_id = query["$or"][0]["benchmarkId"]
        operator_id = query["$or"][1]["operatorId"]
        return _FakeCursor(
            [
                doc
                for doc in self.docs
                if doc.get("benchmarkId") == benchmark_id or doc.get("operatorId") == operator_id
            ]
        )


class _FakeRunsCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _FakeOperatorsCollection:
    async def find_one(self, query, projection=None):
        if query.get("operatorId") == "op-2":
            return {"name": "Second Agent"}
        return None


@pytest.mark.asyncio
async def test_create_benchmark_run_uses_selected_operator(monkeypatch):
    evals = _FakeEvalsCollection(
        [
            {
                "evalId": "eval-1",
                "email": "user@example.com",
                "benchmarkId": "bench-1",
                "benchmarkName": "Demo Benchmark",
                "operatorId": "original-op",
                "operatorName": "Original Agent",
                "operatorTaskName": "Task 1",
                "prompt": "Do the first thing",
                "initialUrl": "https://example.com",
            }
        ]
    )
    runs = _FakeRunsCollection()
    monkeypatch.setattr(evals_route, "evals_collection", evals)
    monkeypatch.setattr(evals_route, "eval_runs_collection", runs)
    monkeypatch.setattr(evals_route, "operators_collection", _FakeOperatorsCollection())

    result = await evals_route.create_benchmark_run(
        "bench-1",
        BenchmarkRunCreateRequest(operatorId="op-2"),
    )

    assert result["success"] is True
    assert len(runs.docs) == 1
    assert runs.docs[0]["operatorId"] == "op-2"
    assert runs.docs[0]["operatorName"] == "Second Agent"
    assert result["runs"][0]["prompt"] == "Do the first thing"
