from __future__ import annotations

from typing import Any

from ica.schemas import (
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaEvaluationMetric,
    IcaEvaluationResult,
    IcaExpectedHarvest,
    IcaMinimumMetric,
)


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


