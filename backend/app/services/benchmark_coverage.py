from __future__ import annotations

from typing import Any

from app.services.task_contracts import task_contract_from_record
from app.services.task_contracts import task_contract_hardening


BENCHMARK_PORTFOLIO_ACTIONS = {
    "incomplete_task_contracts": {
        "area": "tasks",
        "severity": "high",
        "action": "Complete task contracts with intent, initial state, allowed systems, expected artifacts, success criteria and risk.",
    },
    "no_tasks": {
        "area": "tasks",
        "severity": "high",
        "action": "Add benchmark tasks before using the benchmark as a production gate.",
    },
    "no_skills": {
        "area": "skills",
        "severity": "high",
        "action": "Harvest trajectories and promote at least one reusable skill for this benchmark portfolio.",
    },
    "no_ready_skills": {
        "area": "skills",
        "severity": "high",
        "action": "Harden skills with activation, IO, policy, lineage and regression evidence before promotion.",
    },
    "no_regression_runs": {
        "area": "evals",
        "severity": "high",
        "action": "Run benchmark regressions and judge task trials before promotion.",
    },
    "no_passing_regression": {
        "area": "evals",
        "severity": "high",
        "action": "Get at least one passing benchmark regression before promoting capabilities.",
    },
    "failing_regressions": {
        "area": "evals",
        "severity": "high",
        "action": "Inspect failing benchmark traces and fix the underlying capability before publishing.",
    },
    "missing_regression": {
        "area": "evals",
        "severity": "high",
        "action": "Run benchmark regressions for uncovered connectors, entities and skills.",
    },
    "failing_regression": {
        "area": "evals",
        "severity": "high",
        "action": "Inspect failing regression traces before publishing or widening runtime access.",
    },
    "skill_hardening": {
        "area": "skills",
        "severity": "high",
        "action": "Harden skill packages before treating regression coverage as production-ready.",
    },
    "empty_regression_matrix": {
        "area": "evals",
        "severity": "medium",
        "action": "Reference connectors, entities or skills from benchmarks before evaluating coverage.",
    },
}


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def task_contract_completeness(contract: dict[str, Any]) -> dict[str, Any]:
    hardening = task_contract_hardening(contract)
    checks = dict(hardening["checks"])
    checks["expectedArtifact"] = checks.pop("expectedArtifacts")
    missing_fields = [
        "expectedArtifact" if field == "expectedArtifacts" else field
        for field in hardening.get("missingFields") or []
    ]
    return {
        "checks": checks,
        "missingFields": missing_fields,
        "nextActions": hardening["nextActions"],
        "passedChecks": hardening["passedChecks"],
        "totalChecks": hardening["totalChecks"],
        "score": hardening["score"],
        "state": hardening["state"],
        "evaluationReady": hardening["evaluationReady"],
        "reproducibility": hardening["reproducibility"],
    }


