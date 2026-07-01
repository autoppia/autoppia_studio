from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.company_harvesters import list_company_harvesters
from app.models.ica import IcaBenchmarkModeKind
from app.services import infinite_company_arena as ica


router = APIRouter(prefix="/ica", tags=["ica"])

_RUNS_PATH = ica.ROOT / "logs" / "ica_runs.json"
_MAX_RUNS = 100


def _load_runs() -> list[dict[str, Any]]:
    if not _RUNS_PATH.exists():
        return []
    try:
        data = json.loads(_RUNS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _save_runs() -> None:
    _RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RUNS_PATH.write_text(json.dumps(_RUNS[:_MAX_RUNS], indent=2), encoding="utf-8")


_RUNS: list[dict[str, Any]] = _load_runs()


class IcaRunRequest(BaseModel):
    harvesterNames: list[str] = Field(default_factory=list)
    projectIds: list[str] = Field(default_factory=list)
    modeIds: list[IcaBenchmarkModeKind] = Field(default_factory=list)
    canonicalModeOnly: bool = False
    email: str = "ica-owner@example.com"
    baseUrl: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_manifest_paths() -> list[Path]:
    return ica.demo_company_manifest_paths()


def _public_project(project: Any) -> dict[str, Any]:
    surfaces = [surface.model_dump(mode="json") for surface in project.surfaces]
    modes = [mode.model_dump(mode="json") for mode in project.benchmarkModes]
    return {
        "projectId": project.projectId,
        "name": project.name,
        "version": project.version,
        "description": project.description,
        "industry": project.industry,
        "defaultBaseUrl": project.defaultBaseUrl,
        "authRequired": project.auth.required,
        "surfaceKinds": sorted({surface.kind for surface in project.surfaces}),
        "surfaces": surfaces,
        "taskCount": len(project.tasks),
        "tasks": [task.model_dump(mode="json") for task in project.tasks],
        "benchmarkModes": modes,
        "expectedHarvest": project.expectedHarvest.model_dump(mode="json"),
        "metadata": project.metadata,
    }


def _load_projects(project_ids: list[str] | None = None) -> list[Any]:
    requested = set(project_ids or [])
    projects = []
    for manifest_path in _project_manifest_paths():
        project = ica.load_ica_project(manifest_path)
        if requested and project.projectId not in requested:
            continue
        projects.append(project)
    missing = requested - {project.projectId for project in projects}
    if missing:
        raise HTTPException(status_code=404, detail={"missingProjectIds": sorted(missing)})
    return projects


def _run_modes_for(project: Any, requested_modes: list[IcaBenchmarkModeKind]) -> list[IcaBenchmarkModeKind | None]:
    supported = [mode.modeId for mode in project.benchmarkModes]
    if requested_modes:
        return [mode for mode in requested_modes if mode in supported]
    if supported:
        return supported
    return [None]


def _canonical_run_modes_for(project: Any) -> list[IcaBenchmarkModeKind | None]:
    supported = [mode.modeId for mode in project.benchmarkModes]
    if "all_sources" in supported:
        return ["all_sources"]
    if "hybrid" in supported:
        return ["hybrid"]
    if "web_api_documents" in supported:
        return ["web_api_documents"]
    if "web_api_code" in supported:
        return ["web_api_code"]
    if "web_only" in supported:
        return ["web_only"]
    if "api_only" in supported:
        return ["api_only"]
    if supported:
        return [supported[0]]
    return [None]


def _summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result") or {}
    phases = result.get("phases") or {}
    task_discovery = phases.get("taskDiscovery") or {}
    solution_discovery = phases.get("solutionDiscovery") or {}
    agent_execution = phases.get("agentExecution") or {}
    inventory = phases.get("inventory") or {}
    task_missing = task_discovery.get("missingTaskIds") or []
    task_extra = task_discovery.get("extraTaskNames") or []
    solution_missing = solution_discovery.get("missingTaskIds") or []
    solution_incomplete = solution_discovery.get("incompleteTaskIds") or []
    invalid_origins = solution_discovery.get("invalidOriginIds") or []
    hallucinated_tools = solution_discovery.get("hallucinatedToolNames") or []
    hallucinated_connectors = solution_discovery.get("hallucinatedConnectorIds") or []
    inventory_missing = inventory.get("missing") or []
    project_tasks = run.get("projectTasks") or []
    return {
        "runId": run["runId"],
        "runGroupId": run["runGroupId"],
        "createdAt": run["createdAt"],
        "status": run["status"],
        "error": run.get("error") or "",
        "harvesterName": run["harvesterName"],
        "projectId": run["projectId"],
        "projectName": run["projectName"],
        "mode": run["mode"],
        "passed": result.get("passed", False),
        "score": result.get("score", 0.0),
        "taskDiscoveryPassed": task_discovery.get("passed", False),
        "taskDiscoveryScore": task_discovery.get("score", 0.0),
        "taskRecall": task_discovery.get("recall", 0.0),
        "taskPrecision": task_discovery.get("precision", 0.0),
        "matchedTasks": task_discovery.get("matchedCount", 0),
        "expectedTasks": task_discovery.get("expectedCount", 0),
        "taskMissingTaskIds": task_missing,
        "taskExtraTaskNames": task_extra,
        "taskDiscoveryMatches": task_discovery.get("matches") or [],
        "taskDiscoveredCount": task_discovery.get("discoveredCount", 0),
        "projectTasks": project_tasks,
        "solutionDiscoveryPassed": solution_discovery.get("passed", False),
        "solutionScore": solution_discovery.get("score", 0.0),
        "solutionCount": solution_discovery.get("solutionCount", 0),
        "expectedSolutionTasks": solution_discovery.get("expectedTaskCount", 0),
        "solutionExtraTaskIds": solution_discovery.get("extraSolutionTaskIds") or [],
        "solutionMissingTaskIds": solution_missing,
        "solutionIncompleteTaskIds": solution_incomplete,
        "solutionInvalidOriginIds": invalid_origins,
        "solutionHallucinatedToolNames": hallucinated_tools,
        "solutionHallucinatedConnectorIds": hallucinated_connectors,
        "solutionIncompleteReasons": solution_discovery.get("incompleteReasons") or {},
        "solutionDiscoverySolutions": solution_discovery.get("solutions") or [],
        "agentExecutionApplicable": agent_execution.get("applicable", False),
        "agentExecutionSkippedReason": agent_execution.get("skippedReason", ""),
        "agentExecutionMode": agent_execution.get("executionMode", "none"),
        "agentRuntimeExecuted": agent_execution.get("runtimeExecuted", False),
        "agentExecutionPassed": agent_execution.get("passed", True),
        "agentExecutionScore": agent_execution.get("score", 1.0),
        "agentExecutionExpectedTasks": agent_execution.get("expectedTaskCount", 0),
        "agentExecutionExecutedTasks": agent_execution.get("executedTaskCount", 0),
        "agentExecutionPassedTaskIds": agent_execution.get("passedTaskIds") or [],
        "agentExecutionFailedTaskIds": agent_execution.get("failedTaskIds") or [],
        "agentExecutionResults": agent_execution.get("results") or [],
        "inventoryPassed": inventory.get("passed", False),
        "inventoryScore": inventory.get("score", 0.0),
        "inventoryMissing": inventory_missing,
        "missing": [
            *task_missing,
            *solution_missing,
            *solution_incomplete,
            *invalid_origins,
            *hallucinated_tools,
            *hallucinated_connectors,
            *inventory_missing,
        ],
    }


@router.get("/harvesters")
async def get_harvesters() -> dict[str, Any]:
    return {"harvesters": list_company_harvesters()}


@router.get("/demo-companies")
async def get_demo_companies() -> dict[str, Any]:
    projects = [_public_project(project) for project in _load_projects()]
    return {"demoCompanies": projects}


@router.get("/runs")
async def get_runs() -> dict[str, Any]:
    return {"runs": [_summarize_run(run) for run in _RUNS]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    for run in _RUNS:
        if run["runId"] == run_id:
            return run
    raise HTTPException(status_code=404, detail="ICA run not found")


@router.post("/runs")
async def start_runs(request: IcaRunRequest) -> dict[str, Any]:
    harvesters = list_company_harvesters()
    available_harvesters = {str(item["name"]) for item in harvesters}
    harvester_names = request.harvesterNames or sorted(available_harvesters)
    unknown_harvesters = sorted(set(harvester_names) - available_harvesters)
    if unknown_harvesters:
        raise HTTPException(status_code=404, detail={"missingHarvesterNames": unknown_harvesters})

    projects = _load_projects(request.projectIds)
    run_group_id = f"ica-run-group-{uuid4().hex[:10]}"
    created_runs: list[dict[str, Any]] = []

    for harvester_name in harvester_names:
        for project in projects:
            modes = _canonical_run_modes_for(project) if request.canonicalModeOnly else _run_modes_for(project, request.modeIds)
            for mode in modes:
                materialized = ica.materialize_project(project, base_url=request.baseUrl, mode=mode, include_ground_truth_tasks=True)
                project_tasks = [
                    {
                        "taskId": str((task.get("metadata") or {}).get("icaTaskId") or task.get("taskId") or task.get("id") or ""),
                        "name": task.get("name", ""),
                        "prompt": task.get("prompt", ""),
                        "successCriteria": task.get("successCriteria", ""),
                        "expectedSurfaces": (task.get("metadata") or {}).get("expectedSurfaces") or [],
                        "riskClass": task.get("riskClass", "read"),
                        "metadata": task.get("metadata") or {},
                    }
                    for task in materialized.userTasks
                ]
                run_id = f"ica-run-{uuid4().hex[:12]}"
                record = {
                    "runId": run_id,
                    "runGroupId": run_group_id,
                    "createdAt": _utc_now(),
                    "status": "running",
                    "harvesterName": harvester_name,
                    "projectId": project.projectId,
                    "projectName": project.name,
                    "projectTasks": project_tasks,
                    "mode": mode,
                    "result": None,
                    "error": None,
                }
                try:
                    company_id = f"ica:{project.projectId}:{harvester_name}:{mode or 'default'}:{uuid4().hex[:8]}"
                    result = await ica.evaluate_project_company_harvest(
                        project,
                        email=request.email,
                        company_id=company_id,
                        base_url=request.baseUrl,
                        mode=mode,
                        runner=ica.CompanyHarvesterEngineIcaRunner(harvester_name),
                    )
                    record["status"] = "completed"
                    record["result"] = result.model_dump(mode="json")
                except Exception as exc:  # pragma: no cover - defensive API boundary
                    record["status"] = "failed"
                    record["error"] = str(exc)
                created_runs.append(record)

    _RUNS[:0] = created_runs
    del _RUNS[_MAX_RUNS:]
    _save_runs()
    return {
        "runGroupId": run_group_id,
        "runs": [_summarize_run(run) for run in created_runs],
    }
