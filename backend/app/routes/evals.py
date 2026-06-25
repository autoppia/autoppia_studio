import logging
from datetime import datetime, timezone
from typing import Any, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    agents_collection,
    benchmark_tasks_collection,
    benchmarks_collection,
    capabilities_collection,
    eval_runs_collection,
    evals_collection,
)
from app.services.eval_judge import judge_eval_run
from app.services.connector_benchmarks import audit_connector_benchmark_matrix, connector_benchmark_catalog, harvest_and_smoke_connector_benchmark, run_connector_runtime_smoke, seed_connector_benchmark

logger = logging.getLogger(__name__)
router = APIRouter()


class EvalCreateRequest(BaseModel):
    email: str
    prompt: str
    initialUrl: str = ""


class RunCreateRequest(BaseModel):
    sessionId: str = ""
    agentId: str = ""
    agentName: str = ""


class BenchmarkRunCreateRequest(BaseModel):
    sessionId: str = ""
    agentId: str = ""
    agentName: str = ""


class BenchmarkCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    name: str
    description: str = ""
    websiteUrl: str = ""
    agentId: str = ""
    agentName: str = ""


class BenchmarkTaskCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    agentId: str = ""
    name: str = ""
    prompt: str
    successCriteria: str = ""
    initialUrl: str = ""
    judgeType: str = "manual"
    businessIntent: str = ""
    allowedSystems: list[str] = Field(default_factory=list)
    expectedArtifacts: list[str] = Field(default_factory=list)
    riskClass: str = ""
    initialState: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunUpdateRequest(BaseModel):
    label: str | None = None
    actions: List[Any] | None = None
    sessionId: str | None = None
    screenshots: List[str] | None = None


class JudgeRunRequest(BaseModel):
    userContext: dict[str, Any] = {}
    apply: bool = True
    force: bool = False


class ConnectorBenchmarkSeedRequest(BaseModel):
    email: str
    companyId: str
    connectorId: str
    benchmarkKey: str = "email"
    agentId: str = ""
    publishTools: bool = True


class ConnectorBenchmarkSmokeRequest(BaseModel):
    agentId: str = ""
    taskKeys: list[str] = Field(default_factory=list)
    approveSkills: bool = True


class ConnectorBenchmarkAuditRequest(BaseModel):
    email: str
    companyId: str
    publishTools: bool = True


class ConnectorBenchmarkSeedAndSmokeRequest(ConnectorBenchmarkSeedRequest):
    taskKeys: list[str] = Field(default_factory=list)


def _clean_judge_type(value: Any) -> str:
    normalized = str(value or "manual").strip().lower()
    if normalized in {"llm", "llmjudge", "llm_judge"}:
        return "llm"
    return "manual"


async def _agent_name(agent_id: str, fallback: str = "") -> str:
    if not agent_id:
        return fallback or "Generalist Agent"
    doc = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0, "name": 1})
    return str((doc or {}).get("name") or fallback or "Custom Agent")


