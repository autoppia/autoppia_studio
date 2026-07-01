from __future__ import annotations

import json
import os
from typing import Any

from ica.demo_companies.materializer import _mode_for
from ica.schemas import (
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaTaskDiscoveryEvaluation,
    IcaTaskDiscoveryExpectation,
    IcaTaskDiscoveryMatch,
)


def _selected_project_tasks(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[Any]:
    mode_config = _mode_for(project, mode)
    task_filter = set(mode_config.taskIds if mode_config else [])
    surface_filter = set((mode_config.discoveryInput or mode_config.surfaceFilter) if mode_config else [])
    if task_filter:
        return [task for task in project.tasks if task.taskId in task_filter]
    return [
        task
        for task in project.tasks
        if not surface_filter or bool(set(task.expectedSurfaces) & surface_filter)
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
    stop = {
        "the",
        "and",
        "for",
        "with",
        "using",
        "use",
        "from",
        "into",
        "all",
        "una",
        "con",
        "para",
        "que",
        "los",
        "las",
        "task",
        "workflow",
        "primary",
    }
    return {part for part in clean.split() if part and part not in stop}


def _task_text(task: dict[str, Any]) -> str:
    return " ".join(str(task.get(key) or "") for key in ("name", "taskName", "prompt", "successCriteria"))


def _task_id(task: dict[str, Any], fallback: str = "") -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(task.get("taskId") or task.get("id") or metadata.get("icaTaskId") or fallback)


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


def _llm_task_match_enabled() -> bool:
    configured = str(os.getenv("ICA_TASK_DISCOVERY_JUDGE") or "").strip().lower()
    if configured not in {"llm", "hybrid"}:
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


def _llm_task_match_score(
    expectation: IcaTaskDiscoveryExpectation,
    expected_name: str,
    expected_prompt: str,
    discovered: dict[str, Any],
) -> tuple[float | None, str]:
    if not _llm_task_match_enabled():
        return None, "llm_disabled"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("ICA_TASK_DISCOVERY_JUDGE_MODEL", "gpt-5-mini"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Judge whether a discovered company automation task covers the same core business "
                        "use case as an expected benchmark task. Extra scope is acceptable if the expected "
                        "task is clearly covered. Return only JSON with score, matched and reason."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "expected": {
                                "taskId": expectation.taskId,
                                "name": expected_name,
                                "prompt": expected_prompt,
                                "aliases": expectation.aliases,
                                "keywords": expectation.keywords,
                                "expectedSurfaces": expectation.expectedSurfaces,
                            },
                            "discovered": discovered,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        return max(0.0, min(1.0, float(parsed.get("score", 0.0)))), str(parsed.get("reason") or "LLM semantic match.")
    except Exception as exc:  # pragma: no cover - external judge fallback
        return None, f"llm_unavailable:{type(exc).__name__}"


def _judge_task_match(
    expectation: IcaTaskDiscoveryExpectation,
    expected_name: str,
    expected_prompt: str,
    discovered: dict[str, Any],
) -> tuple[float, str, str]:
    rules_score = _task_match_score(expectation, expected_name, discovered)
    if expectation.judge in {"llm", "hybrid"}:
        llm_score, llm_reason = _llm_task_match_score(expectation, expected_name, expected_prompt, discovered)
        if llm_score is not None and (expectation.judge == "llm" or llm_score >= rules_score):
            return round(llm_score, 4), "llm", llm_reason
        return rules_score, "hybrid", f"Rules fallback; {llm_reason}."
    return rules_score, "rules", "Matched by aliases/keywords/token overlap."


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
        expected_prompt = str((expected.prompt if expected else "") or "")
        best_index = -1
        best_score = 0.0
        best_judge = expectation.judge
        best_reason = "No discovered task reached the required similarity threshold."
        for index, task in enumerate(discovered_tasks):
            if index in used_discovered:
                continue
            score, judge, reason = _judge_task_match(expectation, expected_name, expected_prompt, task)
            if score > best_score:
                best_index = index
                best_score = score
                best_judge = judge  # type: ignore[assignment]
                best_reason = reason
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
                    judge=best_judge,
                    reason=best_reason,
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
                    judge=best_judge,
                    reason=best_reason,
                )
            )

    matched_count = len(used_discovered)
    expected_count = len(expectations)
    discovered_count = len(discovered_tasks)
    recall = round(matched_count / expected_count, 4) if expected_count else 1.0
    precision = round(matched_count / discovered_count, 4) if discovered_count else (1.0 if expected_count == 0 else 0.0)
    extra = [
        str(task.get("name") or task.get("taskName") or task.get("prompt") or "")
        for index, task in enumerate(discovered_tasks)
        if index not in used_discovered
    ]
    return IcaTaskDiscoveryEvaluation(
        projectId=project.projectId,
        mode=mode,
        passed=not missing,
        score=recall,
        recall=recall,
        precision=precision,
        expectedCount=expected_count,
        discoveredCount=discovered_count,
        matchedCount=matched_count,
        matches=matches,
        missingTaskIds=missing,
        extraTaskNames=extra,
    )
