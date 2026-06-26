from __future__ import annotations

from typing import Any

from app.services.skill_readiness import skill_reusability_ready
from app.services.task_contracts import task_contract_ready


PROMOTION_PIPELINE_ACTIONS = {
    "task_to_trajectory": {
        "area": "trajectories",
        "severity": "high",
        "action": "Harvest candidate trajectories for benchmark tasks that do not have execution evidence.",
    },
    "trajectory_approval": {
        "area": "judging",
        "severity": "high",
        "action": "Judge and approve generated trajectories before skill promotion.",
    },
    "trajectory_to_skill": {
        "area": "skills",
        "severity": "high",
        "action": "Link skills to approved source trajectories before treating them as reusable capabilities.",
    },
    "skill_hardening": {
        "area": "skills",
        "severity": "high",
        "action": "Harden promoted skills with activation, instructions, artifacts, policy and evidence.",
    },
    "publish_skill": {
        "area": "release",
        "severity": "medium",
        "action": "Publish a hardened skill once task and approved trajectory evidence exist.",
    },
    "pending_trajectory_rows": {
        "area": "data_model",
        "severity": "medium",
        "action": "Keep pending harvest work in benchmark tasks; trajectories should contain generated execution evidence only.",
    },
}


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


def _promotion_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = PROMOTION_PIPELINE_ACTIONS.get(
            gap,
            {
                "area": "capabilities",
                "severity": "medium",
                "action": "Review the Task -> Trajectory -> Skill promotion path before production release.",
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
    legacy_pending_trajectories = [
        trajectory
        for trajectory in trajectories
        if _status(trajectory.get("status")) in {"needs_harvest", "draft", "harvester_pending", "harvesting"}
        or trajectory.get("needs_harvest") is True
    ]
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
    gap_counts: dict[str, int] = {}
    if tasks and tasks_with_trajectory < len(tasks):
        gaps.append({"key": "task_to_trajectory", "label": "Some benchmark tasks have no generated trajectory evidence.", "target": "capabilities"})
        gap_counts["task_to_trajectory"] = len(tasks) - tasks_with_trajectory
    if trajectories and approved_trajectories < len(trajectories):
        gaps.append({"key": "trajectory_approval", "label": "Some generated trajectories are not approved for promotion.", "target": "capabilities"})
        gap_counts["trajectory_approval"] = len(trajectories) - approved_trajectories
    if skills and skills_with_approved_trajectory < len(skills):
        gaps.append({"key": "trajectory_to_skill", "label": "Some skills are not linked to approved source trajectories.", "target": "capabilities"})
        gap_counts["trajectory_to_skill"] = len(skills) - skills_with_approved_trajectory
    if skills and reusable_skills < len(skills):
        gaps.append({"key": "skill_hardening", "label": "Some promoted skills are missing reusable package hardening.", "target": "capabilities"})
        gap_counts["skill_hardening"] = len(skills) - reusable_skills
    if ready_tasks and approved_trajectories and not published_skills:
        gaps.append({"key": "publish_skill", "label": "Approved task/trajectory evidence exists but no skill is published.", "target": "capabilities"})
        gap_counts["publish_skill"] = 1
    if legacy_pending_trajectories:
        gaps.append({"key": "pending_trajectory_rows", "label": "Pending harvest work is still represented as trajectory rows.", "target": "data_model"})
        gap_counts["pending_trajectory_rows"] = len(legacy_pending_trajectories)

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
            "legacyPendingRows": len(legacy_pending_trajectories),
        },
        "skills": {
            "total": len(skills),
            "withTrajectory": skills_with_trajectory,
            "withApprovedTrajectory": skills_with_approved_trajectory,
            "reusable": reusable_skills,
            "published": published_skills,
            "promotionRatio": round(skills_with_approved_trajectory / len(skills), 3) if skills else 0.0,
        },
        "ready": bool(tasks and tasks_with_trajectory and approved_trajectories and skills_with_approved_trajectory and reusable_skills and not legacy_pending_trajectories),
        "path": {
            "taskToTrajectory": bool(tasks_with_trajectory),
            "trajectoryApproved": bool(approved_trajectories),
            "trajectoryToSkill": bool(skills_with_approved_trajectory),
            "skillHardened": bool(reusable_skills),
        },
        "sample": sample,
        "gaps": gaps[:gap_limit],
        "hardeningPlaybook": _promotion_playbook(gap_counts),
    }
