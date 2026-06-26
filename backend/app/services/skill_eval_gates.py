from __future__ import annotations

from typing import Any


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def eval_run_label(run: dict[str, Any]) -> str:
    label = str(run.get("label") or run.get("status") or run.get("result") or "").strip().lower()
    if label in {"passed", "success", "succeeded", "ok"}:
        return "pass"
    if label in {"failed", "error", "errored"}:
        return "fail"
    if label in {"pass", "fail", "pending", "running"}:
        return label
    return "unknown"


def _index_eval_runs(eval_runs: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    runs_by_eval_id: dict[str, list[dict[str, Any]]] = {}
    runs_by_benchmark_id: dict[str, list[dict[str, Any]]] = {}
    for run in eval_runs:
        eval_id = str(run.get("evalId") or "").strip()
        benchmark_id = str(run.get("benchmarkId") or "").strip()
        if eval_id:
            runs_by_eval_id.setdefault(eval_id, []).append(run)
        if benchmark_id:
            runs_by_benchmark_id.setdefault(benchmark_id, []).append(run)
    return runs_by_eval_id, runs_by_benchmark_id


def _skill_regression_refs(skill: dict[str, Any]) -> dict[str, Any]:
    package = skill.get("skillPackage") if isinstance(skill.get("skillPackage"), dict) else {}
    evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    regression = evidence.get("regressionSuite") if isinstance(evidence.get("regressionSuite"), dict) else {}
    production_gate = package.get("productionGate") if isinstance(package.get("productionGate"), dict) else {}
    latest_regression = evidence.get("latestRegression") if isinstance(evidence.get("latestRegression"), dict) else skill.get("latestRegression") if isinstance(skill.get("latestRegression"), dict) else {}
    lineage = skill.get("lineage") if isinstance(skill.get("lineage"), dict) else {}
    benchmark_ids = _dedupe([
        str(skill.get("benchmarkId") or ""),
        *[str(item or "") for item in regression.get("benchmarkIds") or []],
        *[str(item or "") for item in lineage.get("benchmarkIds", [])],
    ])
    eval_ids = _dedupe([
        str(skill.get("evalId") or ""),
        *[str(item or "") for item in regression.get("evalIds") or []],
        *[str(item or "") for item in lineage.get("evalIds", [])],
    ])
    return {
        "package": package,
        "evidence": evidence,
        "regression": regression,
        "productionGate": production_gate,
        "latestRegression": latest_regression,
        "benchmarkIds": benchmark_ids,
        "evalIds": eval_ids,
    }


def build_skill_eval_gate(
    skill: dict[str, Any],
    *,
    runs_by_eval_id: dict[str, list[dict[str, Any]]] | None = None,
    runs_by_benchmark_id: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    runs_by_eval_id = runs_by_eval_id or {}
    runs_by_benchmark_id = runs_by_benchmark_id or {}
    refs = _skill_regression_refs(skill)
    benchmark_ids = refs["benchmarkIds"]
    eval_ids = refs["evalIds"]
    regression = refs["regression"]
    production_gate = refs["productionGate"]
    latest_regression = refs["latestRegression"]
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
    if "fail" in labels:
        state = "failing"
    elif "pass" in labels:
        state = "passing"
    elif any(label in {"pending", "running"} for label in labels):
        state = "pending"
    else:
        state = "missing"
    blockers = _list_values(production_gate.get("blockers"))
    if state == "missing" and "publishableRegression" not in blockers:
        blockers.append("publishableRegression")
    if state == "failing" and "failingRegression" not in blockers:
        blockers.append("failingRegression")
    next_actions: list[str] = []
    if state == "missing":
        next_actions.append("Run a linked benchmark regression before publishing this skill.")
    elif state == "pending":
        next_actions.append("Wait for the linked regression run to finish before publishing this skill.")
    elif state == "failing":
        next_actions.append("Inspect failing regression traces and fix the skill before publishing.")
    return {
        "skillId": str(skill.get("capabilityId") or skill.get("skillId") or ""),
        "name": str(skill.get("name") or ""),
        "state": state,
        "benchmarkIds": benchmark_ids[:5],
        "evalIds": eval_ids[:5],
        "linkedRunIds": _dedupe([run.get("runId") for run in linked_runs])[:5],
        "latestLabel": latest_label,
        "hasRegression": has_regression,
        "publishable": state == "passing",
        "blockers": blockers[:8],
        "nextActions": next_actions,
    }


def summarize_skill_eval_gates(skills: list[dict[str, Any]], eval_runs: list[dict[str, Any]]) -> dict[str, Any]:
    runs_by_eval_id, runs_by_benchmark_id = _index_eval_runs(eval_runs)

    benchmark_linked = 0
    regression_linked = 0
    passing = 0
    failing = 0
    pending = 0
    missing = 0
    blocked = 0
    samples: list[dict[str, Any]] = []
    for skill in skills:
        gate = build_skill_eval_gate(skill, runs_by_eval_id=runs_by_eval_id, runs_by_benchmark_id=runs_by_benchmark_id)
        benchmark_ids = gate["benchmarkIds"]
        eval_ids = gate["evalIds"]
        has_regression = bool(gate["hasRegression"])
        if benchmark_ids or eval_ids:
            benchmark_linked += 1
        if has_regression:
            regression_linked += 1
        state = gate["state"]
        if state == "failing":
            failing += 1
        elif state == "passing":
            passing += 1
        elif state == "pending":
            pending += 1
        else:
            missing += 1
        blockers = gate["blockers"]
        if "failingRegression" in blockers or state == "failing" or (
            "publishableRegression" in blockers and state != "missing"
        ):
            blocked += 1
        if len(samples) < 8:
            samples.append(
                {
                    "skillId": gate["skillId"],
                    "name": gate["name"],
                    "state": state,
                    "benchmarkIds": benchmark_ids[:5],
                    "evalIds": eval_ids[:5],
                    "latestLabel": gate["latestLabel"],
                    "blockers": blockers[:5],
                    "nextActions": gate["nextActions"][:2],
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
