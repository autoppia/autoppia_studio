from __future__ import annotations

from typing import Any

from app.database import benchmark_tasks_collection, eval_runs_collection, evals_collection, trajectories_collection
from app.services.task_contracts import task_contract_from_record


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def regression_case_key(case: dict[str, Any]) -> str:
    return str(case.get("taskId") or case.get("evalId") or f"{case.get('source')}:{case.get('benchmarkId')}:{case.get('name')}")


def serialize_regression_case(doc: dict[str, Any], *, source: str) -> dict[str, Any]:
    task_contract = task_contract_from_record(doc)
    return {
        "source": source,
        "taskId": doc.get("taskId", ""),
        "evalId": doc.get("evalId", ""),
        "benchmarkId": doc.get("benchmarkId", ""),
        "name": doc.get("name") or doc.get("taskName") or doc.get("agentTaskName") or "",
        "businessIntent": task_contract.get("businessIntent") or "",
        "successCriteria": task_contract.get("successCriteria") or "",
        "riskClass": task_contract.get("riskClass") or "",
        "expectedArtifacts": task_contract.get("expectedArtifacts") or [],
        "allowedSystems": task_contract.get("allowedSystems") or [],
    }


async def skill_trajectory_docs(
    skill: dict[str, Any],
    trajectory_docs: list[dict[str, Any]] | None = None,
    *,
    trajectories: Any | None = None,
) -> list[dict[str, Any]]:
    if trajectories is None:
        trajectories = trajectories_collection
    if trajectory_docs is not None:
        return trajectory_docs
    docs: list[dict[str, Any]] = []
    for trajectory_id in _dedupe_strings([str(value or "") for value in (skill.get("trajectoryIds") or [])]):
        trajectory = await trajectories.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
        if trajectory:
            docs.append(trajectory)
    return docs


async def skill_regression_cases(
    skill: dict[str, Any],
    *,
    trajectory_docs: list[dict[str, Any]],
    benchmark_tasks: Any | None = None,
    legacy_evals: Any | None = None,
) -> list[dict[str, Any]]:
    if benchmark_tasks is None:
        benchmark_tasks = benchmark_tasks_collection
    if legacy_evals is None:
        legacy_evals = evals_collection
    company_id = str(skill.get("companyId") or "")
    email = str(skill.get("email") or "")
    task_ids = _dedupe_strings([str(trajectory.get("taskId") or "") for trajectory in trajectory_docs])
    benchmark_ids = _dedupe_strings(
        [
            str(skill.get("benchmarkId") or ""),
            *[str(trajectory.get("benchmarkId") or "") for trajectory in trajectory_docs],
        ]
    )
    eval_ids = _dedupe_strings(
        [
            str(skill.get("evalId") or ""),
            *[str(trajectory.get("evalId") or "") for trajectory in trajectory_docs],
        ]
    )

    cases_by_key: dict[str, dict[str, Any]] = {}

    async def collect(collection: Any, query: dict[str, Any], source: str, limit: int = 100) -> None:
        if company_id:
            query["companyId"] = company_id
        if email:
            query["email"] = email
        docs = await collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=limit)
        for doc in docs:
            case = serialize_regression_case(doc, source=source)
            key = regression_case_key(case)
            if key:
                cases_by_key.setdefault(key, case)

    if task_ids:
        await collect(benchmark_tasks, {"taskId": {"$in": task_ids}}, "benchmark_task")
    if benchmark_ids:
        await collect(benchmark_tasks, {"benchmarkId": {"$in": benchmark_ids}}, "benchmark_task")
    if eval_ids:
        await collect(legacy_evals, {"evalId": {"$in": eval_ids}}, "legacy_eval")
    if benchmark_ids:
        await collect(legacy_evals, {"benchmarkId": {"$in": benchmark_ids}}, "legacy_eval")

    return list(cases_by_key.values())[:100]


async def skill_eval_ids(
    skill: dict[str, Any],
    trajectory_docs: list[dict[str, Any]] | None = None,
    *,
    trajectories: Any | None = None,
    benchmark_tasks: Any | None = None,
    legacy_evals: Any | None = None,
) -> list[str]:
    if trajectories is None:
        trajectories = trajectories_collection
    if benchmark_tasks is None:
        benchmark_tasks = benchmark_tasks_collection
    if legacy_evals is None:
        legacy_evals = evals_collection
    eval_ids = _dedupe_strings([str(skill.get("evalId") or "")])
    benchmark_id = str(skill.get("benchmarkId") or "")
    company_id = str(skill.get("companyId") or "")
    email = str(skill.get("email") or "")
    trajectory_docs = await skill_trajectory_docs(skill, trajectory_docs, trajectories=trajectories)

    eval_ids.extend(_dedupe_strings([str(trajectory.get("evalId") or "") for trajectory in trajectory_docs]))

    if benchmark_id:
        legacy_query: dict[str, Any] = {"benchmarkId": benchmark_id}
        task_query: dict[str, Any] = {"benchmarkId": benchmark_id}
        if company_id:
            legacy_query["companyId"] = company_id
            task_query["companyId"] = company_id
        if email:
            legacy_query["email"] = email
            task_query["email"] = email

        legacy_eval_docs = await legacy_evals.find(legacy_query, {"_id": 0, "evalId": 1}).to_list(length=500)
        benchmark_task_docs = await benchmark_tasks.find(task_query, {"_id": 0, "taskId": 1}).to_list(length=500)
        eval_ids.extend(_dedupe_strings([str(doc.get("evalId") or "") for doc in legacy_eval_docs]))
        eval_ids.extend(_dedupe_strings([str(doc.get("taskId") or "") for doc in benchmark_task_docs]))

    return _dedupe_strings(eval_ids)


async def latest_skill_regression(
    skill: dict[str, Any],
    trajectory_docs: list[dict[str, Any]] | None = None,
    *,
    trajectories: Any | None = None,
    benchmark_tasks: Any | None = None,
    legacy_evals: Any | None = None,
    eval_runs: Any | None = None,
) -> dict[str, Any] | None:
    if trajectories is None:
        trajectories = trajectories_collection
    if benchmark_tasks is None:
        benchmark_tasks = benchmark_tasks_collection
    if legacy_evals is None:
        legacy_evals = evals_collection
    if eval_runs is None:
        eval_runs = eval_runs_collection
    eval_ids = await skill_eval_ids(
        skill,
        trajectory_docs=trajectory_docs,
        trajectories=trajectories,
        benchmark_tasks=benchmark_tasks,
        legacy_evals=legacy_evals,
    )
    if not eval_ids:
        return None
    runs = await eval_runs.find({"evalId": {"$in": eval_ids}}, {"_id": 0}).sort("createdAt", -1).to_list(length=100)
    if not runs:
        return None
    latest = runs[0]
    return {
        "evalId": latest.get("evalId", ""),
        "runId": latest.get("runId", ""),
        "label": str(latest.get("label") or "").strip().lower(),
        "createdAt": latest.get("createdAt"),
    }