def _task_to_eval(task: dict[str, Any], benchmark: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    benchmark_doc = benchmark or {}
    initial_url = metadata.get("startUrl") or metadata.get("iwaStartUrl") or benchmark_doc.get("websiteUrl") or ""
    task_contract = {
        "businessIntent": metadata.get("businessIntent") or task.get("businessIntent") or task.get("prompt", ""),
        "initialState": metadata.get("initialState") if isinstance(metadata.get("initialState"), dict) else {},
        "initialUrl": initial_url,
        "allowedSystems": [str(item) for item in metadata.get("allowedSystems") or [] if item],
        "expectedArtifacts": [str(item) for item in metadata.get("expectedArtifacts") or [] if item],
        "successCriteria": task.get("successCriteria", ""),
        "riskClass": str(metadata.get("riskClass") or ""),
    }
    task_contract["completeness"] = _task_contract_completeness(task_contract)
    judge_type = _clean_judge_type(task.get("judgeType"))
    return {
        "evalId": task.get("taskId", ""),
        "taskId": task.get("taskId", ""),
        "email": task.get("email", ""),
        "companyId": task.get("companyId", ""),
        "prompt": task.get("prompt", ""),
        "initialUrl": initial_url,
        "benchmarkId": task.get("benchmarkId", ""),
        "benchmarkName": benchmark_doc.get("name") or task.get("benchmarkName") or "Benchmark",
        "agentId": task.get("agentId", ""),
        "agentName": benchmark_doc.get("agentName", ""),
        "agentTaskName": task.get("taskName") or task.get("name") or "",
        "successCriteria": task.get("successCriteria", ""),
        "taskContract": task_contract,
        "judgeType": judge_type,
        "evaluationHarness": _evaluation_harness(task_contract, judge_type),
        "status": task.get("status", ""),
        "source": task.get("source", "benchmark_task"),
        "createdAt": task.get("createdAt"),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _task_contract_completeness(contract: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "businessIntent": bool(str(contract.get("businessIntent") or "").strip()),
        "initialState": bool(contract.get("initialUrl") or contract.get("initialState")),
        "allowedSystems": bool(contract.get("allowedSystems")),
        "expectedArtifact": bool(contract.get("expectedArtifacts")),
        "successCriteria": bool(str(contract.get("successCriteria") or "").strip()),
        "riskClass": bool(str(contract.get("riskClass") or "").strip()),
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    return {
        "checks": checks,
        "passedChecks": passed,
        "totalChecks": total,
        "score": round(passed / total, 3) if total else 0.0,
        "state": "complete" if passed == total else "incomplete",
    }


def _evaluation_harness(contract: dict[str, Any], judge_type: str) -> dict[str, Any]:
    deterministic_ready = bool(str(contract.get("successCriteria") or "").strip())
    stateful_ready = bool(contract.get("initialUrl") or contract.get("initialState"))
    llm_enabled = judge_type == "llm"
    layers = [
        {
            "key": "deterministic",
            "label": "Deterministic checks",
            "enabled": deterministic_ready,
            "role": "first_pass",
            "summary": "Success criteria can be checked before model judging." if deterministic_ready else "Add success criteria for deterministic checks.",
        },
        {
            "key": "stateful",
            "label": "Stateful evaluator",
            "enabled": stateful_ready,
            "role": "environment_replay",
            "summary": "Initial URL/state can drive replay or stateful evaluation." if stateful_ready else "Add initial URL or state for replay.",
        },
        {
            "key": "llm",
            "label": "LLM judge",
            "enabled": llm_enabled,
            "role": "semantic_review",
            "summary": "LLMJudge is enabled as semantic review." if llm_enabled else "LLMJudge is disabled unless this task needs semantic review.",
        },
        {
            "key": "manual",
            "label": "Human review",
            "enabled": True,
            "role": "override",
            "summary": "Manual review remains available for overrides and unresolved cases.",
        },
    ]
    return {
        "strategy": "layered",
        "preferredOrder": [layer["key"] for layer in layers if layer["enabled"]],
        "deterministicFirst": deterministic_ready,
        "statefulReplay": stateful_ready,
        "llmAsComplement": llm_enabled,
        "humanOverride": True,
        "layers": layers,
    }


def _promotion_gate(
    *,
    task_total: int,
    task_complete: int,
    skill_total: int,
    ready_skills: int,
    published_skills: int,
    run_total: int,
    run_pass: int,
    run_fail: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    next_actions: list[str] = []
    if task_total == 0:
        blockers.append("no_tasks")
        next_actions.append("Add benchmark tasks with business intent, allowed systems, expected artifacts, success criteria, and risk class.")
    elif task_complete < task_total:
        blockers.append("incomplete_task_contracts")
        next_actions.append("Complete every task contract before using the benchmark as a production gate.")
    if skill_total == 0:
        blockers.append("no_skills")
        next_actions.append("Harvest candidate trajectories and promote at least one reusable skill.")
    elif ready_skills == 0:
        blockers.append("no_ready_skills")
        next_actions.append("Harden skills with activation guidance, IO, policy, source trajectories, and regression evidence.")
    if run_total == 0:
        blockers.append("no_regression_runs")
        next_actions.append("Run the benchmark and judge the resulting task trials.")
    elif run_pass == 0:
        blockers.append("no_passing_regression")
        next_actions.append("Get at least one passing regression run before promotion.")
    if run_fail > 0:
        blockers.append("failing_regressions")
        next_actions.append("Investigate failing regression runs before publishing or widening runtime access.")

    if blockers:
        state = "needs_regression" if blockers == ["no_regression_runs"] else "blocked"
    elif published_skills > 0:
        state = "published"
    else:
        state = "ready"

    return {
        "state": state,
        "blockers": blockers,
        "nextActions": next_actions,
        "canPromote": state in {"ready", "published"},
    }


def _benchmark_coverage_summary(
    *,
    tasks: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    unique_skills: list[dict[str, Any]] = []
    seen_skill_ids: set[str] = set()
    for skill in skills:
        skill_id = str(skill.get("capabilityId") or skill.get("skillId") or "").strip()
        if skill_id and skill_id in seen_skill_ids:
            continue
        if skill_id:
            seen_skill_ids.add(skill_id)
        unique_skills.append(skill)
    skills = unique_skills
    task_evals = [_task_to_eval(task, benchmark) for task in tasks]
    contracts = [task.get("taskContract") or {} for task in task_evals]
    completeness = [contract.get("completeness") or _task_contract_completeness(contract) for contract in contracts]
    systems = _dedupe_strings([system for contract in contracts for system in (contract.get("allowedSystems") or [])])
    task_artifacts = _dedupe_strings([artifact for contract in contracts for artifact in (contract.get("expectedArtifacts") or [])])
    skill_artifacts = _dedupe_strings([artifact for skill in skills for artifact in (skill.get("expectedArtifacts") or [])])
    risk_classes = _dedupe_strings([contract.get("riskClass") for contract in contracts])
    connector_ids = _dedupe_strings([connector_id for skill in skills for connector_id in (skill.get("connectorIds") or [])])
    entity_names = _dedupe_strings([
        entity
        for skill in skills
        for entity in [*(skill.get("inputEntities") or []), skill.get("outputEntity")]
    ])
    skill_ids = _dedupe_strings([skill.get("capabilityId") or skill.get("skillId") for skill in skills])
    labels = [str(run.get("label") or "pending").lower() for run in runs]
    latest_run = runs[0] if runs else None
    published_statuses = {"published", "approved", "active", "production"}
    ready_statuses = {"ready", *published_statuses}
    task_complete = sum(1 for item in completeness if item.get("state") == "complete")
    skill_ready = sum(1 for skill in skills if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in ready_statuses)
    skill_published = sum(1 for skill in skills if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in published_statuses)
    run_pass = labels.count("pass")
    run_fail = labels.count("fail")
    return {
        "taskCount": len(tasks),
        "taskContractCoverage": {
            "complete": task_complete,
            "total": len(completeness),
            "averageScore": round(sum(float(item.get("score") or 0) for item in completeness) / len(completeness), 3) if completeness else 0.0,
        },
        "systems": systems,
        "expectedArtifacts": _dedupe_strings([*task_artifacts, *skill_artifacts]),
        "riskClasses": risk_classes,
        "connectorIds": connector_ids,
        "entityNames": entity_names,
        "skillCoverage": {
            "skillIds": skill_ids,
            "total": len(skill_ids),
            "ready": skill_ready,
            "published": skill_published,
        },
        "runCoverage": {
            "total": len(runs),
            "pass": run_pass,
            "fail": run_fail,
            "pending": labels.count("pending"),
            "latestLabel": str((latest_run or {}).get("label") or ""),
            "latestRunId": str((latest_run or {}).get("runId") or ""),
            "latestCreatedAt": (latest_run or {}).get("createdAt"),
        },
        "promotionGate": _promotion_gate(
            task_total=len(tasks),
            task_complete=task_complete,
            skill_total=len(skill_ids),
            ready_skills=skill_ready,
            published_skills=skill_published,
            run_total=len(runs),
            run_pass=run_pass,
            run_fail=run_fail,
        ),
    }


def _coverage_portfolio(coverage_items: list[dict[str, Any]]) -> dict[str, Any]:
    latest_runs = [
        item.get("runCoverage") or {}
        for item in coverage_items
        if (item.get("runCoverage") or {}).get("latestRunId")
    ]
    latest_runs = sorted(latest_runs, key=lambda item: str(item.get("latestCreatedAt") or ""), reverse=True)
    task_total = sum(int((item.get("taskContractCoverage") or {}).get("total") or 0) for item in coverage_items)
    task_complete = sum(int((item.get("taskContractCoverage") or {}).get("complete") or 0) for item in coverage_items)
    run_total = sum(int((item.get("runCoverage") or {}).get("total") or 0) for item in coverage_items)
    run_pass = sum(int((item.get("runCoverage") or {}).get("pass") or 0) for item in coverage_items)
    run_fail = sum(int((item.get("runCoverage") or {}).get("fail") or 0) for item in coverage_items)
    run_pending = sum(int((item.get("runCoverage") or {}).get("pending") or 0) for item in coverage_items)
    skill_ids = _dedupe_strings([
        skill_id
        for item in coverage_items
        for skill_id in ((item.get("skillCoverage") or {}).get("skillIds") or [])
    ])
    ready_skills = sum(int((item.get("skillCoverage") or {}).get("ready") or 0) for item in coverage_items)
    published_skills = sum(int((item.get("skillCoverage") or {}).get("published") or 0) for item in coverage_items)
    portfolio = {
        "benchmarks": len(coverage_items),
        "tasks": task_total,
        "taskContracts": {
            "complete": task_complete,
            "total": task_total,
            "coverageRatio": round(task_complete / task_total, 3) if task_total else 0.0,
        },
        "connectors": _dedupe_strings([connector_id for item in coverage_items for connector_id in (item.get("connectorIds") or [])]),
        "systems": _dedupe_strings([system for item in coverage_items for system in (item.get("systems") or [])]),
        "entities": _dedupe_strings([entity for item in coverage_items for entity in (item.get("entityNames") or [])]),
        "artifacts": _dedupe_strings([artifact for item in coverage_items for artifact in (item.get("expectedArtifacts") or [])]),
        "skills": {
            "skillIds": skill_ids,
            "total": len(skill_ids),
            "ready": ready_skills,
            "published": published_skills,
        },
        "regressions": {
            "total": run_total,
            "pass": run_pass,
            "fail": run_fail,
            "pending": run_pending,
            "passRatio": round(run_pass / run_total, 3) if run_total else 0.0,
            "latest": [
                {
                    "runId": str(item.get("latestRunId") or ""),
                    "label": str(item.get("latestLabel") or ""),
                    "createdAt": item.get("latestCreatedAt"),
                }
                for item in latest_runs[:5]
            ],
        },
        "promotionGate": _promotion_gate(
            task_total=task_total,
            task_complete=task_complete,
            skill_total=len(skill_ids),
            ready_skills=ready_skills,
            published_skills=published_skills,
            run_total=run_total,
            run_pass=run_pass,
            run_fail=run_fail,
        ),
    }
    portfolio["coverageMatrix"] = _coverage_matrix(coverage_items)
    return portfolio


def _coverage_matrix(coverage_items: list[dict[str, Any]]) -> dict[str, Any]:
    connectors: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    skills: dict[str, dict[str, Any]] = {}

    def _run_state(run_coverage: dict[str, Any]) -> str:
        total = int(run_coverage.get("total") or 0)
        fail = int(run_coverage.get("fail") or 0)
        passed = int(run_coverage.get("pass") or 0)
        if total == 0:
            return "missing_regression"
        if fail:
            return "failing"
        if passed:
            return "passing"
        return "pending"

    def _touch_row(table: dict[str, dict[str, Any]], key: str, *, kind: str, benchmark_index: int, run_coverage: dict[str, Any]) -> None:
        row = table.setdefault(
            key,
            {
                "id": key,
                "kind": kind,
                "benchmarkCount": 0,
                "benchmarkRefs": [],
                "regressions": {"total": 0, "pass": 0, "fail": 0, "pending": 0},
                "state": "missing_regression",
            },
        )
        benchmark_ref = f"benchmark:{benchmark_index}"
        if benchmark_ref not in row["benchmarkRefs"]:
            row["benchmarkRefs"].append(benchmark_ref)
            row["benchmarkCount"] += 1
        regressions = row["regressions"]
        regressions["total"] += int(run_coverage.get("total") or 0)
        regressions["pass"] += int(run_coverage.get("pass") or 0)
        regressions["fail"] += int(run_coverage.get("fail") or 0)
        regressions["pending"] += int(run_coverage.get("pending") or 0)
        row_state = _run_state(regressions)
        row["state"] = row_state
        row["covered"] = row_state in {"passing", "pending"}

    for index, item in enumerate(coverage_items):
        run_coverage = item.get("runCoverage") if isinstance(item.get("runCoverage"), dict) else {}
        for connector_id in item.get("connectorIds") or []:
            _touch_row(connectors, str(connector_id), kind="connector", benchmark_index=index, run_coverage=run_coverage)
        for entity_name in item.get("entityNames") or []:
            _touch_row(entities, str(entity_name), kind="entity", benchmark_index=index, run_coverage=run_coverage)
        skill_coverage = item.get("skillCoverage") if isinstance(item.get("skillCoverage"), dict) else {}
        skill_state = "published" if int(skill_coverage.get("published") or 0) else "ready" if int(skill_coverage.get("ready") or 0) else "needs_hardening"
        for skill_id in skill_coverage.get("skillIds") or []:
            row = skills.setdefault(
                str(skill_id),
                {
                    "id": str(skill_id),
                    "kind": "skill",
                    "benchmarkCount": 0,
                    "benchmarkRefs": [],
                    "regressions": {"total": 0, "pass": 0, "fail": 0, "pending": 0},
                    "state": skill_state,
                    "covered": skill_state in {"ready", "published"},
                },
            )
            row["baseState"] = "published" if row.get("baseState") == "published" or skill_state == "published" else skill_state
            benchmark_ref = f"benchmark:{index}"
            if benchmark_ref not in row["benchmarkRefs"]:
                row["benchmarkRefs"].append(benchmark_ref)
                row["benchmarkCount"] += 1
            regressions = row["regressions"]
            regressions["total"] += int(run_coverage.get("total") or 0)
            regressions["pass"] += int(run_coverage.get("pass") or 0)
            regressions["fail"] += int(run_coverage.get("fail") or 0)
            regressions["pending"] += int(run_coverage.get("pending") or 0)
            regression_state = _run_state(regressions)
            base_state = str(row.get("baseState") or skill_state)
            if regression_state == "failing":
                row["state"] = "failing"
            elif base_state == "needs_hardening":
                row["state"] = base_state
            elif regression_state == "missing_regression":
                row["state"] = regression_state
            else:
                row["state"] = base_state
            row["covered"] = row["state"] in {"ready", "published"}

    def _sorted_rows(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        clean_rows = []
        for row in rows.values():
            clean = dict(row)
            clean.pop("baseState", None)
            clean_rows.append(clean)
        return sorted(clean_rows, key=lambda row: (-int(row.get("benchmarkCount") or 0), str(row.get("id") or "")))

    return {
        "connectors": _sorted_rows(connectors),
        "entities": _sorted_rows(entities),
        "skills": _sorted_rows(skills),
    }


async def _benchmark_task_eval(eval_id: str) -> dict[str, Any] | None:
    task = await benchmark_tasks_collection.find_one({"taskId": eval_id}, {"_id": 0})
    if not task:
        return None
    benchmark = await benchmarks_collection.find_one({"benchmarkId": task.get("benchmarkId", "")}, {"_id": 0}) or {}
    return _task_to_eval(task, benchmark)


# ── Eval (task) endpoints ──


@router.get("/evals")
async def list_evals(email: str, companyId: str = ""):
    legacy_query: dict[str, Any] = {"email": email}
    if companyId:
        legacy_query["companyId"] = companyId
    cursor = evals_collection.find(legacy_query, {"_id": 0}).sort("createdAt", -1)
    evals = await cursor.to_list(length=500)

    task_query: dict[str, Any] = {"email": email}
    if companyId:
        task_query["companyId"] = companyId
    task_cursor = benchmark_tasks_collection.find(task_query, {"_id": 0}).sort("createdAt", -1)
    tasks = await task_cursor.to_list(length=500)
    benchmark_ids = sorted({str(task.get("benchmarkId") or "") for task in tasks if task.get("benchmarkId")})
    benchmark_docs = {}
    if benchmark_ids:
        docs = await benchmarks_collection.find({"benchmarkId": {"$in": benchmark_ids}}, {"_id": 0}).to_list(length=500)
        benchmark_docs = {doc.get("benchmarkId"): doc for doc in docs}
    task_evals = [_task_to_eval(task, benchmark_docs.get(task.get("benchmarkId"))) for task in tasks]
    return {"evals": [*task_evals, *evals]}


@router.get("/eval-runs")
async def list_all_runs(email: str, companyId: str = ""):
    eval_query: dict[str, Any] = {"email": email}
    if companyId:
        eval_query["companyId"] = companyId
    eval_cursor = evals_collection.find(eval_query, {"_id": 0})
    evals = await eval_cursor.to_list(length=500)
    task_query: dict[str, Any] = {"email": email}
    if companyId:
        task_query["companyId"] = companyId
    tasks = await benchmark_tasks_collection.find(task_query, {"_id": 0}).to_list(length=500)
    benchmark_ids = sorted({str(task.get("benchmarkId") or "") for task in tasks if task.get("benchmarkId")})
    benchmark_docs = {}
    if benchmark_ids:
        docs = await benchmarks_collection.find({"benchmarkId": {"$in": benchmark_ids}}, {"_id": 0}).to_list(length=500)
        benchmark_docs = {doc.get("benchmarkId"): doc for doc in docs}
    task_evals = [_task_to_eval(task, benchmark_docs.get(task.get("benchmarkId"))) for task in tasks]
    evals = [*task_evals, *evals]
    eval_by_id = {ev.get("evalId"): ev for ev in evals}
    if not eval_by_id:
        return {"runs": []}

    run_cursor = eval_runs_collection.find(
        {"evalId": {"$in": list(eval_by_id.keys())}},
        {"_id": 0, "actions": 0},
    ).sort("createdAt", -1)
    runs = await run_cursor.to_list(length=1000)
    for run in runs:
        ev = eval_by_id.get(run.get("evalId"), {})
        run["prompt"] = ev.get("prompt", "")
        run["initialUrl"] = ev.get("initialUrl", "")
        run["benchmarkId"] = ev.get("benchmarkId", ev.get("agentId", ""))
        run["benchmarkName"] = ev.get("benchmarkName", ev.get("agentName", ""))
        run["agentId"] = run.get("agentId", "")
        run["agentName"] = run.get("agentName", "")
        run["agentTaskName"] = ev.get("agentTaskName", "")
        run["judgeType"] = _clean_judge_type(run.get("judgeType") or ev.get("judgeType"))
        run["labelSource"] = run.get("labelSource") or ("manual_review" if run["judgeType"] == "manual" else "llm_pending")
    return {"runs": runs}


@router.get("/benchmarks")
async def list_benchmarks(email: str, companyId: str = ""):
    query: dict[str, Any] = {"email": email}
    if companyId:
        query["companyId"] = companyId
    benchmarks = await benchmarks_collection.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=500)
    tasks = await benchmark_tasks_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    benchmark_ids = _dedupe_strings([benchmark.get("benchmarkId") for benchmark in benchmarks])
    task_ids = _dedupe_strings([task.get("taskId") for task in tasks])
    skills: list[dict[str, Any]] = []
    if benchmark_ids or task_ids:
        skill_query: dict[str, Any] = {**query, "capabilityKind": "skill"}
        linked_filters = []
        if benchmark_ids:
            linked_filters.append({"benchmarkId": {"$in": benchmark_ids}})
        if task_ids:
            linked_filters.append({"evalId": {"$in": task_ids}})
        if linked_filters:
            skill_query["$or"] = linked_filters
        skills = await capabilities_collection.find(skill_query, {"_id": 0}).sort("updatedAt", -1).to_list(length=1000)
    runs = []
    if task_ids:
        runs = await eval_runs_collection.find({"evalId": {"$in": task_ids}}, {"_id": 0, "actions": 0}).sort("createdAt", -1).to_list(length=1000)
    tasks_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_benchmark.setdefault(str(task.get("benchmarkId") or ""), []).append(task)
    skills_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for skill in skills:
        benchmark_id = str(skill.get("benchmarkId") or "")
        if benchmark_id:
            skills_by_benchmark.setdefault(benchmark_id, []).append(skill)
        eval_id = str(skill.get("evalId") or "")
        if eval_id:
            task = next((item for item in tasks if item.get("taskId") == eval_id), None)
            if task and task.get("benchmarkId"):
                skills_by_benchmark.setdefault(str(task.get("benchmarkId")), []).append(skill)
    runs_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    task_benchmark_by_id = {str(task.get("taskId") or ""): str(task.get("benchmarkId") or "") for task in tasks}
    for run in runs:
        benchmark_id = task_benchmark_by_id.get(str(run.get("evalId") or ""), "")
        if benchmark_id:
            runs_by_benchmark.setdefault(benchmark_id, []).append(run)
    benchmark_payloads = [
        {
            **benchmark,
            "tasks": [_task_to_eval(task, benchmark) for task in tasks_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), [])],
            "coverage": _benchmark_coverage_summary(
                tasks=tasks_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), []),
                skills=skills_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), []),
                runs=runs_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), []),
                benchmark=benchmark,
            ),
        }
        for benchmark in benchmarks
    ]
    return {
        "benchmarks": benchmark_payloads,
        "coveragePortfolio": _coverage_portfolio([benchmark.get("coverage") or {} for benchmark in benchmark_payloads]),
    }


