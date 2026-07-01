from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ica.demo_companies.loader import project_path
from ica.demo_companies.web_source_collector import web_snapshot_material
from ica.schemas import (
    ExpectedSurface,
    IcaBenchmarkMode,
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaExpectedHarvest,
    IcaMaterializedProject,
)


def _absolute_url(base_url: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return base_url.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


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
    if kind in {"code_repository", "code_file"}:
        return "code"
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
    include_ground_truth_tasks: bool = True,
    collect_web_snapshots: bool = False,
) -> IcaMaterializedProject:
    root = Path(manifest_path).parent if manifest_path else project_path(project.projectId)
    resolved_base = base_url or project.defaultBaseUrl
    mode_config = _mode_for(project, mode)
    surface_filter = set(mode_config.surfaceFilter if mode_config else [])
    task_filter = set(mode_config.taskIds if mode_config else [])
    expected_harvest = _mode_expected_harvest(project, mode_config)
    if task_filter:
        selected_tasks = [task for task in project.tasks if task.taskId in task_filter]
    else:
        selected_tasks = [
            task
            for task in project.tasks
            if not surface_filter or bool(set(task.expectedSurfaces) & surface_filter)
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
            if include_ground_truth_tasks:
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
        if surface.kind in {"document_url", "file", "knowledge_note", "code_repository", "code_file"}:
            local_doc = root / surface.url.lstrip("/")
            if local_doc.exists():
                material["content"] = local_doc.read_text(encoding="utf-8")
        materials.append(material)
        if surface.kind == "web" and collect_web_snapshots:
            materials.append(
                web_snapshot_material(
                    name=surface.name,
                    url=url,
                    metadata={
                        "icaProjectId": project.projectId,
                        "icaSurfaceId": surface.surfaceId,
                        "sourceSurfaceKind": "web",
                        "groundTruthFree": True,
                    },
                )
            )

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

    user_tasks = [] if not include_ground_truth_tasks else [
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
                "usesCode": "code" in (mode_config.discoveryInput if mode_config else []) or "code" in task.expectedSurfaces,
                "expectedTools": [
                    *([f"{project.projectId}.web.explore_workflows"] if "web" in task.expectedSurfaces else []),
                    *(["knowledge.company_docs.search"] if "documents" in task.expectedSurfaces else []),
                ],
            },
        }
        for task in selected_tasks
    ]
    return IcaMaterializedProject(project=project, materials=materials, userTasks=user_tasks, expectedHarvest=expected_harvest, mode=mode)

