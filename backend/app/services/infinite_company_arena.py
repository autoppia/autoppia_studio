from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from app.models.agent_config import AgentCallable, AgentConfig, AgentTask
from app.company_harvesters import get_company_harvester
from app.models.company_harvester import CompanyHarvesterInput, CompanyHarvesterOutput, CompanyMaterial
from app.models.ica import (
    ExpectedSurface,
    IcaBenchmarkMode,
    IcaBenchmarkModeKind,
    IcaCompanyBenchmarkResult,
    IcaDemoProject,
    IcaEvaluationMetric,
    IcaEvaluationResult,
    IcaExpectedHarvest,
    IcaMaterializedProject,
    IcaMinimumMetric,
    IcaSolutionDiscoveryEvaluation,
    IcaTaskDiscoveryEvaluation,
    IcaTaskDiscoveryExpectation,
    IcaTaskDiscoveryMatch,
    IcaTaskSolutionSpec,
)
from app.runtimes.base import AgentRuntimeProfile
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
    include_ground_truth_tasks: bool = True,
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
        include_ground_truth_tasks: bool = False,
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
        include_ground_truth_tasks: bool = False,
    ) -> dict[str, Any]:
        materialized = materialize_project(project, base_url=base_url, mode=mode, include_ground_truth_tasks=include_ground_truth_tasks)
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


def _discovery_mode_for(mode: IcaBenchmarkModeKind | None) -> str:
    return {
        "web_only": "ui_only",
        "api_only": "ui_api_docs",
        "hybrid": "ui_api_docs",
    }.get(str(mode or ""), "full_company")


def _company_harvester_input_from_materialized(
    materialized: IcaMaterializedProject,
    *,
    company_id: str,
    include_ground_truth_tasks: bool = False,
) -> CompanyHarvesterInput:
    return CompanyHarvesterInput(
        companyId=company_id,
        companyName=materialized.project.name,
        description=materialized.project.description,
        materials=[CompanyMaterial.model_validate(material) for material in materialized.materials],
        discoveryMode=_discovery_mode_for(materialized.mode),  # type: ignore[arg-type]
        userTasks=materialized.userTasks if include_ground_truth_tasks else [],
        metadata={
            "icaProjectId": materialized.project.projectId,
            "icaMode": materialized.mode or "",
        },
    )


def _snapshot_from_company_harvester_output(output: CompanyHarvesterOutput) -> dict[str, list[dict[str, Any]]]:
    connector_docs = {
        connector.connectorId or connector.name or f"connector:{index}": {
            "connectorId": connector.connectorId or connector.name or f"connector:{index}",
            "name": connector.name,
            "type": connector.type,
            "surface": connector.surface,
            "authRequired": connector.authRequired,
            "runtimeRequirements": connector.runtimeRequirements,
            "source": "company_harvester_output",
        }
        for index, solution in enumerate(output.taskSolutions, start=1)
        for connector in solution.connectors
    }
    tool_docs = {
        tool.toolId or tool.name: {
            "toolId": tool.toolId or tool.name,
            "name": tool.name,
            "connectorId": tool.connectorId,
            "executionType": tool.executionType,
            "policyBoundary": tool.policyBoundary,
            "riskLevel": tool.riskLevel,
            "source": "company_harvester_output",
        }
        for solution in output.taskSolutions
        for tool in solution.tools
        if tool.name
    }
    tasks = [
        {
            "taskId": proposal.taskId,
            "name": proposal.name,
            "taskName": proposal.name,
            "prompt": proposal.prompt,
            "successCriteria": proposal.successCriteria,
            "riskClass": proposal.riskClass,
            "metadata": {
                **proposal.metadata,
                "expectedSurfaces": proposal.expectedSurfaces,
                "confidence": proposal.confidence,
                "evidence": proposal.evidence,
            },
            "source": "company_harvester_output",
        }
        for proposal in output.proposedTasks
    ]
    benchmarks = [
        {
            "benchmarkId": output.benchmarkId or "company_harvester_output:benchmark",
            "taskCount": len(tasks),
            "source": "company_harvester_output",
        }
    ] if tasks else []
    return {
        "connectors": list(connector_docs.values()),
        "tools": list(tool_docs.values()),
        "tasks": tasks,
        "benchmarks": benchmarks,
    }