@router.get("/connector-benchmarks/catalog")
async def list_connector_benchmark_catalog():
    return {"benchmarks": connector_benchmark_catalog()}


@router.post("/connector-benchmarks/audit-matrix")
async def audit_connector_benchmark_matrix_endpoint(body: ConnectorBenchmarkAuditRequest):
    if not body.email.strip():
        raise HTTPException(status_code=400, detail="email is required")
    if not body.companyId.strip():
        raise HTTPException(status_code=400, detail="companyId is required")
    report = await audit_connector_benchmark_matrix(
        email=body.email,
        company_id=body.companyId,
        publish_tools=body.publishTools,
    )
    return {"success": report["summary"]["fail"] == 0, "connectorAudit": report}


@router.post("/connector-benchmarks/seed")
async def seed_connector_benchmark_endpoint(body: ConnectorBenchmarkSeedRequest):
    if not body.email.strip():
        raise HTTPException(status_code=400, detail="email is required")
    if not body.companyId.strip():
        raise HTTPException(status_code=400, detail="companyId is required")
    if not body.connectorId.strip():
        raise HTTPException(status_code=400, detail="connectorId is required")
    try:
        seeded = await seed_connector_benchmark(
            benchmark_key=body.benchmarkKey,
            email=body.email,
            company_id=body.companyId,
            connector_id=body.connectorId,
            agent_id=body.agentId,
            publish_tools=body.publishTools,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **seeded}


