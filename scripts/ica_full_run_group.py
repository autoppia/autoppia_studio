from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.company_harvesters import list_company_harvesters
from app.routes.ica import _RUNS_PATH, _canonical_run_modes_for
from app.services import infinite_company_arena as ica


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_tasks(project: Any, mode: str | None) -> list[dict[str, Any]]:
    materialized = ica.materialize_project(project, mode=mode, include_ground_truth_tasks=True)
    return [
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


def _save(records: list[dict[str, Any]]) -> None:
    _RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _RUNS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
    tmp_path.replace(_RUNS_PATH)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create one ICA run group for all selected harvesters and demo companies.")
    parser.add_argument("--harvester", action="append", default=[], help="Harvester name. Repeatable. Defaults to all registered harvesters.")
    parser.add_argument("--project", action="append", default=[], help="Project id. Repeatable. Defaults to all demo companies.")
    parser.add_argument("--email", default="ica-owner@example.com")
    parser.add_argument("--append", action="store_true", help="Append to existing runs instead of replacing them.")
    args = parser.parse_args()

    harvesters = [item["name"] for item in list_company_harvesters()]
    if args.harvester:
        requested = set(args.harvester)
        harvesters = [name for name in harvesters if name in requested]
        missing = requested - set(harvesters)
        if missing:
            raise SystemExit(f"Unknown harvesters: {sorted(missing)}")

    projects = [ica.load_ica_project(path) for path in ica.demo_company_manifest_paths()]
    if args.project:
        requested_projects = set(args.project)
        projects = [project for project in projects if project.projectId in requested_projects]
        missing_projects = requested_projects - {project.projectId for project in projects}
        if missing_projects:
            raise SystemExit(f"Unknown projects: {sorted(missing_projects)}")

    run_group_id = f"ica-run-group-{uuid4().hex[:10]}"
    records: list[dict[str, Any]] = []
    if args.append and _RUNS_PATH.exists():
        try:
            existing = json.loads(_RUNS_PATH.read_text(encoding="utf-8"))
            records = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
        except json.JSONDecodeError:
            records = []
    else:
        _save([])

    total = sum(len(_canonical_run_modes_for(project)) for _harvester in harvesters for project in projects)
    done = 0
    for harvester_name in harvesters:
        for project in projects:
            for mode in _canonical_run_modes_for(project):
                done += 1
                run_id = f"ica-run-{uuid4().hex[:12]}"
                record = {
                    "runId": run_id,
                    "runGroupId": run_group_id,
                    "createdAt": _utc_now(),
                    "status": "running",
                    "harvesterName": harvester_name,
                    "projectId": project.projectId,
                    "projectName": project.name,
                    "projectTasks": _project_tasks(project, mode),
                    "mode": mode,
                    "result": None,
                    "error": None,
                }
                records.insert(0, record)
                _save(records)
                print(json.dumps({"progress": f"{done}/{total}", "harvester": harvester_name, "projectId": project.projectId, "mode": mode, "status": "running"}), flush=True)
                try:
                    company_id = f"ica:{project.projectId}:{harvester_name}:{mode or 'default'}:{uuid4().hex[:8]}"
                    result = await ica.evaluate_project_company_harvest(
                        project,
                        email=args.email,
                        company_id=company_id,
                        mode=mode,
                        runner=ica.CompanyHarvesterEngineIcaRunner(harvester_name),
                    )
                    record["status"] = "completed"
                    record["result"] = result.model_dump(mode="json")
                except Exception as exc:
                    record["status"] = "failed"
                    record["error"] = f"{type(exc).__name__}: {exc}"[:4000]
                _save(records)
                print(
                    json.dumps(
                        {
                            "progress": f"{done}/{total}",
                            "harvester": harvester_name,
                            "projectId": project.projectId,
                            "mode": mode,
                            "status": record["status"],
                            "score": ((record.get("result") or {}).get("score") if record.get("result") else 0.0),
                            "error": record.get("error") or "",
                        }
                    ),
                    flush=True,
                )

    print(json.dumps({"runGroupId": run_group_id, "runs": total, "path": str(_RUNS_PATH)}, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
