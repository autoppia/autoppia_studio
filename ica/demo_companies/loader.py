from __future__ import annotations

import json
from pathlib import Path

from ica.iwa_bridge import iwa_expected_solution, iwa_task_discovery_expectation, iwa_task_spec, selected_iwa_use_cases
from ica.schemas import IcaDemoProject


ROOT = Path(__file__).resolve().parents[2]
DEMO_COMPANIES_ROOT = ROOT / "demo_companies"
DEMO_PROJECTS_ROOT = DEMO_COMPANIES_ROOT


def load_ica_project(path: str | Path) -> IcaDemoProject:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "project.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data = _augment_legacy_iwa_project(data)
    return IcaDemoProject.model_validate(data)


def _augment_legacy_iwa_project(data: dict) -> dict:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    if not metadata.get("legacyDemoWeb"):
        return data
    iwa_project_id = str(metadata.get("legacyIwaProject") or "")
    if not iwa_project_id:
        return data
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    if not tasks or any(str(task.get("taskId") or "") != "primary_web_workflow" for task in tasks if isinstance(task, dict)):
        return data
    use_cases = selected_iwa_use_cases(iwa_project_id, limit=3)
    if not use_cases:
        return data
    project_id = str(data.get("projectId") or "")
    generated_tasks = [iwa_task_spec(ica_project_id=project_id, iwa_project_id=iwa_project_id, use_case=use_case) for use_case in use_cases]
    data = dict(data)
    data["tasks"] = generated_tasks
    data["taskDiscoveryExpectations"] = [
        iwa_task_discovery_expectation(task_id=task["taskId"], use_case=str(task["metadata"]["iwaUseCase"]))
        for task in generated_tasks
    ]
    data["expectedSolutions"] = [
        iwa_expected_solution(ica_project_id=project_id, iwa_project_id=iwa_project_id, use_case=use_case)
        for use_case in use_cases
    ]
    expected_harvest = dict(data.get("expectedHarvest") or {})
    expected_harvest["minimumTaskCount"] = len(generated_tasks)
    expected_harvest["minimumSolutionCount"] = len(generated_tasks)
    data["expectedHarvest"] = expected_harvest
    benchmark_modes = []
    for mode in data.get("benchmarkModes") or []:
        if not isinstance(mode, dict):
            continue
        mode = dict(mode)
        if mode.get("modeId") == "web_only":
            mode["taskIds"] = [task["taskId"] for task in generated_tasks]
            mode["description"] = "Legacy IWA web adapter mode with generated IWA use cases."
            mode_expected = dict(mode.get("expectedHarvest") or {})
            mode_expected["minimumTaskCount"] = len(generated_tasks)
            mode_expected["minimumSolutionCount"] = len(generated_tasks)
            mode["expectedHarvest"] = mode_expected
        benchmark_modes.append(mode)
    data["benchmarkModes"] = benchmark_modes
    data["metadata"] = {**metadata, "iwaSuiteGenerated": True, "iwaSuiteUseCases": use_cases}
    return data


def demo_company_manifest_paths(root: str | Path | None = None) -> list[Path]:
    base = Path(root) if root else DEMO_COMPANIES_ROOT
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("project.json") if path.is_file())


def project_path(project_id: str) -> Path:
    direct = DEMO_PROJECTS_ROOT / project_id
    if (direct / "project.json").exists():
        return direct
    for manifest_path in demo_company_manifest_paths():
        if manifest_path.parent.name == project_id:
            return manifest_path.parent
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("projectId") == project_id:
            return manifest_path.parent
    return direct


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