@router.post("/connector-benchmarks/seed-and-smoke")
async def seed_and_smoke_connector_benchmark(body: ConnectorBenchmarkSeedAndSmokeRequest):
    seeded = await seed_connector_benchmark_endpoint(body)
    benchmark = seeded["benchmark"]
    agent = seeded["agent"]
    report = await run_connector_runtime_smoke(
        benchmark_id=str(benchmark.get("benchmarkId") or ""),
        agent_id=str(agent.get("agentId") or ""),
        task_keys=body.taskKeys or None,
    )
    return {"success": report["failed"] == 0, "benchmark": benchmark, "agent": agent, "tasks": seeded["tasks"], "runtimeSmoke": report}


@router.post("/benchmarks/{benchmark_id}/connector-runtime-smoke")
async def run_connector_benchmark_smoke(benchmark_id: str, body: ConnectorBenchmarkSmokeRequest):
    benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0})
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    agent_id = body.agentId or str(benchmark.get("agentId") or "")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    report = await run_connector_runtime_smoke(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=body.taskKeys or None,
    )
    return {"success": report["failed"] == 0, "runtimeSmoke": report}


@router.post("/benchmarks/{benchmark_id}/connector-harvest-and-smoke")
async def harvest_and_smoke_connector_benchmark_endpoint(benchmark_id: str, body: ConnectorBenchmarkSmokeRequest):
    benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0})
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    agent_id = body.agentId or str(benchmark.get("agentId") or "")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    report = await harvest_and_smoke_connector_benchmark(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=body.taskKeys or None,
        approve_skills=body.approveSkills,
    )
    return {"success": report["success"], "report": report}


