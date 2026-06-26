import pytest

from app.services import skill_regressions
from app.services.skill_regressions import latest_skill_regression
from app.services.skill_regressions import skill_eval_ids
from app.services.skill_regressions import skill_regression_cases
from app.services.skill_regressions import skill_trajectory_docs


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def sort(self, key, direction):
        reverse = direction < 0
        self.docs.sort(key=lambda doc: doc.get(key) or "", reverse=reverse)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class _Collection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.queries = []

    async def find_one(self, query, projection=None):
        self.queries.append(dict(query))
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        self.queries.append(dict(query))
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])


def _matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in set(value["$in"]):
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


@pytest.mark.asyncio
async def test_skill_trajectory_docs_loads_deduped_source_trajectories(monkeypatch):
    trajectories = _Collection(
        [
            {"trajectoryId": "traj-1", "taskId": "task-1"},
            {"trajectoryId": "traj-2", "taskId": "task-2"},
        ]
    )
    monkeypatch.setattr(skill_regressions, "trajectories_collection", trajectories)

    docs = await skill_trajectory_docs({"trajectoryIds": ["traj-1", "traj-1", "traj-2", ""]})

    assert [doc["trajectoryId"] for doc in docs] == ["traj-1", "traj-2"]
    assert trajectories.queries == [{"trajectoryId": "traj-1"}, {"trajectoryId": "traj-2"}]


@pytest.mark.asyncio
async def test_skill_regression_cases_collects_task_and_legacy_eval_contracts(monkeypatch):
    benchmark_tasks = _Collection(
        [
            {
                "taskId": "task-1",
                "benchmarkId": "bench-1",
                "companyId": "co-1",
                "email": "owner@example.com",
                "name": "Draft claim response",
                "metadata": {
                    "taskContract": {
                        "businessIntent": "Answer claim status",
                        "successCriteria": "Draft created",
                        "riskClass": "draft",
                        "expectedInputs": ["claim_id", "customer_email"],
                        "expectedArtifacts": ["draft_email"],
                        "allowedSystems": ["imap", "insurance_erp"],
                    },
                },
                "createdAt": "2026-06-25T10:00:00+00:00",
            }
        ]
    )
    legacy_evals = _Collection(
        [
            {
                "evalId": "eval-1",
                "benchmarkId": "bench-1",
                "companyId": "co-1",
                "email": "owner@example.com",
                "agentTaskName": "Legacy claim check",
                "riskClass": "read",
                "createdAt": "2026-06-25T11:00:00+00:00",
            }
        ]
    )
    monkeypatch.setattr(skill_regressions, "benchmark_tasks_collection", benchmark_tasks)
    monkeypatch.setattr(skill_regressions, "evals_collection", legacy_evals)

    cases = await skill_regression_cases(
        {"companyId": "co-1", "email": "owner@example.com", "benchmarkId": "bench-1", "evalId": "eval-1"},
        trajectory_docs=[{"taskId": "task-1", "benchmarkId": "bench-1", "evalId": "eval-1"}],
    )

    assert [case["source"] for case in cases] == ["benchmark_task", "legacy_eval"]
    assert cases[0]["businessIntent"] == "Answer claim status"
    assert cases[0]["expectedInputs"] == ["claim_id", "customer_email"]
    assert cases[0]["expectedArtifacts"] == ["draft_email"]
    assert cases[1]["evalId"] == "eval-1"
    assert all(query["companyId"] == "co-1" and query["email"] == "owner@example.com" for query in benchmark_tasks.queries + legacy_evals.queries)


@pytest.mark.asyncio
async def test_latest_skill_regression_uses_linked_eval_ids_and_latest_run(monkeypatch):
    benchmark_tasks = _Collection([{"taskId": "task-from-benchmark", "benchmarkId": "bench-1", "companyId": "co-1"}])
    legacy_evals = _Collection([{"evalId": "eval-from-benchmark", "benchmarkId": "bench-1", "companyId": "co-1"}])
    eval_runs = _Collection(
        [
            {"evalId": "eval-from-trajectory", "runId": "run-old", "label": "fail", "createdAt": "2026-06-25T10:00:00+00:00"},
            {"evalId": "task-from-benchmark", "runId": "run-new", "label": "PASS", "createdAt": "2026-06-25T12:00:00+00:00"},
        ]
    )
    monkeypatch.setattr(skill_regressions, "benchmark_tasks_collection", benchmark_tasks)
    monkeypatch.setattr(skill_regressions, "evals_collection", legacy_evals)
    monkeypatch.setattr(skill_regressions, "eval_runs_collection", eval_runs)

    eval_ids = await skill_eval_ids(
        {"companyId": "co-1", "benchmarkId": "bench-1", "evalId": "eval-direct"},
        trajectory_docs=[{"evalId": "eval-from-trajectory"}],
    )
    latest = await latest_skill_regression(
        {"companyId": "co-1", "benchmarkId": "bench-1", "evalId": "eval-direct"},
        trajectory_docs=[{"evalId": "eval-from-trajectory"}],
    )

    assert eval_ids == ["eval-direct", "eval-from-trajectory", "eval-from-benchmark", "task-from-benchmark"]
    assert latest == {
        "evalId": "task-from-benchmark",
        "runId": "run-new",
        "label": "pass",
        "createdAt": "2026-06-25T12:00:00+00:00",
    }
