from __future__ import annotations

from typing import Any

from app.services.skill_readiness import skill_reusability_ready
from app.services.task_contracts import task_contract_ready


def _clean_id(value: Any) -> str:
    return str(value or "").strip()


def _status(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _skill_id(skill: dict[str, Any]) -> str:
    return _clean_id(skill.get("skillId") or skill.get("capabilityId"))


def _trajectory_ids(skill: dict[str, Any]) -> list[str]:
    ids = skill.get("trajectoryIds")
    if not isinstance(ids, list):
        ids = [skill.get("trajectoryId")] if skill.get("trajectoryId") else []
    return [_clean_id(item) for item in ids if _clean_id(item)]


def _published_skill(skill: dict[str, Any]) -> bool:
    return _status(skill.get("promotionStatus") or skill.get("status")) in {"published", "approved", "ready", "production", "active"}


def summarize_promotion_pipeline(
    *,
    tasks: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    sample_limit: int = 8,
    gap_limit: int = 10,
) -> dict[str, Any]:
    task_ids = {_clean_id(task.get("taskId")) for task in tasks if _clean_id(task.get("taskId"))}
    approved_trajectory_ids = {
        _clean_id(trajectory.get("trajectoryId"))
        for trajectory in trajectories
        if _clean_id(trajectory.get("trajectoryId")) and _status(trajectory.get("status")) in {"approved", "accepted"}
    }
    trajectories_by_task = {
        _clean_id(trajectory.get("taskId"))
        for trajectory in trajectories
        if _clean_id(trajectory.get("taskId")) and _clean_id(trajectory.get("trajectoryId"))
    }
    task_declared_trajectories = {
        _clean_id(task.get("taskId"))
        for task in tasks
        if _clean_id(task.get("taskId")) and _clean_id(task.get("trajectoryId"))
    }
    tasks_with_trajectory = len((trajectories_by_task | task_declared_trajectories) & task_ids)
    skills_with_trajectory = 0
    skills_with_approved_trajectory = 0
    sample: list[dict[str, Any]] = []
    for skill in skills:
        trajectory_ids = _trajectory_ids(skill)
        linked_approved = sorted(set(trajectory_ids) & approved_trajectory_ids)
        if trajectory_ids:
            skills_with_trajectory += 1
        if linked_approved:
            skills_with_approved_trajectory += 1
        if len(sample) < sample_limit:
            sample.append(
                {
                    "skillId": _skill_id(skill),
                    "name": str(skill.get("name") or skill.get("title") or _skill_id(skill)),
                    "trajectoryIds": trajectory_ids,
                    "approvedTrajectoryIds": linked_approved,
                    "promotionStatus": _status(skill.get("promotionStatus") or skill.get("status")),
                    "reusable": skill_reusability_ready(skill),
                    "published": _published_skill(skill),
                }
            )

    ready_tasks = sum(1 for task in tasks if task_contract_ready(task))
    approved_trajectories = len(approved_trajectory_ids)
    reusable_skills = sum(1 for skill in skills if skill_reusability_ready(skill))
    published_skills = sum(1 for skill in skills if _published_skill(skill))
    gaps: list[dict[str, str]] = []
    if tasks and tasks_with_trajectory < len(tasks):
        gaps.append({"key": "task_to_trajectory", "label": "Some benchmark tasks have no generated trajectory evidence.", "target": "capabilities"})
    if trajectories and approved_trajectories < len(trajectories):
        gaps.append({"key": "trajectory_approval", "label": "Some generated trajectories are not approved for promotion.", "target": "capabilities"})
    if skills and skills_with_approved_trajectory < len(skills):
        gaps.append({"key": "trajectory_to_skill", "label": "Some skills are not linked to approved source trajectories.", "target": "capabilities"})
    if skills and reusable_skills < len(skills):
        gaps.append({"key": "skill_hardening", "label": "Some promoted skills are missing reusable package hardening.", "target": "capabilities"})
    if ready_tasks and approved_trajectories and not published_skills:
        gaps.append({"key": "publish_skill", "label": "Approved task/trajectory evidence exists but no skill is published.", "target": "capabilities"})

    return {
        "tasks": {
            "total": len(tasks),
            "withContract": ready_tasks,
            "withTrajectory": tasks_with_trajectory,
            "coverageRatio": round(tasks_with_trajectory / len(tasks), 3) if tasks else 0.0,
        },
        "trajectories": {
            "total": len(trajectories),
            "approved": approved_trajectories,
            "linkedToTasks": len(trajectories_by_task & task_ids),
            "approvalRatio": round(approved_trajectories / len(trajectories), 3) if trajectories else 0.0,
        },
        "skills": {
            "total": len(skills),
            "withTrajectory": skills_with_trajectory,
            "withApprovedTrajectory": skills_with_approved_trajectory,
            "reusable": reusable_skills,
            "published": published_skills,
            "promotionRatio": round(skills_with_approved_trajectory / len(skills), 3) if skills else 0.0,
        },
        "ready": bool(tasks and tasks_with_trajectory and approved_trajectories and skills_with_approved_trajectory and reusable_skills),
        "path": {
            "taskToTrajectory": bool(tasks_with_trajectory),
            "trajectoryApproved": bool(approved_trajectories),
            "trajectoryToSkill": bool(skills_with_approved_trajectory),
            "skillHardened": bool(reusable_skills),
        },
        "sample": sample,
        "gaps": gaps[:gap_limit],
    }