@router.post("/benchmarks")
async def create_benchmark(body: BenchmarkCreateRequest):
    name = body.name.strip()
    if not body.email.strip():
        raise HTTPException(status_code=400, detail="email is required")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    now = _now()
    benchmark_id = str(uuid4())
    agent_name = body.agentName or await _agent_name(body.agentId, "")
    doc = {
        "benchmarkId": benchmark_id,
        "email": body.email,
        "companyId": body.companyId,
        "agentId": body.agentId,
        "agentName": agent_name if body.agentId else body.agentName,
        "name": name,
        "description": body.description,
        "websiteUrl": body.websiteUrl,
        "source": "manual",
        "createdAt": now,
        "updatedAt": now,
    }
    await benchmarks_collection.insert_one(doc)
    return {"success": True, "benchmark": doc}


@router.post("/benchmarks/{benchmark_id}/tasks")
async def create_benchmark_task(benchmark_id: str, body: BenchmarkTaskCreateRequest):
    benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0})
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    prompt = body.prompt.strip()
    name = body.name.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    now = _now()
    metadata = dict(body.metadata or {})
    initial_url = body.initialUrl.strip()
    if initial_url:
        metadata["startUrl"] = initial_url
    if body.businessIntent.strip():
        metadata["businessIntent"] = body.businessIntent.strip()
    if body.allowedSystems:
        metadata["allowedSystems"] = [str(item).strip() for item in body.allowedSystems if str(item).strip()]
    if body.expectedArtifacts:
        metadata["expectedArtifacts"] = [str(item).strip() for item in body.expectedArtifacts if str(item).strip()]
    if body.riskClass.strip():
        metadata["riskClass"] = body.riskClass.strip()
    if body.initialState:
        metadata["initialState"] = body.initialState
    task = {
        "taskId": str(uuid4()),
        "email": body.email or benchmark.get("email", ""),
        "companyId": body.companyId or benchmark.get("companyId", ""),
        "agentId": body.agentId or benchmark.get("agentId", ""),
        "benchmarkId": benchmark_id,
        "name": name or prompt[:80],
        "taskName": name or prompt[:80],
        "prompt": prompt,
        "successCriteria": body.successCriteria,
        "judgeType": _clean_judge_type(body.judgeType),
        "metadata": metadata,
        "status": "pending",
        "source": "manual",
        "createdAt": now,
        "updatedAt": now,
    }
    await benchmark_tasks_collection.insert_one(task)
    return {"success": True, "task": _task_to_eval(task, benchmark)}


