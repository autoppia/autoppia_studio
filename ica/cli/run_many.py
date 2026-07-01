from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ica.company_harvesters.runners import CompanyHarvesterEngineIcaRunner
from ica.demo_companies.loader import demo_company_manifest_paths, load_ica_project
from ica.evaluation.benchmark import evaluate_project_company_harvest
from ica.schemas import IcaDemoProject


def _load_projects(category: str = "", reachable_only: bool = False) -> list[IcaDemoProject]:
    projects = [load_ica_project(path) for path in demo_company_manifest_paths()]
    if category:
        projects = [project for project in projects if str(project.metadata.get("category") or "") == category]
    if reachable_only:
        projects = [project for project in projects if project.metadata.get("remoteReachable", True)]
    return sorted(projects, key=lambda project: project.projectId)


def _result_row(harvester: str, project: IcaDemoProject, mode: str, result: Any, elapsed: float) -> dict[str, Any]:
    phases = result.phases
    task = phases.get("taskDiscovery") or {}
    solution = phases.get("solutionDiscovery") or {}
    inventory = phases.get("inventory") or {}
    execution = phases.get("agentExecution") or {}
    execution_results = execution.get("results") or []
    build_failures = [
        {"taskId": item.get("taskId"), "buildErrors": item.get("buildErrors") or []}
        for item in execution_results
        if isinstance(item, dict) and item.get("buildPassed") is False
    ]
    return {
        "harvester": harvester,
        "projectId": project.projectId,
        "mode": mode,
        "category": project.metadata.get("category", ""),
        "remoteReachable": project.metadata.get("remoteReachable", True),
        "passed": result.passed,
        "score": result.score,
        "elapsedSeconds": round(elapsed, 3),
        "taskDiscovery": {
            "passed": task.get("passed", False),
            "score": task.get("score", 0.0),
            "recall": task.get("recall", 0.0),
            "precision": task.get("precision", 0.0),
            "expectedCount": task.get("expectedCount", 0),
            "discoveredCount": task.get("discoveredCount", 0),
            "missingTaskIds": task.get("missingTaskIds", []),
            "extraTaskNames": task.get("extraTaskNames", []),
        },
        "solutionDiscovery": {
            "passed": solution.get("passed", False),
            "score": solution.get("score", 0.0),
            "solutionCount": solution.get("solutionCount", 0),
            "missingTaskIds": solution.get("missingTaskIds", []),
            "incompleteTaskIds": solution.get("incompleteTaskIds", []),
            "invalidOriginIds": solution.get("invalidOriginIds", []),
            "hallucinatedToolNames": solution.get("hallucinatedToolNames", []),
            "hallucinatedConnectorIds": solution.get("hallucinatedConnectorIds", []),
            "incompleteReasons": solution.get("incompleteReasons", {}),
        },
        "inventory": {
            "passed": inventory.get("passed", False),
            "score": inventory.get("score", 0.0),
            "missing": inventory.get("missing", []),
        },
        "agentExecution": {
            "applicable": execution.get("applicable", False),
            "passed": execution.get("passed", True),
            "score": execution.get("score", 1.0),
            "skippedReason": execution.get("skippedReason", ""),
            "expectedTaskCount": execution.get("expectedTaskCount", 0),
            "executedTaskCount": execution.get("executedTaskCount", 0),
            "buildPassedCount": sum(1 for item in execution_results if isinstance(item, dict) and item.get("buildPassed", True)),
            "buildFailedCount": len(build_failures),
            "buildFailures": build_failures,
        },
    }


async def _run_case(harvester: str, project: IcaDemoProject, mode: str, timeout_seconds: float) -> dict[str, Any]:
    started = time.time()
    try:
        result = await asyncio.wait_for(
            evaluate_project_company_harvest(
                project,
                email="ica-batch@autoppia.com",
                company_id=f"ica-batch-{harvester}-{project.projectId}-{int(started)}",
                mode=mode,
                runner=CompanyHarvesterEngineIcaRunner(harvester),
            ),
            timeout=timeout_seconds,
        )
        return _result_row(harvester, project, mode, result, time.time() - started)
    except Exception as exc:
        return {
            "harvester": harvester,
            "projectId": project.projectId,
            "mode": mode,
            "category": project.metadata.get("category", ""),
            "remoteReachable": project.metadata.get("remoteReachable", True),
            "passed": False,
            "score": 0.0,
            "elapsedSeconds": round(time.time() - started, 3),
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_harvester: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_harvester[str(row["harvester"])].append(row)
        by_project[str(row["projectId"])].append(row)

    def stats(group: list[dict[str, Any]]) -> dict[str, Any]:
        scores = [float(row.get("score") or 0.0) for row in group]
        return {
            "cases": len(group),
            "passed": sum(1 for row in group if row.get("passed")),
            "failed": sum(1 for row in group if not row.get("passed")),
            "errors": sum(1 for row in group if row.get("error")),
            "averageScore": round(sum(scores) / len(scores), 4) if scores else 0.0,
        }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows),
        "passed": sum(1 for row in rows if row.get("passed")),
        "failed": sum(1 for row in rows if not row.get("passed")),
        "errors": sum(1 for row in rows if row.get("error")),
        "averageScore": round(sum(float(row.get("score") or 0.0) for row in rows) / len(rows), 4) if rows else 0.0,
        "byHarvester": {key: stats(value) for key, value in sorted(by_harvester.items())},
        "byProject": {key: stats(value) for key, value in sorted(by_project.items())},
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run ICA harvesters across multiple demo companies.")
    parser.add_argument("--harvester", action="append", default=[], help="Harvester to run. Repeatable. Defaults to agentic.")
    parser.add_argument("--category", default="", help="Filter demo companies by metadata.category, e.g. only_web.")
    parser.add_argument("--company", action="append", default=[], help="Specific project id. Repeatable.")
    parser.add_argument("--reachable-only", action="store_true", help="Skip demo companies marked remoteReachable=false.")
    parser.add_argument("--mode", default="web_only")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=180.0, help="Per harvester/project timeout in seconds.")
    parser.add_argument("--output-dir", default="logs")
    args = parser.parse_args()

    harvesters = args.harvester or ["agentic"]
    projects = _load_projects(category=args.category, reachable_only=args.reachable_only)
    if args.company:
        allowed = set(args.company)
        projects = [project for project in projects if project.projectId in allowed]
    if args.limit > 0:
        projects = projects[: args.limit]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("ica_batch_%Y%m%dT%H%M%SZ")
    jsonl_path = output_dir / f"{run_id}.jsonl"
    summary_path = output_dir / f"{run_id}.summary.json"

    rows: list[dict[str, Any]] = []
    with jsonl_path.open("w", encoding="utf-8") as stream:
        for harvester in harvesters:
            for project in projects:
                row = await _run_case(harvester, project, args.mode, args.timeout)
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = _summarize(rows)
    summary["runId"] = run_id
    summary["jsonlPath"] = str(jsonl_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summaryPath": str(summary_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