class CompanyHarvesterEngineIcaRunner:
    def __init__(self, harvester_name: str = "local_heuristic") -> None:
        self.harvester_name = harvester_name

    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
        include_ground_truth_tasks: bool = False,
    ) -> dict[str, Any]:
        materialized = materialize_project(project, base_url=base_url, mode=mode, include_ground_truth_tasks=include_ground_truth_tasks)
        request = _company_harvester_input_from_materialized(
            materialized,
            company_id=company_id,
            include_ground_truth_tasks=include_ground_truth_tasks,
        )
        harvester = get_company_harvester(self.harvester_name)
        output = await harvester.harvest(request)
        snapshot = _snapshot_from_company_harvester_output(output)
        return {
            "project": project.model_dump(),
            "materialized": materialized.model_dump(),
            "intake": {"companyId": company_id, "email": email, "source": "company_harvester_engine"},
            "run": {
                "runId": f"{company_id}:{harvester.info().name}:ica",
                "status": "ready",
                "currentStep": "ready",
                "normalSummary": {
                    "companyHarvesterOutput": {
                        "proposedTaskCount": len(output.proposedTasks),
                        "taskSolutionCount": len(output.taskSolutions),
                    }
                },
                "errors": [],
            },
            "snapshot": snapshot,
            "companyHarvesterOutput": output.model_dump(mode="json"),
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


def _selected_project_tasks(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[Any]:
    mode_config = _mode_for(project, mode)
    task_filter = set(mode_config.taskIds if mode_config else [])
    surface_filter = set((mode_config.discoveryInput or mode_config.surfaceFilter) if mode_config else [])
    return [
        task
        for task in project.tasks
        if (not task_filter or task.taskId in task_filter)
        and (not surface_filter or bool(set(task.expectedSurfaces) & surface_filter))
    ]


def _task_expectations(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[IcaTaskDiscoveryExpectation]:
    selected = _selected_project_tasks(project, mode)
    selected_ids = {task.taskId for task in selected}
    explicit = [item for item in project.taskDiscoveryExpectations if not selected_ids or item.taskId in selected_ids]
    by_id = {item.taskId: item for item in explicit}
    expectations = []
    for task in selected:
        if task.taskId in by_id:
            expectations.append(by_id[task.taskId])
            continue
        words = [part for part in _tokenize(f"{task.name} {task.prompt}") if len(part) > 3]
        expectations.append(
            IcaTaskDiscoveryExpectation(
                taskId=task.taskId,
                aliases=[task.name],
                keywords=words[:8],
                expectedSurfaces=task.expectedSurfaces,
            )
        )
    return expectations


def _tokenize(value: str) -> set[str]:
    clean = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
    stop = {"the", "and", "for", "with", "using", "use", "from", "into", "all", "una", "con", "para", "que", "los", "las"}
    return {part for part in clean.split() if part and part not in stop}


def _task_text(task: dict[str, Any]) -> str:
    return " ".join(str(task.get(key) or "") for key in ("name", "taskName", "prompt", "successCriteria"))


def _task_id(task: dict[str, Any], fallback: str = "") -> str:
    return str(task.get("taskId") or task.get("id") or task.get("metadata", {}).get("icaTaskId") if isinstance(task.get("metadata"), dict) else "" or fallback)


def _expected_task(project: IcaDemoProject, task_id: str) -> Any | None:
    for task in project.tasks:
        if task.taskId == task_id:
            return task
    return None


def _task_match_score(expectation: IcaTaskDiscoveryExpectation, expected_name: str, discovered: dict[str, Any]) -> float:
    discovered_text = _task_text(discovered)
    discovered_tokens = _tokenize(discovered_text)
    expected_tokens = _tokenize(" ".join([expected_name, *expectation.aliases, *expectation.keywords]))
    if not expected_tokens or not discovered_tokens:
        return 0.0
    overlap = len(expected_tokens & discovered_tokens) / len(expected_tokens)
    alias_hit = any(alias and alias.lower() in discovered_text.lower() for alias in expectation.aliases)
    keyword_hit = sum(1 for keyword in expectation.keywords if keyword.lower() in discovered_text.lower())
    keyword_bonus = min(keyword_hit / max(len(expectation.keywords), 1), 1.0) * 0.25
    return round(min(1.0, overlap + keyword_bonus + (0.25 if alias_hit else 0.0)), 4)


def evaluate_task_discovery(
    *,
    project: IcaDemoProject,
    discovered_tasks: list[dict[str, Any]],
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaTaskDiscoveryEvaluation:
    expectations = _task_expectations(project, mode)
    matches: list[IcaTaskDiscoveryMatch] = []
    used_discovered: set[int] = set()
    missing: list[str] = []

    for expectation in expectations:
        expected = _expected_task(project, expectation.taskId)
        expected_name = str((expected.name if expected else expectation.taskId) or expectation.taskId)
        best_index = -1
        best_score = 0.0
        for index, task in enumerate(discovered_tasks):
            if index in used_discovered:
                continue
            score = _task_match_score(expectation, expected_name, task)
            if score > best_score:
                best_index = index
                best_score = score
        matched = best_index >= 0 and best_score >= expectation.minSimilarity
        if matched:
            used_discovered.add(best_index)
            matched_task = discovered_tasks[best_index]
            matches.append(
                IcaTaskDiscoveryMatch(
                    expectedTaskId=expectation.taskId,
                    expectedName=expected_name,
                    matchedTaskId=_task_id(matched_task, fallback=str(best_index)),
                    matchedName=str(matched_task.get("name") or matched_task.get("taskName") or matched_task.get("prompt") or ""),
                    score=best_score,
                    matched=True,
                    judge=expectation.judge,
                    reason="Matched by aliases/keywords/token overlap.",
                )
            )
        else:
            missing.append(expectation.taskId)
            matches.append(
                IcaTaskDiscoveryMatch(
                    expectedTaskId=expectation.taskId,
                    expectedName=expected_name,
                    score=best_score,
                    matched=False,
                    judge=expectation.judge,
                    reason="No discovered task reached the required similarity threshold.",
                )
            )

    matched_count = len(used_discovered)
    expected_count = len(expectations)
    discovered_count = len(discovered_tasks)
    recall = round(matched_count / expected_count, 4) if expected_count else 1.0
    precision = round(matched_count / discovered_count, 4) if discovered_count else (1.0 if expected_count == 0 else 0.0)
    score = round((recall * 0.75) + (precision * 0.25), 4)
    extra = [
        str(task.get("name") or task.get("taskName") or task.get("prompt") or "")
        for index, task in enumerate(discovered_tasks)
        if index not in used_discovered
    ]
    return IcaTaskDiscoveryEvaluation(
        projectId=project.projectId,
        mode=mode,
        passed=not missing,
        score=score,
        recall=recall,
        precision=precision,
        expectedCount=expected_count,
        discoveredCount=discovered_count,
        matchedCount=matched_count,
        matches=matches,
        missingTaskIds=missing,
        extraTaskNames=extra,
    )


def _solution_expected_tasks(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[Any]:
    return _selected_project_tasks(project, mode)


def _tool_names(snapshot: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(tool.get("name") or "") for tool in snapshot.get("tools", []) if tool.get("name")}


def _connector_types(snapshot: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(connector.get("type") or "") for connector in snapshot.get("connectors", []) if connector.get("type")}


def _expected_solution_for(project: IcaDemoProject, task_id: str) -> IcaTaskSolutionSpec | None:
    for solution in project.expectedSolutions:
        if solution.taskId == task_id:
            return solution
    return None


def _default_solution_for_task(project: IcaDemoProject, task: Any, snapshot: dict[str, list[dict[str, Any]]]) -> IcaTaskSolutionSpec:
    surfaces = set(task.expectedSurfaces)
    connectors = []
    if "api" in surfaces:
        connectors.append("api")
    if "web" in surfaces:
        connectors.append("web")
    if "documents" in surfaces:
        connectors.append("knowledge")
    available_tools = sorted(_tool_names(snapshot))
    tools = []
    if "documents" in surfaces and "knowledge.company_docs.search" in available_tools:
        tools.append("knowledge.company_docs.search")
    if "web" in surfaces:
        tools.extend(name for name in available_tools if ".web." in name or name.endswith(".explore_workflows"))
    if "api" in surfaces:
        tools.extend(name for name in available_tools if ".api." in name)
    tools = sorted(dict.fromkeys(tools))
    trajectory_id = f"{project.projectId}:{task.taskId}:expected_trajectory"
    return IcaTaskSolutionSpec(
        taskId=task.taskId,
        connectors=connectors,
        tools=tools,
        trajectories=[
            {
                "trajectoryId": trajectory_id,
                "description": f"Use {', '.join(connectors) or 'available'} surfaces to solve {task.name}.",
                "toolCalls": [{"toolName": name, "arguments": {}} for name in tools[:4]],
                "source": "generated",
            }
        ],
        skills=[
            {
                "skillId": f"{project.projectId}:{task.taskId}:skill",
                "name": f"{task.name} skill",
                "description": task.successCriteria,
                "trajectoryIds": [trajectory_id],
                "instructions": task.prompt,
                "source": "hybrid",
            }
        ],
        agentProvider={
            "runtimeKind": "model_agent",
            "provider": "openai",
            "model": "",
            "systemPrompt": f"You are the {project.name} task agent. Solve: {task.prompt}",
        },
    )


def propose_task_solutions(
    *,
    project: IcaDemoProject,
    snapshot: dict[str, list[dict[str, Any]]],
    mode: IcaBenchmarkModeKind | None = None,
) -> list[IcaTaskSolutionSpec]:
    expected_ids = {task.taskId for task in _solution_expected_tasks(project, mode)}
    solutions: list[IcaTaskSolutionSpec] = []
    for task in _solution_expected_tasks(project, mode):
        solutions.append(_default_solution_for_task(project, task, snapshot))
    return [solution for solution in solutions if not expected_ids or solution.taskId in expected_ids]


def evaluate_solution_discovery(
    *,
    project: IcaDemoProject,
    solutions: list[IcaTaskSolutionSpec],
    snapshot: dict[str, list[dict[str, Any]]],
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaSolutionDiscoveryEvaluation:
    expected_tasks = _solution_expected_tasks(project, mode)
    expected_task_ids = [task.taskId for task in expected_tasks]
    by_task = {solution.taskId: solution for solution in solutions}
    available_connectors = _connector_types(snapshot)
    missing: list[str] = []
    incomplete: list[str] = []

    for task in expected_tasks:
        solution = by_task.get(task.taskId)
        if not solution:
            missing.append(task.taskId)
            continue
        expected_solution = _expected_solution_for(project, task.taskId)
        required_connectors = {"api" if surface == "api" else "web" if surface == "web" else "knowledge" for surface in task.expectedSurfaces if surface in {"api", "web", "documents"}}
        if expected_solution:
            required_connectors |= set(expected_solution.connectors)
        has_connector_plan = required_connectors <= set(solution.connectors)
        has_available_connectors = required_connectors <= available_connectors
        required_tools = set(expected_solution.tools if expected_solution else [])
        has_tools = bool(solution.tools) and (not required_tools or bool(required_tools & set(solution.tools)))
        has_trajectory = bool(solution.trajectories)
        has_skill = bool(solution.skills)
        has_agent = bool(solution.agentProvider.runtimeKind)
        if not (has_connector_plan and has_available_connectors and has_tools and has_trajectory and has_skill and has_agent):
            incomplete.append(task.taskId)

    passed_count = len(expected_task_ids) - len(missing) - len(incomplete)
    score = round(passed_count / len(expected_task_ids), 4) if expected_task_ids else 1.0
    return IcaSolutionDiscoveryEvaluation(
        projectId=project.projectId,
        mode=mode,
        passed=not missing and not incomplete,
        score=score,
        expectedTaskCount=len(expected_task_ids),
        solutionCount=len(solutions),
        missingTaskIds=missing,
        incompleteTaskIds=incomplete,
        solutions=solutions,
    )


def build_agent_config_from_solution(
    *,
    project: IcaDemoProject,
    task: dict[str, Any],
    solution: IcaTaskSolutionSpec,
    email: str = "",
    company_id: str = "",
) -> AgentConfig:
    provider = solution.agentProvider
    tool_callables = [
        AgentCallable(
            name=tool_name,
            description=f"Tool required for {task.get('name') or solution.taskId}.",
            kind="tool",
            source="ica_solution",
            connectorId=next((connector for connector in solution.connectors if connector in tool_name), ""),
            executionReady=True,
        )
        for tool_name in solution.tools
    ]
    skill_callables = [
        AgentCallable(
            name=skill.name,
            description=skill.description or skill.instructions,
            kind="skill",
            source="ica_solution",
            capabilityId=skill.skillId,
            trajectoryIds=skill.trajectoryIds,
            executionReady=True,
        )
        for skill in solution.skills
    ]
    return AgentConfig(
        agentId=f"{project.projectId}:{solution.taskId}:{provider.runtimeKind}",
        name=f"{project.name} - {task.get('name') or solution.taskId}",
        email=email,
        companyId=company_id,
        runtimeKind=provider.runtimeKind,
        runtimeProfile=AgentRuntimeProfile(
            kind=provider.runtimeKind,
            provider=provider.provider,
            model=provider.model,
            systemPrompt=provider.systemPrompt,
        ),
        status="draft",
        tasks=[
            AgentTask(
                name=str(task.get("name") or solution.taskId),
                prompt=str(task.get("prompt") or ""),
                successCriteria=str(task.get("successCriteria") or ""),
            )
        ],
        tools=tool_callables,
        skills=skill_callables,
        capabilityDiscovery={
            "mode": "ica_task_solution",
            "icaProjectId": project.projectId,
            "icaTaskId": solution.taskId,
            "connectors": solution.connectors,
            "trajectoryIds": [trajectory.trajectoryId for trajectory in solution.trajectories],
        },
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
) -> IcaCompanyBenchmarkResult:
    runner = runner or CompanyHarvesterIcaRunner()
    result = await runner.run(
        project,
        email=email,
        company_id=company_id,
        base_url=base_url,
        mode=mode,
        process=process,
        include_ground_truth_tasks=False,
    )
    expected = IcaExpectedHarvest.model_validate(result.get("expectedHarvest") or project.expectedHarvest.model_dump())
    inventory = evaluate_company_harvest_snapshot(
        project=project,
        snapshot=result.get("snapshot") or {},
        expected_harvest=expected,
        run=result.get("run") or {},
        mode=mode,
    )
    snapshot = result.get("snapshot") or {}
    task_discovery = evaluate_task_discovery(project=project, discovered_tasks=snapshot.get("tasks") or [], mode=mode)
    solutions = propose_task_solutions(project=project, snapshot=snapshot, mode=mode)
    solution_discovery = evaluate_solution_discovery(project=project, solutions=solutions, snapshot=snapshot, mode=mode)
    score = round((task_discovery.score * 0.45) + (solution_discovery.score * 0.45) + (inventory.score * 0.10), 4)
    passed = task_discovery.passed and solution_discovery.passed and inventory.passed
    return IcaCompanyBenchmarkResult(
        projectId=project.projectId,
        mode=mode,
        passed=passed,
        score=score,
        phases={
            "taskDiscovery": task_discovery.model_dump(),
            "solutionDiscovery": solution_discovery.model_dump(),
            "inventory": inventory.model_dump(),
        },
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
