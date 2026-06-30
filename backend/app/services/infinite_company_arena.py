from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from app.models.ica import (
    ExpectedSurface,
    IcaBenchmarkMode,
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaEvaluationMetric,
    IcaEvaluationResult,
    IcaExpectedHarvest,
    IcaMaterializedProject,
    IcaMinimumMetric,
)
from app.services import company_harvester


ROOT = Path(__file__).resolve().parents[3]
DEMO_PROJECTS_ROOT = ROOT / "demo_projects"


def _absolute_url(base_url: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return base_url.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def load_ica_project(path: str | Path) -> IcaDemoProject:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "project.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return IcaDemoProject.model_validate(data)


def project_path(project_id: str) -> Path:
    return DEMO_PROJECTS_ROOT / project_id


def load_demo_project(project_id: str) -> IcaDemoProject:
    return load_ica_project(project_path(project_id))


def legacy_web_demo_project(
    *,
    project_id: str,
    name: str,
    base_url: str,
    task_name: str = "Explore web workflow",
    task_prompt: str = "Use the web UI to discover and complete the primary workflow.",
) -> IcaDemoProject:
    return IcaDemoProject.model_validate(
        {
            "projectId": project_id,
            "name": name,
            "description": "Web-only ICA wrapper for a legacy autoppia_webs_demo project.",
            "industry": "legacy web automation benchmark",
            "defaultBaseUrl": base_url,
            "surfaces": [
                {
                    "surfaceId": f"{project_id}-web",
                    "kind": "web",
                    "name": f"{name} Web",
                    "url": "/",
                    "description": "Legacy demo web exposed as a web-only ICA surface.",
                    "metadata": {"legacyDemoWeb": True},
                }
            ],
            "tasks": [
                {
                    "taskId": "legacy_web_primary_workflow",
                    "name": task_name,
                    "prompt": task_prompt,
                    "successCriteria": "Completes the requested workflow using browser actions.",
                    "expectedSurfaces": ["web"],
                    "riskClass": "write",
                }
            ],
            "expectedHarvest": {
                "connectors": ["web"],
                "minimumTaskCount": 1,
                "minimumToolCount": 1,
                "requiresBrowserTasks": True,
            },
            "benchmarkModes": [
                {
                    "modeId": "web_only",
                    "description": "Legacy demo web adapter mode.",
                    "surfaceFilter": ["web"],
                    "taskIds": ["legacy_web_primary_workflow"],
                    "expectedHarvest": {
                        "connectors": ["web"],
                        "minimumTaskCount": 1,
                        "minimumToolCount": 1,
                        "requiresBrowserTasks": True,
                    },
                }
            ],
        }
    )


def _openapi_metadata(manifest_path: Path, surface_url: str) -> dict[str, Any]:
    candidate = manifest_path.parent / surface_url.lstrip("/")
    if candidate.exists() and candidate.suffix == ".json":
        return {"openApiUrl": surface_url, "openapi": json.loads(candidate.read_text(encoding="utf-8"))}
    if surface_url.endswith("/openapi.json"):
        return {"openApiUrl": surface_url}
    return {}


def _surface_kind_to_expected(kind: str) -> ExpectedSurface:
    if kind == "web":
        return "web"
    if kind in {"openapi", "api_docs"}:
        return "api"
    if kind in {"document_url", "file", "knowledge_note"}:
        return "documents"
    return "other"


def _mode_for(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None) -> IcaBenchmarkMode | None:
    if not mode:
        return None
    for item in project.benchmarkModes:
        if item.modeId == mode:
            return item
    raise ValueError(f"ICA project {project.projectId!r} does not define benchmark mode {mode!r}")


def _mode_expected_harvest(project: IcaDemoProject, mode_config: IcaBenchmarkMode | None) -> IcaExpectedHarvest:
    if not mode_config:
        return project.expectedHarvest
    if mode_config.expectedHarvest != IcaExpectedHarvest():
        return mode_config.expectedHarvest
    return project.expectedHarvest


def materialize_project(
    project: IcaDemoProject,
    *,
    manifest_path: str | Path | None = None,
    base_url: str = "",
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaMaterializedProject:
    root = Path(manifest_path).parent if manifest_path else project_path(project.projectId)
    resolved_base = base_url or project.defaultBaseUrl
    mode_config = _mode_for(project, mode)
    surface_filter = set(mode_config.surfaceFilter if mode_config else [])
    task_filter = set(mode_config.taskIds if mode_config else [])
    expected_harvest = _mode_expected_harvest(project, mode_config)
    selected_tasks = [
        task
        for task in project.tasks
        if (not task_filter or task.taskId in task_filter)
        and (not surface_filter or bool(set(task.expectedSurfaces) & surface_filter))
    ]
    materials: list[dict[str, Any]] = []

    for surface in project.surfaces:
        if surface_filter and _surface_kind_to_expected(surface.kind) not in surface_filter:
            continue
        url = _absolute_url(resolved_base, surface.url)
        material_kind = "website" if surface.kind == "web" else surface.kind
        metadata = {
            **surface.metadata,
            "icaProjectId": project.projectId,
            "icaSurfaceId": surface.surfaceId,
            "authRequired": surface.authRequired,
            "description": surface.description,
        }
        if surface.kind in {"openapi", "api_docs"}:
            metadata.update(_openapi_metadata(root / "project.json", surface.url))
            metadata["connector"] = {
                "name": surface.name,
                "type": "api",
                "surface": "api",
                "authRequired": surface.authRequired,
                "docsUrl": url,
            }
        if surface.kind == "web":
            metadata["uiTaskHints"] = [
                {
                    "name": task.name,
                    "prompt": task.prompt,
                    "successCriteria": task.successCriteria,
                    "riskClass": task.riskClass,
                    "expectedSurfaces": task.expectedSurfaces,
                }
                for task in project.tasks
                if task in selected_tasks
                if "web" in task.expectedSurfaces
            ]
        material: dict[str, Any] = {
            "kind": material_kind,
            "name": surface.name,
            "url": url,
            "metadata": metadata,
        }
        if surface.kind in {"document_url", "file", "knowledge_note"}:
            local_doc = root / surface.url.lstrip("/")
            if local_doc.exists():
                material["content"] = local_doc.read_text(encoding="utf-8")
        materials.append(material)

    if project.auth.required:
        materials.append(
            {
                "kind": "auth_note",
                "name": f"{project.name} owner auth",
                "content": project.auth.instructions,
                "metadata": {
                    "authConfigured": True,
                    "username": project.auth.username,
                    "credentialRef": f"ica:{project.projectId}:owner",
                    "authKind": project.auth.kind,
                },
            }
        )

    user_tasks = [
        {
            "name": task.name,
            "prompt": task.prompt,
            "successCriteria": task.successCriteria,
            "riskClass": task.riskClass,
            "metadata": {
                **task.metadata,
                "icaProjectId": project.projectId,
                "icaTaskId": task.taskId,
                "expectedSurfaces": task.expectedSurfaces,
                "requiresBrowser": "web" in task.expectedSurfaces,
                "prefersApi": "api" in task.expectedSurfaces,
                "usesKnowledge": "documents" in task.expectedSurfaces,
                "expectedTools": [
                    *([f"{project.projectId}.web.explore_workflows"] if "web" in task.expectedSurfaces else []),
                    *(["knowledge.company_docs.search"] if "documents" in task.expectedSurfaces else []),
                ],
            },
        }
        for task in selected_tasks
    ]
    return IcaMaterializedProject(project=project, materials=materials, userTasks=user_tasks, expectedHarvest=expected_harvest, mode=mode)


class IcaCompanyHarvestRunner(Protocol):
    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
    ) -> dict[str, Any]:
        ...


async def _cursor_to_list(cursor: Any, length: int = 1000) -> list[dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return [dict(item) for item in await cursor.to_list(length=length)]
    return [dict(item) for item in cursor]


async def _company_harvest_snapshot(company_id: str, intake_id: str) -> dict[str, list[dict[str, Any]]]:
    connectors = await _cursor_to_list(company_harvester.connectors_collection.find({"companyId": company_id}))
    connector_ids = [str(item.get("connectorId") or "") for item in connectors if item.get("connectorId")]
    tools = await _cursor_to_list(company_harvester.tools_collection.find({"connectorId": {"$in": connector_ids}})) if connector_ids else []
    benchmarks = await _cursor_to_list(company_harvester.benchmarks_collection.find({"companyId": company_id}))
    benchmark_ids = [str(item.get("benchmarkId") or "") for item in benchmarks if item.get("benchmarkId")]
    tasks = await _cursor_to_list(company_harvester.benchmark_tasks_collection.find({"benchmarkId": {"$in": benchmark_ids}})) if benchmark_ids else []
    return {
        "connectors": connectors,
        "tools": tools,
        "benchmarks": benchmarks,
        "tasks": tasks,
        "intakes": await _cursor_to_list(company_harvester.company_intakes_collection.find({"intakeId": intake_id})),
    }


class CompanyHarvesterIcaRunner:
    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
    ) -> dict[str, Any]:
        materialized = materialize_project(project, base_url=base_url, mode=mode)
        intake = await company_harvester.create_company_intake(
            email=email,
            company_id=company_id,
            company_name=project.name,
            description=project.description,
            materials=materialized.materials,
            user_tasks=materialized.userTasks,
            mode="dev",
        )
        run = await company_harvester.start_company_harvest(intake["intakeId"], email=email, mode="dev")
        if process:
            run = await company_harvester.process_company_harvest_run(run["runId"])
        snapshot = await _company_harvest_snapshot(company_id, intake["intakeId"])
        return {
            "project": project.model_dump(),
            "materialized": materialized.model_dump(),
            "intake": intake,
            "run": run,
            "snapshot": snapshot,
            "expectedHarvest": materialized.expectedHarvest.model_dump(),
        }


def evaluate_company_harvest_snapshot(
    *,
    project: IcaDemoProject,
    snapshot: dict[str, list[dict[str, Any]]],
    expected_harvest: IcaExpectedHarvest | None = None,
    run: dict[str, Any] | None = None,
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaEvaluationResult:
    expected = expected_harvest or project.expectedHarvest
    found_connectors = sorted({str(item.get("type") or "") for item in snapshot.get("connectors", []) if item.get("type")})
    expected_connectors = sorted(set(expected.connectors))
    missing: list[str] = []
    connector_missing = [item for item in expected_connectors if item not in found_connectors]
    missing.extend(f"connector:{item}" for item in connector_missing)

    tool_count = len(snapshot.get("tools", []))
    task_count = len(snapshot.get("tasks", []))
    benchmark_count = len(snapshot.get("benchmarks", []))
    if tool_count < expected.minimumToolCount:
        missing.append(f"tools:{tool_count}/{expected.minimumToolCount}")
    if task_count < expected.minimumTaskCount:
        missing.append(f"tasks:{task_count}/{expected.minimumTaskCount}")
    if benchmark_count < 1 and expected.minimumTaskCount > 0:
        missing.append("benchmark:0/1")

    if expected.requiresKnowledge and "knowledge" not in found_connectors:
        missing.append("knowledge:required")
    if expected.requiresApiTools and "api" not in found_connectors:
        missing.append("api_tools:required")
    if expected.requiresBrowserTasks and "web" not in found_connectors:
        missing.append("browser_tasks:required")

    checks = [
        not connector_missing,
        tool_count >= expected.minimumToolCount,
        task_count >= expected.minimumTaskCount,
        benchmark_count >= (1 if expected.minimumTaskCount > 0 else 0),
        (not expected.requiresKnowledge or "knowledge" in found_connectors),
        (not expected.requiresApiTools or "api" in found_connectors),
        (not expected.requiresBrowserTasks or "web" in found_connectors),
    ]
    passed_checks = sum(1 for item in checks if item)
    score = round(passed_checks / len(checks), 4) if checks else 1.0
    compact_run = {
        key: value
        for key, value in (run or {}).items()
        if key in {"runId", "intakeId", "status", "currentStep", "nextAction", "normalSummary", "errors"}
    }
    return IcaEvaluationResult(
        projectId=project.projectId,
        mode=mode,
        passed=not missing,
        score=score,
        connectors=IcaEvaluationMetric(
            expected=expected_connectors,
            found=found_connectors,
            missing=connector_missing,
            passed=not connector_missing,
        ),
        tools=IcaMinimumMetric(minimum=expected.minimumToolCount, found=tool_count, passed=tool_count >= expected.minimumToolCount),
        tasks=IcaMinimumMetric(minimum=expected.minimumTaskCount, found=task_count, passed=task_count >= expected.minimumTaskCount),
        benchmarks=IcaMinimumMetric(minimum=1 if expected.minimumTaskCount > 0 else 0, found=benchmark_count, passed=benchmark_count >= (1 if expected.minimumTaskCount > 0 else 0)),
        missing=missing,
        run=compact_run,
    )


async def evaluate_project_company_harvest(
    project: IcaDemoProject,
    *,
    email: str,
    company_id: str,
    base_url: str = "",
    mode: IcaBenchmarkModeKind | None = None,
    process: bool = True,
    runner: IcaCompanyHarvestRunner | None = None,
) -> IcaEvaluationResult:
    runner = runner or CompanyHarvesterIcaRunner()
    result = await runner.run(
        project,
        email=email,
        company_id=company_id,
        base_url=base_url,
        mode=mode,
        process=process,
    )
    expected = IcaExpectedHarvest.model_validate(result.get("expectedHarvest") or project.expectedHarvest.model_dump())
    return evaluate_company_harvest_snapshot(
        project=project,
        snapshot=result.get("snapshot") or {},
        expected_harvest=expected,
        run=result.get("run") or {},
        mode=mode,
    )


async def seed_company_harvester_from_project(
    project: IcaDemoProject,
    *,
    email: str,
    company_id: str,
    base_url: str = "",
    mode: IcaBenchmarkModeKind | None = None,
    process: bool = True,
) -> dict[str, Any]:
    materialized = materialize_project(project, base_url=base_url, mode=mode)
    intake = await company_harvester.create_company_intake(
        email=email,
        company_id=company_id,
        company_name=project.name,
        description=project.description,
        materials=materialized.materials,
        user_tasks=materialized.userTasks,
        mode="dev",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email=email, mode="dev")
    if process:
        run = await company_harvester.process_company_harvest_run(run["runId"])
    return {"project": project.model_dump(), "intake": intake, "run": run, "expectedHarvest": project.expectedHarvest.model_dump()}
