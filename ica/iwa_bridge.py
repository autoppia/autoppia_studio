from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


IWA_REPO = Path("/home/usuario1/daryxx/autoppia/operator/autoppia_iwa")


def _ensure_iwa_path() -> bool:
    if not IWA_REPO.exists():
        return False
    repo = str(IWA_REPO)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    return True


def load_iwa_trajectory_map(project_id: str) -> dict[str, Any]:
    if not _ensure_iwa_path():
        return {}
    try:
        from autoppia_iwa.src.demo_webs.trajectory_registry import get_trajectory_map

        return get_trajectory_map(project_id) or {}
    except Exception:
        return {}


def iwa_action_tool_calls(project_id: str, use_case: str) -> list[dict[str, Any]]:
    trajectory = load_iwa_trajectory_map(project_id).get(use_case)
    if trajectory is None:
        return []
    try:
        return [action.to_tool_call() for action in (trajectory.actions or [])]
    except Exception:
        return []


def iwa_tests(project_id: str, use_case: str) -> list[dict[str, Any]]:
    trajectory = load_iwa_trajectory_map(project_id).get(use_case)
    if trajectory is None:
        return []
    tests: list[dict[str, Any]] = []
    for test in trajectory.tests or []:
        if hasattr(test, "model_dump"):
            tests.append(test.model_dump(mode="json"))
        elif isinstance(test, dict):
            tests.append(test)
    return tests


def iwa_prompt(project_id: str, use_case: str) -> str:
    trajectory = load_iwa_trajectory_map(project_id).get(use_case)
    return str(getattr(trajectory, "prompt", "") or "")


def iwa_use_case_title(use_case: str) -> str:
    return " ".join(part.capitalize() for part in str(use_case or "").lower().split("_"))


def selected_iwa_use_cases(project_id: str, *, limit: int = 3) -> list[str]:
    preferred = {
        "autocalendar": ["SELECT_MONTH", "ADD_EVENT", "SEARCH_SUBMIT"],
        "autocinema": ["FILM_DETAIL", "ADD_COMMENT", "ADD_TO_WATCHLIST"],
        "autobooks": ["SEARCH_BOOK", "ADD_BOOK", "ADD_TO_CART"],
        "autozone": ["SEARCH_PRODUCT", "ADD_TO_CART", "VIEW_CART"],
        "autodining": ["SEARCH_RESTAURANT", "VIEW_FULL_MENU", "RESERVE_RESTAURANT"],
        "autocrm": ["SEARCH_MATTER", "ADD_NEW_MATTER", "VIEW_MATTER_DETAILS"],
        "automail": ["SEARCH_EMAIL", "TEMPLATE_SENT", "TEMPLATE_SAVED_DRAFT"],
        "autodelivery": ["SEARCH_DELIVERY_RESTAURANT", "ADD_TO_CART_MENU_ITEM", "QUICK_ORDER_STARTED"],
        "autolodge": ["SEARCH_HOTEL", "VIEW_HOTEL", "RESERVE_HOTEL"],
        "autoconnect": ["VIEW_USER_PROFILE", "CONNECT_WITH_USER", "POST_STATUS"],
        "autowork": ["BOOK_A_CONSULTATION", "QUICK_HIRE", "HIRE_CONSULTANT"],
        "autolist": ["AUTOLIST_ADD_TASK_CLICKED", "AUTOLIST_TASK_ADDED", "AUTOLIST_COMPLETE_TASK"],
        "autodrive": ["ENTER_LOCATION", "ENTER_DESTINATION", "SEARCH"],
        "autohealth": ["OPEN_APPOINTMENT_FORM", "SEARCH_DOCTORS", "REFILL_PRESCRIPTION"],
    }
    available = load_iwa_trajectory_map(project_id)
    if not available:
        return []
    selected = [item for item in preferred.get(project_id, []) if item in available]
    if len(selected) < limit:
        selected.extend(item for item in available if item not in selected)
    return selected[:limit]


def iwa_task_spec(*, ica_project_id: str, iwa_project_id: str, use_case: str) -> dict[str, Any]:
    prompt = iwa_prompt(iwa_project_id, use_case) or f"Complete the {iwa_use_case_title(use_case)} workflow."
    title = iwa_use_case_title(use_case)
    return {
        "taskId": f"iwa_{use_case.lower()}",
        "name": title,
        "prompt": f"Using the {ica_project_id.replace('_web', '').title()} web UI, {prompt[0].lower() + prompt[1:] if prompt else title.lower()}.",
        "successCriteria": f"The {use_case} IWA event/test is satisfied.",
        "expectedSurfaces": ["web"],
        "riskClass": "write" if any(term in use_case.lower() for term in ("add", "create", "delete", "edit", "reserve", "book", "send", "post", "hire", "refill")) else "read",
        "metadata": {
            "legacyIwaProject": iwa_project_id,
            "iwaUseCase": use_case,
            "executionTest": {
                "type": "iwa_event",
                "projectId": iwa_project_id,
                "useCase": use_case,
                "requiredTools": [f"{ica_project_id}.web.explore_workflows"],
                "expected": {"eventName": use_case},
            },
            "requiresIwaEvaluator": True,
            "legacyDemoWeb": True,
            "generatedFromIwaRegistry": True,
        },
    }


def iwa_task_discovery_expectation(*, task_id: str, use_case: str) -> dict[str, Any]:
    title = iwa_use_case_title(use_case)
    return {
        "taskId": task_id,
        "aliases": [title, use_case.replace("_", " "), use_case],
        "keywords": [part.lower() for part in use_case.split("_") if part],
        "expectedSurfaces": ["web"],
        "minSimilarity": 0.35,
        "judge": "hybrid",
    }


def iwa_expected_solution(*, ica_project_id: str, iwa_project_id: str, use_case: str) -> dict[str, Any]:
    task_id = f"iwa_{use_case.lower()}"
    title = iwa_use_case_title(use_case)
    return {
        "taskId": task_id,
        "connectors": ["web"],
        "tools": [f"{ica_project_id}.web.explore_workflows"],
        "trajectories": [
            {
                "trajectoryId": f"{ica_project_id}:{task_id}:iwa",
                "description": f"Replay the IWA {use_case} workflow.",
                "toolCalls": [
                    {
                        "toolName": f"{ica_project_id}.web.explore_workflows",
                        "arguments": {
                            "iwaUseCase": use_case,
                            "eventName": use_case,
                            "goal": iwa_prompt(iwa_project_id, use_case) or title,
                        },
                    }
                ],
                "source": "expected",
            }
        ],
        "skills": [
            {
                "skillId": f"{ica_project_id}:{task_id}:skill",
                "name": f"{title} skill",
                "description": f"Complete the {title} workflow in the web UI.",
                "trajectoryIds": [f"{ica_project_id}:{task_id}:iwa"],
                "instructions": iwa_prompt(iwa_project_id, use_case) or title,
                "source": "trajectory",
            }
        ],
        "agentProvider": {"runtimeKind": "claude_code", "provider": "anthropic"},
    }
