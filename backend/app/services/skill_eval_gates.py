from __future__ import annotations

from typing import Any


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def eval_run_label(run: dict[str, Any]) -> str:
    label = str(run.get("label") or run.get("status") or run.get("result") or "").strip().lower()
    if label in {"passed", "success", "succeeded", "ok"}:
        return "pass"
    if label in {"failed", "error", "errored"}:
        return "fail"
    if label in {"pass", "fail", "pending", "running"}:
        return label
    return "unknown"


def summarize_skill_eval_gates(skills: list[dict[str, Any]], eval_runs: list[dict[str, Any]]) -> dict[str, Any]:
    runs_by_eval_id: dict[str, list[dict[str, Any]]] = {}
    runs_by_benchmark_id: dict[str, list[dict[str, Any]]] = {}
    for run in eval_runs:
        eval_id = str(run.get("evalId") or "").strip()
        benchmark_id = str(run.get("benchmarkId") or "").strip()
        if eval_id:
            runs_by_eval_id.setdefault(eval_id, []).append(run)
        if benchmark_id:
            runs_by_benchmark_id.setdefault(benchmark_id, []).append(run)

    benchmark_linked = 0
    regression_linked = 0
    passing = 0
    failing = 0
    pending = 0
    missing = 0
    blocked = 0
    samples: list[dict[str, Any]] = []
    for skill in skills:
        package = skill.get("skillPackage") if isinstance(skill.get("skillPackage"), dict) else {}
        evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
        regression = evidence.get("regressionSuite") if isinstance(evidence.get("regressionSuite"), dict) else {}
        production_gate = package.get("productionGate") if isinstance(package.get("productionGate"), dict) else {}
        latest_regression = evidence.get("latestRegression") if isinstance(evidence.get("latestRegression"), dict) else skill.get("latestRegression") if isinstance(skill.get("latestRegression"), dict) else {}
        lineage = skill.get("lineage") if isinstance(skill.get("lineage"), dict) else {}
        benchmark_ids = _list_values([
            str(skill.get("benchmarkId") or ""),
            *[str(item or "") for item in regression.get("benchmarkIds") or []],
            *[str(item or "") for item in lineage.get("benchmarkIds", [])],
        ])
        eval_ids = _list_values([
            str(skill.get("evalId") or ""),
            *[str(item or "") for item in regression.get("evalIds") or []],
            *[str(item or "") for item in lineage.get("evalIds", [])],
        ])
        linked_runs = [
            run
            for eval_id in eval_ids
            for run in runs_by_eval_id.get(eval_id, [])
        ] + [
            run
            for benchmark_id in benchmark_ids
            for run in runs_by_benchmark_id.get(benchmark_id, [])
        ]
        labels = [eval_run_label(run) for run in linked_runs]
        latest_label = str(latest_regression.get("label") or "").lower()
        if latest_label:
            labels.append(eval_run_label({"label": latest_label}))
        if regression.get("publishable"):
            labels.append("pass")
        has_regression = bool(regression.get("cases") or benchmark_ids or eval_ids or latest_regression or linked_runs)
        if benchmark_ids or eval_ids:
            benchmark_linked += 1
        if has_regression:
            regression_linked += 1
        if "fail" in labels:
            state = "failing"
            failing += 1
        elif "pass" in labels:
            state = "passing"
            passing += 1
        elif any(label in {"pending", "running"} for label in labels):
            state = "pending"
            pending += 1
        else:
            state = "missing"
            missing += 1
        blockers = _list_values(production_gate.get("blockers"))
        if "publishableRegression" in blockers or state == "failing":
            blocked += 1
        if len(samples) < 8:
            samples.append(
                {
                    "skillId": str(skill.get("capabilityId") or skill.get("skillId") or ""),
                    "name": str(skill.get("name") or ""),
                    "state": state,
                    "benchmarkIds": benchmark_ids[:5],
                    "evalIds": eval_ids[:5],
                    "latestLabel": latest_label,
                    "blockers": blockers[:5],
                }
            )
    return {
        "totalSkills": len(skills),
        "benchmarkLinked": benchmark_linked,
        "regressionLinked": regression_linked,
        "passing": passing,
        "failing": failing,
        "pending": pending,
        "missing": missing,
        "blockedByRegression": blocked,
        "sample": samples,
    }
