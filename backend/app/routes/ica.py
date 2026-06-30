from __future__ import annotations

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

_RUNS: list[dict[str, Any]] = []
_MAX_RUNS = 100


class IcaRunRequest(BaseModel):
    harvesterNames: list[str] = Field(default_factory=list)
    projectIds: list[str] = Field(default_factory=list)
    modeIds: list[IcaBenchmarkModeKind] = Field(default_factory=list)
    email: str = "ica-owner@example.com"
    baseUrl: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_manifest_paths() -> list[Path]:
    root = ica.DEMO_PROJECTS_ROOT
    if not root.exists():
        return []
    return sorted(path / "project.json" for path in root.iterdir() if (path / "project.json").exists())


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


def _summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result") or {}
    phases = result.get("phases") or {}
    task_discovery = phases.get("taskDiscovery") or {}
    solution_discovery = phases.get("solutionDiscovery") or {}
    inventory = phases.get("inventory") or {}
    return {
        "runId": run["runId"],
        "runGroupId": run["runGroupId"],
        "createdAt": run["createdAt"],
        "status": run["status"],
        "harvesterName": run["harvesterName"],
        "projectId": run["projectId"],
        "projectName": run["projectName"],
        "mode": run["mode"],
        "passed": result.get("passed", False),
        "score": result.get("score", 0.0),
        "taskRecall": task_discovery.get("recall", 0.0),
        "taskPrecision": task_discovery.get("precision", 0.0),
        "matchedTasks": task_discovery.get("matchedCount", 0),
        "expectedTasks": task_discovery.get("expectedCount", 0),
        "solutionScore": solution_discovery.get("score", 0.0),
        "solutionCount": solution_discovery.get("solutionCount", 0),
        "inventoryScore": inventory.get("score", 0.0),
        "missing": [
            *(task_discovery.get("missingTaskIds") or []),
            *(solution_discovery.get("missingTaskIds") or []),
            *(inventory.get("missing") or []),
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
            modes = _run_modes_for(project, request.modeIds)
            for mode in modes:
                run_id = f"ica-run-{uuid4().hex[:12]}"
                record = {
                    "runId": run_id,
                    "runGroupId": run_group_id,
                    "createdAt": _utc_now(),
                    "status": "running",
                    "harvesterName": harvester_name,
                    "projectId": project.projectId,
                    "projectName": project.name,
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
    return {
        "runGroupId": run_group_id,
        "runs": [_summarize_run(run) for run in created_runs],
    }