@router.post("/benchmarks/{benchmark_id}/runs")
async def create_benchmark_run(benchmark_id: str, body: BenchmarkRunCreateRequest):
    eval_cursor = evals_collection.find(
        {
            "$or": [
                {"benchmarkId": benchmark_id},
                {"agentId": benchmark_id},
            ]
        },
        {"_id": 0},
    ).sort("createdAt", 1)
    evals = await eval_cursor.to_list(length=200)
    if not evals:
        task_cursor = benchmark_tasks_collection.find({"benchmarkId": benchmark_id}, {"_id": 0}).sort("createdAt", 1)
        tasks = await task_cursor.to_list(length=200)
        benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0}) or {}
        evals = [_task_to_eval(task, benchmark) for task in tasks]
    if not evals:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    benchmark_run_id = str(uuid4())
    created = []
    now = datetime.now(timezone.utc).isoformat()
    selected_agent_id = str(body.agentId or "")
    selected_agent_name = await _agent_name(selected_agent_id, body.agentName)
    for ev in evals:
        run_id = str(uuid4())
        doc = {
            "runId": run_id,
            "benchmarkRunId": benchmark_run_id,
            "evalId": ev.get("evalId", ""),
            "email": ev.get("email", ""),
            "benchmarkId": ev.get("benchmarkId", ev.get("agentId", "")),
            "benchmarkName": ev.get("benchmarkName", ev.get("agentName", "")),
            "agentId": selected_agent_id,
            "agentName": selected_agent_name,
            "agentTaskName": ev.get("agentTaskName", ""),
            "sessionId": body.sessionId,
            "actions": [],
            "label": "pending",
            "judgeType": _clean_judge_type(ev.get("judgeType")),
            "labelSource": "manual_review" if _clean_judge_type(ev.get("judgeType")) == "manual" else "llm_pending",
            "screenshots": [],
            "createdAt": now,
        }
        await eval_runs_collection.insert_one(doc)
        created.append(
            {
                "runId": run_id,
                "evalId": ev.get("evalId", ""),
                "prompt": ev.get("prompt", ""),
                "initialUrl": ev.get("initialUrl", ""),
                "agentTaskName": ev.get("agentTaskName", ""),
            }
        )
    return {"success": True, "benchmarkRunId": benchmark_run_id, "runs": created}