def _task_contract_for_coverage(task: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    initial_url = metadata.get("startUrl") or metadata.get("iwaStartUrl") or benchmark.get("websiteUrl") or ""
    contract = task_contract_from_record({**task, "initialUrl": task.get("initialUrl") or initial_url})
    contract["completeness"] = task_contract_completeness(contract)
    return contract


def _benchmark_portfolio_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = BENCHMARK_PORTFOLIO_ACTIONS.get(
            gap,
            {
                "area": "evals",
                "severity": "medium",
                "action": "Review benchmark portfolio gates before production promotion.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


def promotion_gate(
    *,
    task_total: int,
    task_complete: int,
    skill_total: int,
    ready_skills: int,
    published_skills: int,
    run_total: int,
    run_pass: int,
    run_fail: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    next_actions: list[str] = []
    if task_total == 0:
        blockers.append("no_tasks")
        next_actions.append("Add benchmark tasks with business intent, allowed systems, expected artifacts, success criteria, and risk class.")
    elif task_complete < task_total:
        blockers.append("incomplete_task_contracts")
        next_actions.append("Complete every task contract before using the benchmark as a production gate.")
    if skill_total == 0:
        blockers.append("no_skills")
        next_actions.append("Harvest candidate trajectories and promote at least one reusable skill.")
    elif ready_skills == 0:
        blockers.append("no_ready_skills")
        next_actions.append("Harden skills with activation guidance, IO, policy, source trajectories, and regression evidence.")
    if run_total == 0:
        blockers.append("no_regression_runs")
        next_actions.append("Run the benchmark and judge the resulting task trials.")
    elif run_pass == 0:
        blockers.append("no_passing_regression")
        next_actions.append("Get at least one passing regression run before promotion.")
    if run_fail > 0:
        blockers.append("failing_regressions")
        next_actions.append("Investigate failing regression runs before publishing or widening runtime access.")

    if blockers:
        state = "needs_regression" if blockers == ["no_regression_runs"] else "blocked"
    elif published_skills > 0:
        state = "published"
    else:
        state = "ready"

    return {
        "state": state,
        "blockers": blockers,
        "nextActions": next_actions,
        "canPromote": state in {"ready", "published"},
    }


def benchmark_coverage_summary(
    *,
    tasks: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    unique_skills: list[dict[str, Any]] = []
    seen_skill_ids: set[str] = set()
    for skill in skills:
        skill_id = str(skill.get("capabilityId") or skill.get("skillId") or "").strip()
        if skill_id and skill_id in seen_skill_ids:
            continue
        if skill_id:
            seen_skill_ids.add(skill_id)
        unique_skills.append(skill)
    skills = unique_skills
    contracts = [_task_contract_for_coverage(task, benchmark) for task in tasks]
    completeness = [contract.get("completeness") or task_contract_completeness(contract) for contract in contracts]
    systems = _dedupe_strings([system for contract in contracts for system in (contract.get("allowedSystems") or [])])
    expected_inputs = _dedupe_strings([input_name for contract in contracts for input_name in (contract.get("expectedInputs") or [])])
    task_artifacts = _dedupe_strings([artifact for contract in contracts for artifact in (contract.get("expectedArtifacts") or [])])
    task_fixtures = _dedupe_strings([fixture for contract in contracts for fixture in (contract.get("fixtures") or [])])
    skill_artifacts = _dedupe_strings([artifact for skill in skills for artifact in (skill.get("expectedArtifacts") or [])])
    risk_classes = _dedupe_strings([contract.get("riskClass") for contract in contracts])
    connector_ids = _dedupe_strings([connector_id for skill in skills for connector_id in (skill.get("connectorIds") or [])])
    entity_names = _dedupe_strings([
        entity
        for skill in skills
        for entity in [*(skill.get("inputEntities") or []), skill.get("outputEntity")]
    ])
    skill_ids = _dedupe_strings([skill.get("capabilityId") or skill.get("skillId") for skill in skills])
    labels = [str(run.get("label") or "pending").lower() for run in runs]
    latest_run = runs[0] if runs else None
    published_statuses = {"published", "approved", "active", "production"}
    ready_statuses = {"ready", *published_statuses}
    task_complete = sum(1 for item in completeness if item.get("state") == "complete")
    task_evaluation_ready = sum(1 for item in completeness if item.get("evaluationReady"))
    missing_field_counts: dict[str, int] = {}
    for item in completeness:
        for field in item.get("missingFields") or []:
            key = str(field or "").strip()
            if key:
                missing_field_counts[key] = missing_field_counts.get(key, 0) + 1
    skill_ready = sum(1 for skill in skills if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in ready_statuses)
    skill_published = sum(1 for skill in skills if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in published_statuses)
    run_pass = labels.count("pass")
    run_fail = labels.count("fail")
    return {
        "taskCount": len(tasks),
        "taskContractCoverage": {
            "complete": task_complete,
            "total": len(completeness),
            "averageScore": round(sum(float(item.get("score") or 0) for item in completeness) / len(completeness), 3) if completeness else 0.0,
            "evaluationReady": task_evaluation_ready,
            "missingFields": [{"name": key, "count": missing_field_counts[key]} for key in sorted(missing_field_counts, key=lambda item: (-missing_field_counts[item], item))],
            "reproducibility": {
                "withInitialState": sum(1 for item in completeness if (item.get("reproducibility") or {}).get("initialState")),
                "withEvaluatorConfig": sum(1 for item in completeness if (item.get("reproducibility") or {}).get("evaluatorConfig")),
                "withFixtures": sum(1 for item in completeness if (item.get("reproducibility") or {}).get("fixtures")),
                "withSeed": sum(1 for item in completeness if (item.get("reproducibility") or {}).get("seed")),
                "readyForReplay": sum(1 for item in completeness if (item.get("reproducibility") or {}).get("readyForReplay")),
            },
        },
        "systems": systems,
        "expectedInputs": expected_inputs,
        "expectedArtifacts": _dedupe_strings([*task_artifacts, *skill_artifacts]),
        "fixtures": task_fixtures,
        "riskClasses": risk_classes,
        "connectorIds": connector_ids,
        "entityNames": entity_names,
        "skillCoverage": {
            "skillIds": skill_ids,
            "total": len(skill_ids),
            "ready": skill_ready,
            "published": skill_published,
        },
        "runCoverage": {
            "total": len(runs),
            "pass": run_pass,
            "fail": run_fail,
            "pending": labels.count("pending"),
            "latestLabel": str((latest_run or {}).get("label") or ""),
            "latestRunId": str((latest_run or {}).get("runId") or ""),
            "latestCreatedAt": (latest_run or {}).get("createdAt"),
        },
        "promotionGate": promotion_gate(
            task_total=len(tasks),
            task_complete=task_complete,
            skill_total=len(skill_ids),
            ready_skills=skill_ready,
            published_skills=skill_published,
            run_total=len(runs),
            run_pass=run_pass,
            run_fail=run_fail,
        ),
    }


def coverage_portfolio(coverage_items: list[dict[str, Any]]) -> dict[str, Any]:
    latest_runs = [
        item.get("runCoverage") or {}
        for item in coverage_items
        if (item.get("runCoverage") or {}).get("latestRunId")
    ]
    latest_runs = sorted(latest_runs, key=lambda item: str(item.get("latestCreatedAt") or ""), reverse=True)
    task_total = sum(int((item.get("taskContractCoverage") or {}).get("total") or 0) for item in coverage_items)
    task_complete = sum(int((item.get("taskContractCoverage") or {}).get("complete") or 0) for item in coverage_items)
    task_evaluation_ready = sum(int((item.get("taskContractCoverage") or {}).get("evaluationReady") or 0) for item in coverage_items)
    missing_task_fields: dict[str, int] = {}
    for item in coverage_items:
        for field in (item.get("taskContractCoverage") or {}).get("missingFields") or []:
            key = str(field.get("name") if isinstance(field, dict) else field or "").strip()
            if key:
                missing_task_fields[key] = missing_task_fields.get(key, 0) + int((field.get("count") if isinstance(field, dict) else 1) or 0)
    run_total = sum(int((item.get("runCoverage") or {}).get("total") or 0) for item in coverage_items)
    run_pass = sum(int((item.get("runCoverage") or {}).get("pass") or 0) for item in coverage_items)
    run_fail = sum(int((item.get("runCoverage") or {}).get("fail") or 0) for item in coverage_items)
    run_pending = sum(int((item.get("runCoverage") or {}).get("pending") or 0) for item in coverage_items)
    skill_ids = _dedupe_strings([
        skill_id
        for item in coverage_items
        for skill_id in ((item.get("skillCoverage") or {}).get("skillIds") or [])
    ])
    ready_skills = sum(int((item.get("skillCoverage") or {}).get("ready") or 0) for item in coverage_items)
    published_skills = sum(int((item.get("skillCoverage") or {}).get("published") or 0) for item in coverage_items)
    portfolio = {
        "benchmarks": len(coverage_items),
        "tasks": task_total,
        "taskContracts": {
            "complete": task_complete,
            "total": task_total,
            "evaluationReady": task_evaluation_ready,
            "coverageRatio": round(task_complete / task_total, 3) if task_total else 0.0,
            "missingFields": [{"name": key, "count": missing_task_fields[key]} for key in sorted(missing_task_fields, key=lambda item: (-missing_task_fields[item], item))],
        },
        "connectors": _dedupe_strings([connector_id for item in coverage_items for connector_id in (item.get("connectorIds") or [])]),
        "systems": _dedupe_strings([system for item in coverage_items for system in (item.get("systems") or [])]),
        "entities": _dedupe_strings([entity for item in coverage_items for entity in (item.get("entityNames") or [])]),
        "artifacts": _dedupe_strings([artifact for item in coverage_items for artifact in (item.get("expectedArtifacts") or [])]),
        "skills": {
            "skillIds": skill_ids,
            "total": len(skill_ids),
            "ready": ready_skills,
            "published": published_skills,
        },
        "regressions": {
            "total": run_total,
            "pass": run_pass,
            "fail": run_fail,
            "pending": run_pending,
            "passRatio": round(run_pass / run_total, 3) if run_total else 0.0,
            "latest": [
                {
                    "runId": str(item.get("latestRunId") or ""),
                    "label": str(item.get("latestLabel") or ""),
                    "createdAt": item.get("latestCreatedAt"),
                }
                for item in latest_runs[:5]
            ],
        },
        "promotionGate": promotion_gate(
            task_total=task_total,
            task_complete=task_complete,
            skill_total=len(skill_ids),
            ready_skills=ready_skills,
            published_skills=published_skills,
            run_total=run_total,
            run_pass=run_pass,
            run_fail=run_fail,
        ),
    }
    matrix = coverage_matrix(coverage_items)
    portfolio["coverageMatrix"] = matrix
    portfolio["regressionGate"] = regression_gate_from_matrix(matrix)
    gap_counts: dict[str, int] = {}
    for blocker in portfolio["promotionGate"].get("blockers") or []:
        if blocker == "incomplete_task_contracts":
            gap_counts[blocker] = max(0, task_total - task_complete)
        elif blocker == "no_skills":
            gap_counts[blocker] = max(1, len(coverage_items))
        elif blocker == "no_ready_skills":
            gap_counts[blocker] = max(0, len(skill_ids) - ready_skills)
        elif blocker == "no_regression_runs":
            gap_counts[blocker] = max(1, len(coverage_items))
        elif blocker == "failing_regressions":
            gap_counts[blocker] = max(1, run_fail)
        else:
            gap_counts[blocker] = gap_counts.get(blocker, 0) + 1
    regression_gate = portfolio["regressionGate"]
    if regression_gate.get("state") == "empty":
        gap_counts["empty_regression_matrix"] = max(1, len(coverage_items))
    for blocker in regression_gate.get("blockers") or []:
        if blocker == "missing_regression":
            count = sum(int(item.get("count") or 0) for item in regression_gate.get("missingRegression") or [])
        elif blocker == "failing_regression":
            count = sum(int(item.get("count") or 0) for item in regression_gate.get("failingRegression") or [])
        elif blocker == "skill_hardening":
            count = sum(int(item.get("count") or 0) for item in regression_gate.get("needsHardening") or [])
        else:
            count = 1
        gap_counts[blocker] = gap_counts.get(blocker, 0) + max(1, count)
    portfolio["hardeningPlaybook"] = _benchmark_portfolio_playbook({key: count for key, count in gap_counts.items() if count})
    return portfolio


def regression_gate_from_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    rows_by_kind = {
        "connectors": matrix.get("connectors") if isinstance(matrix.get("connectors"), list) else [],
        "entities": matrix.get("entities") if isinstance(matrix.get("entities"), list) else [],
        "skills": matrix.get("skills") if isinstance(matrix.get("skills"), list) else [],
    }
    missing: dict[str, int] = {}
    failing: dict[str, int] = {}
    needs_hardening: dict[str, int] = {}
    ungated_samples: list[dict[str, Any]] = []
    failing_samples: list[dict[str, Any]] = []
    total = 0
    gated = 0
    for kind, rows in rows_by_kind.items():
        for row in rows:
            if not isinstance(row, dict):
                continue
            total += 1
            state = str(row.get("state") or "unknown")
            if state in {"passing", "ready", "published"}:
                gated += 1
            if state == "missing_regression":
                missing[kind] = missing.get(kind, 0) + 1
                if len(ungated_samples) < 8:
                    ungated_samples.append(_regression_gate_sample(row, kind=kind))
            if state == "failing":
                failing[kind] = failing.get(kind, 0) + 1
                if len(failing_samples) < 8:
                    failing_samples.append(_regression_gate_sample(row, kind=kind))
            if state == "needs_hardening" or str(row.get("hardeningState") or "") == "needs_hardening":
                needs_hardening[kind] = needs_hardening.get(kind, 0) + 1
    blockers: list[str] = []
    next_actions: list[str] = []
    if sum(missing.values()):
        blockers.append("missing_regression")
        next_actions.append("Run benchmark regressions for uncovered connectors, entities and skills before promotion.")
    if sum(failing.values()):
        blockers.append("failing_regression")
        next_actions.append("Inspect failing regression traces and fix the underlying capability before publishing.")
    if sum(needs_hardening.values()):
        blockers.append("skill_hardening")
        next_actions.append("Harden skills before treating regression coverage as production-ready.")
    if not total:
        state = "empty"
        next_actions.append("Create benchmarks that reference connectors, entities or skills before evaluating coverage.")
    elif failing:
        state = "failing"
    elif missing or needs_hardening:
        state = "needs_regression"
    else:
        state = "ready"
    return {
        "state": state,
        "ready": state == "ready",
        "totalCapabilities": total,
        "gatedCapabilities": gated,
        "coverageRatio": round(gated / total, 3) if total else 0.0,
        "blockers": blockers,
        "missingRegression": _counts_by_kind(missing),
        "failingRegression": _counts_by_kind(failing),
        "needsHardening": _counts_by_kind(needs_hardening),
        "ungatedSamples": ungated_samples,
        "failingSamples": failing_samples,
        "nextActions": next_actions,
    }


def _counts_by_kind(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"kind": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _regression_gate_sample(row: dict[str, Any], *, kind: str) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "kind": kind,
        "state": str(row.get("state") or ""),
        "benchmarkRefs": _dedupe_strings(row.get("benchmarkRefs") if isinstance(row.get("benchmarkRefs"), list) else []),
        "regressions": row.get("regressions") if isinstance(row.get("regressions"), dict) else {},
    }


def coverage_matrix(coverage_items: list[dict[str, Any]]) -> dict[str, Any]:
    connectors: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    skills: dict[str, dict[str, Any]] = {}

    def _run_state(run_coverage: dict[str, Any]) -> str:
        total = int(run_coverage.get("total") or 0)
        fail = int(run_coverage.get("fail") or 0)
        passed = int(run_coverage.get("pass") or 0)
        if total == 0:
            return "missing_regression"
        if fail:
            return "failing"
        if passed:
            return "passing"
        return "pending"

    def _touch_row(table: dict[str, dict[str, Any]], key: str, *, kind: str, benchmark_index: int, run_coverage: dict[str, Any]) -> None:
        row = table.setdefault(
            key,
            {
                "id": key,
                "kind": kind,
                "benchmarkCount": 0,
                "benchmarkRefs": [],
                "regressions": {"total": 0, "pass": 0, "fail": 0, "pending": 0},
                "state": "missing_regression",
            },
        )
        benchmark_ref = f"benchmark:{benchmark_index}"
        if benchmark_ref not in row["benchmarkRefs"]:
            row["benchmarkRefs"].append(benchmark_ref)
            row["benchmarkCount"] += 1
        regressions = row["regressions"]
        regressions["total"] += int(run_coverage.get("total") or 0)
        regressions["pass"] += int(run_coverage.get("pass") or 0)
        regressions["fail"] += int(run_coverage.get("fail") or 0)
        regressions["pending"] += int(run_coverage.get("pending") or 0)
        row_state = _run_state(regressions)
        row["state"] = row_state
        row["covered"] = row_state in {"passing", "pending"}

    for index, item in enumerate(coverage_items):
        run_coverage = item.get("runCoverage") if isinstance(item.get("runCoverage"), dict) else {}
        for connector_id in item.get("connectorIds") or []:
            _touch_row(connectors, str(connector_id), kind="connector", benchmark_index=index, run_coverage=run_coverage)
        for entity_name in item.get("entityNames") or []:
            _touch_row(entities, str(entity_name), kind="entity", benchmark_index=index, run_coverage=run_coverage)
        skill_coverage = item.get("skillCoverage") if isinstance(item.get("skillCoverage"), dict) else {}
        skill_state = "published" if int(skill_coverage.get("published") or 0) else "ready" if int(skill_coverage.get("ready") or 0) else "needs_hardening"
        for skill_id in skill_coverage.get("skillIds") or []:
            row = skills.setdefault(
                str(skill_id),
                {
                    "id": str(skill_id),
                    "kind": "skill",
                    "benchmarkCount": 0,
                    "benchmarkRefs": [],
                    "regressions": {"total": 0, "pass": 0, "fail": 0, "pending": 0},
                    "state": skill_state,
                    "covered": skill_state in {"ready", "published"},
                },
            )
            row["baseState"] = "published" if row.get("baseState") == "published" or skill_state == "published" else skill_state
            benchmark_ref = f"benchmark:{index}"
            if benchmark_ref not in row["benchmarkRefs"]:
                row["benchmarkRefs"].append(benchmark_ref)
                row["benchmarkCount"] += 1
            regressions = row["regressions"]
            regressions["total"] += int(run_coverage.get("total") or 0)
            regressions["pass"] += int(run_coverage.get("pass") or 0)
            regressions["fail"] += int(run_coverage.get("fail") or 0)
            regressions["pending"] += int(run_coverage.get("pending") or 0)
            regression_state = _run_state(regressions)
            base_state = str(row.get("baseState") or skill_state)
            if regression_state == "failing":
                row["state"] = "failing"
            elif base_state == "needs_hardening":
                row["state"] = base_state
            elif regression_state == "missing_regression":
                row["state"] = regression_state
            else:
                row["state"] = base_state
            row["covered"] = row["state"] in {"ready", "published"}

    def _sorted_rows(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        clean_rows = []
        for row in rows.values():
            clean = dict(row)
            if clean.get("baseState") == "needs_hardening":
                clean["hardeningState"] = "needs_hardening"
            clean.pop("baseState", None)
            clean_rows.append(clean)
        return sorted(clean_rows, key=lambda row: (-int(row.get("benchmarkCount") or 0), str(row.get("id") or "")))

    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        states: dict[str, int] = {}
        covered = 0
        for row in rows:
            state = str(row.get("state") or "unknown")
            states[state] = states.get(state, 0) + 1
            if row.get("covered"):
                covered += 1
        total = len(rows)
        return {
            "total": total,
            "covered": covered,
            "coverageRatio": round(covered / total, 3) if total else 0.0,
            "states": [{"name": key, "count": states[key]} for key in sorted(states, key=lambda item: (-states[item], item))],
        }

    connector_rows = _sorted_rows(connectors)
    entity_rows = _sorted_rows(entities)
    skill_rows = _sorted_rows(skills)

    return {
        "connectors": connector_rows,
        "entities": entity_rows,
        "skills": skill_rows,
        "summary": {
            "connectors": _summary(connector_rows),
            "entities": _summary(entity_rows),
            "skills": _summary(skill_rows),
        },
    }
