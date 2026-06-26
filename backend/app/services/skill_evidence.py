from typing import Any


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def source_trajectory_evidence(trajectory_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for trajectory in trajectory_docs:
        actions = trajectory.get("steps") or trajectory.get("trajectory") or trajectory.get("actions") or []
        judge = trajectory.get("judge") if isinstance(trajectory.get("judge"), dict) else {}
        review = trajectory.get("review") if isinstance(trajectory.get("review"), dict) else {}
        evidence.append(
            {
                "trajectoryId": trajectory.get("trajectoryId", ""),
                "taskId": trajectory.get("taskId", ""),
                "benchmarkId": trajectory.get("benchmarkId", ""),
                "evalId": trajectory.get("evalId", ""),
                "name": trajectory.get("name") or trajectory.get("taskName", ""),
                "status": trajectory.get("status", ""),
                "judgeLabel": judge.get("label") or review.get("label") or "",
                "connectorIds": _dedupe_strings([str(value or "") for value in trajectory.get("connectorIds") or []]),
                "toolIds": _dedupe_strings([str(value or "") for value in trajectory.get("toolIds") or []]),
                "actionCount": len(actions) if isinstance(actions, list) else 0,
                "createdAt": trajectory.get("createdAt"),
                "updatedAt": trajectory.get("updatedAt"),
            }
        )
    return evidence


def skill_lineage(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]]) -> dict[str, Any]:
    benchmark_ids = _dedupe_strings([str(skill.get("benchmarkId") or "")])
    eval_ids = _dedupe_strings([str(skill.get("evalId") or "")])
    connector_ids = _dedupe_strings([str(value or "") for value in skill.get("connectorIds") or []])
    tool_ids = _dedupe_strings([str(value or "") for value in skill.get("toolIds") or []])
    trajectory_ids = _dedupe_strings([str(value or "") for value in skill.get("trajectoryIds") or []])
    sources = _dedupe_strings([str(skill.get("source") or "")])

    for trajectory in trajectory_docs:
        benchmark_ids.extend(_dedupe_strings([str(trajectory.get("benchmarkId") or "")]))
        eval_ids.extend(_dedupe_strings([str(trajectory.get("evalId") or "")]))
        connector_ids.extend(_dedupe_strings([str(value or "") for value in trajectory.get("connectorIds") or []]))
        tool_ids.extend(_dedupe_strings([str(value or "") for value in trajectory.get("toolIds") or []]))
        sources.extend(_dedupe_strings([str(trajectory.get("source") or "")]))

    return {
        "trajectoryIds": _dedupe_strings(trajectory_ids),
        "benchmarkIds": _dedupe_strings(benchmark_ids),
        "evalIds": _dedupe_strings(eval_ids),
        "connectorIds": _dedupe_strings(connector_ids),
        "toolIds": _dedupe_strings(tool_ids),
        "sources": _dedupe_strings(sources),
    }


def skill_hardening_status(
    skill: dict[str, Any],
    *,
    trajectory_docs: list[dict[str, Any]],
    latest_regression: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = {
        "activation": bool(str(skill.get("whenToUse") or "").strip()),
        "instructions": bool(str(skill.get("instructions") or "").strip()),
        "riskPolicy": bool(str(skill.get("riskPolicy") or "").strip()),
        "lineage": bool(skill.get("trajectoryIds") or trajectory_docs),
        "regression": latest_regression is not None,
        "publishableRegression": bool(latest_regression and latest_regression.get("label") == "pass"),
        "entities": bool((skill.get("inputEntities") or []) or str(skill.get("outputEntity") or "").strip()),
        "artifacts": bool(skill.get("expectedArtifacts") or skill.get("outputCard")),
    }
    passed = sum(1 for value in checks.values() if value)
    return {
        "checks": checks,
        "passedChecks": passed,
        "totalChecks": len(checks),
        "score": round(passed / len(checks), 3) if checks else 0.0,
        "state": "hardened"
        if checks["activation"]
        and checks["instructions"]
        and checks["riskPolicy"]
        and checks["lineage"]
        and checks["publishableRegression"]
        else "drafting",
    }