@router.get("/evals/{eval_id}")
async def get_eval(eval_id: str):
    doc = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not doc:
        doc = await _benchmark_task_eval(eval_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Eval not found")
    return {"eval": doc}


@router.post("/evals")
async def create_eval(body: EvalCreateRequest):
    eval_id = str(uuid4())
    doc = {
        "evalId": eval_id,
        "email": body.email,
        "prompt": body.prompt,
        "initialUrl": body.initialUrl,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await evals_collection.insert_one(doc)
    return {"success": True, "evalId": eval_id}


@router.delete("/evals/{eval_id}")
async def delete_eval(eval_id: str):
    result = await evals_collection.delete_one({"evalId": eval_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Eval not found")
    # Also delete all runs for this eval
    await eval_runs_collection.delete_many({"evalId": eval_id})
    return {"success": True}


# ── Eval run endpoints ──


@router.get("/evals/{eval_id}/runs")
async def list_runs(eval_id: str):
    cursor = eval_runs_collection.find(
        {"evalId": eval_id},
        {"_id": 0, "actions": 0},
    ).sort("createdAt", -1)
    runs = await cursor.to_list(length=500)
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not ev:
        ev = await _benchmark_task_eval(eval_id)
    for run in runs:
        run["judgeType"] = _clean_judge_type(run.get("judgeType") or (ev or {}).get("judgeType"))
        run["labelSource"] = run.get("labelSource") or ("manual_review" if run["judgeType"] == "manual" else "llm_pending")
    return {"runs": runs}


@router.post("/evals/{eval_id}/runs")
async def create_run(eval_id: str, body: RunCreateRequest):
    # Verify eval exists
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not ev:
        ev = await _benchmark_task_eval(eval_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Eval not found")

    run_id = str(uuid4())
    selected_agent_id = str(body.agentId or "")
    selected_agent_name = await _agent_name(selected_agent_id, body.agentName)
    doc = {
        "runId": run_id,
        "evalId": eval_id,
        "benchmarkRunId": "",
        "email": ev.get("email", ""),
        "benchmarkId": ev.get("benchmarkId", ev.get("agentId", "")),
        "benchmarkName": ev.get("benchmarkName", ev.get("agentName", "")),
        "agentId": selected_agent_id,
        "agentName": selected_agent_name,
        "agentTaskName": ev.get("agentTaskName", ""),
        "sessionId": body.sessionId,
        "actions": [],
        "label": "pending",
        "judgeType": _clean_judge_type(ev.get("judgeType")),
        "labelSource": "manual_review" if _clean_judge_type(ev.get("judgeType")) == "manual" else "llm_pending",
        "screenshots": [],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await eval_runs_collection.insert_one(doc)
    return {"success": True, "runId": run_id}


@router.get("/evals/{eval_id}/runs/{run_id}")
async def get_run(eval_id: str, run_id: str):
    doc = await eval_runs_collection.find_one({"runId": run_id, "evalId": eval_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": doc}


@router.put("/evals/{eval_id}/runs/{run_id}")
async def update_run(eval_id: str, run_id: str, body: RunUpdateRequest):
    update = {}
    if body.label is not None:
        if body.label not in ("pass", "fail", "pending"):
            raise HTTPException(status_code=400, detail="Label must be 'pass', 'fail', or 'pending'")
        update["label"] = body.label
        update["labelSource"] = "manual_override" if body.label in {"pass", "fail"} else "manual_review"
        update["manualOverride"] = body.label in {"pass", "fail"}
        update["reviewedAt"] = _now()
    if body.actions is not None:
        update["actions"] = body.actions
    if body.sessionId is not None:
        update["sessionId"] = body.sessionId
    if body.screenshots is not None:
        update["screenshots"] = body.screenshots

    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")

    result = await eval_runs_collection.update_one({"runId": run_id, "evalId": eval_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True}


@router.post("/evals/{eval_id}/runs/{run_id}/judge")
async def judge_run(eval_id: str, run_id: str, body: JudgeRunRequest):
    ev = await evals_collection.find_one({"evalId": eval_id}, {"_id": 0})
    if not ev:
        ev = await _benchmark_task_eval(eval_id)
    run = await eval_runs_collection.find_one({"runId": run_id, "evalId": eval_id}, {"_id": 0})
    if not ev or not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    judge_type = _clean_judge_type(ev.get("judgeType") or run.get("judgeType"))
    if judge_type != "llm" and not body.force:
        raise HTTPException(status_code=400, detail="This task is configured for manual review. Change the task judge to LLMJudge or call with force=true.")
    judgement = await judge_eval_run(run=run, eval_doc=ev, user_context=body.userContext)
    if body.apply:
        await eval_runs_collection.update_one(
            {"runId": run_id, "evalId": eval_id},
            {"$set": {"label": judgement["label"], "judge": judgement, "judgeType": "llm", "labelSource": "llm_judge", "judgedAt": _now()}},
        )
    return {"success": True, "judgement": judgement}


@router.delete("/evals/{eval_id}/runs/{run_id}")
async def delete_run(eval_id: str, run_id: str):
    result = await eval_runs_collection.delete_one({"runId": run_id, "evalId": eval_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"success": True}
