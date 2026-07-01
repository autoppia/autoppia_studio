from __future__ import annotations

from pathlib import Path
import json

import pytest

from ica import benchmark
from ica.schemas import IcaExpectedHarvest


DEMO_COMPANIES_ROOT = Path(__file__).resolve().parents[2] / "demo_companies"


def _manifest_paths() -> list[Path]:
    return benchmark.demo_company_manifest_paths(DEMO_COMPANIES_ROOT)


def _manifest_json(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def test_only_web_category_contains_all_legacy_demo_webs():
    only_web = DEMO_COMPANIES_ROOT / "only_web"
    manifests = sorted(only_web.glob("*/project.json"))
    projects = [benchmark.load_ica_project(path) for path in manifests]

    assert len(projects) == 16
    assert {project.projectId for project in projects} == {
        "autobooks_web",
        "autocalendar_web",
        "autocinema_web",
        "autoconnect_web",
        "autocrm_web",
        "autodelivery_web",
        "autodining_web",
        "autodiscord_web",
        "autodrive_web",
        "autohealth_web",
        "autolist_web",
        "autolodge_web",
        "automail_web",
        "autostats_web",
        "autowork_web",
        "autozone_web",
    }
    assert all(project.benchmarkModes[0].modeId == "web_only" for project in projects)
    assert all(project.expectedHarvest.connectors == ["web"] for project in projects)
    assert all(project.surfaces[0].metadata.get("legacyDemoWeb") is True for project in projects)


def test_only_web_remote_readiness_metadata_is_explicit():
    projects = [benchmark.load_ica_project(path) for path in sorted((DEMO_COMPANIES_ROOT / "only_web").glob("*/project.json"))]
    by_id = {project.projectId: project for project in projects}
    unreachable = {"autodiscord_web", "autostats_web"}

    assert {project_id for project_id, project in by_id.items() if project.metadata.get("remoteReachable") is False} == unreachable
    assert all(project.metadata.get("remoteCheckedAt") for project in projects)


def test_only_web_iwa_registry_projects_get_generated_task_suites():
    projects = [benchmark.load_ica_project(path) for path in sorted((DEMO_COMPANIES_ROOT / "only_web").glob("*/project.json"))]
    generated = {
        project.projectId: project
        for project in projects
        if project.metadata.get("iwaSuiteGenerated")
    }

    autocalendar = next(project for project in projects if project.projectId == "autocalendar_web")
    assert len(autocalendar.tasks) == 3
    assert {task.metadata.get("iwaUseCase") for task in autocalendar.tasks} == {"SELECT_MONTH", "ADD_EVENT", "SEARCH_SUBMIT"}
    assert "autocinema_web" in generated
    assert "autodiscord_web" not in generated
    assert "autostats_web" not in generated
    assert all(len(project.tasks) == 3 for project in generated.values())
    assert all(len(project.expectedSolutions) == 3 for project in generated.values())
    assert all(task.metadata.get("iwaUseCase") for project in generated.values() for task in project.tasks)


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_manifest_loads(manifest_path: Path):
    project = benchmark.load_ica_project(manifest_path)

    assert project.projectId == manifest_path.parent.name
    assert project.name
    assert project.version
    assert project.surfaces
    assert project.benchmarkModes


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_manifest_uses_canonical_fields(manifest_path: Path):
    raw = _manifest_json(manifest_path)
    expected_harvest_keys = {
        "connectors",
        "minimumTaskCount",
        "minimumToolCount",
        "requiresKnowledge",
        "requiresApiTools",
        "requiresBrowserTasks",
        "minimumSolutionCount",
    }
    forbidden_mode_keys = {"expectedTaskIds", "label"}
    expected_harvest = raw.get("expectedHarvest") or {}

    assert set(expected_harvest) <= expected_harvest_keys
    for mode in raw.get("benchmarkModes") or []:
        assert not (set(mode) & forbidden_mode_keys)
        assert "taskIds" in mode
        assert "expectedHarvest" in mode
        assert "sourceCombination" in (mode.get("metadata") or {})
        assert set((mode.get("expectedHarvest") or {})) <= expected_harvest_keys


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_surface_files_exist(manifest_path: Path):
    project = benchmark.load_ica_project(manifest_path)
    root = manifest_path.parent

    for surface in project.surfaces:
        if surface.url.startswith(("http://", "https://")):
            continue
        if surface.kind in {"openapi", "document_url", "file", "code_file"}:
            assert (root / surface.url.lstrip("/")).exists(), f"{project.projectId}:{surface.surfaceId} points to missing {surface.url}"


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_benchmark_modes_reference_existing_tasks(manifest_path: Path):
    project = benchmark.load_ica_project(manifest_path)
    task_ids = {task.taskId for task in project.tasks}

    for mode in project.benchmarkModes:
        assert mode.modeId
        assert set(mode.taskIds) <= task_ids
        assert set(mode.expectedHarvest.connectors) <= {"web", "api", "knowledge", "code", "email", "database", "other"}


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_materializes_every_benchmark_mode(manifest_path: Path):
    project = benchmark.load_ica_project(manifest_path)

    for mode in project.benchmarkModes:
        materialized = benchmark.materialize_project(project, manifest_path=manifest_path, mode=mode.modeId)
        assert materialized.mode == mode.modeId
        if mode.expectedHarvest != IcaExpectedHarvest():
            assert materialized.expectedHarvest == mode.expectedHarvest
        else:
            assert materialized.expectedHarvest == project.expectedHarvest
        if mode.expectedHarvest.minimumTaskCount:
            assert len(materialized.userTasks) >= mode.expectedHarvest.minimumTaskCount


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda path: path.parent.name)
def test_demo_company_execution_tests_have_expected_solutions(manifest_path: Path):
    project = benchmark.load_ica_project(manifest_path)
    tasks_with_execution = {
        task.taskId
        for task in project.tasks
        if isinstance(task.metadata.get("executionTest"), dict)
    }
    if not tasks_with_execution:
        return
    if project.projectId == "autocinema_web":
        return
    solution_task_ids = {solution.taskId for solution in project.expectedSolutions}
    assert tasks_with_execution <= solution_task_ids

    assert tasks_with_execution
