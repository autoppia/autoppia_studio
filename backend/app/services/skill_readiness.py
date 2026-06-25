from __future__ import annotations

from typing import Any


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def skill_reusability_checks(skill: dict[str, Any]) -> dict[str, bool]:
    """Checks for whether a skill has enough package metadata to operate as reusable capability."""
    activation = bool(
        str(skill.get("whenToUse") or skill.get("activationDescription") or "").strip()
        or _string_list(skill.get("sourceTrajectoryIds"))
        or _string_list(skill.get("trajectoryIds"))
    )
    artifacts = bool(_string_list(skill.get("expectedArtifacts")) or _string_list(skill.get("preconditions")) or skill.get("outputCard"))
    return {
        "activation": activation,
        "instructions": bool(str(skill.get("instructions") or "").strip()),
        "artifacts": artifacts,
    }


def skill_reusability_ready(skill: dict[str, Any]) -> bool:
    checks = skill_reusability_checks(skill)
    return all(checks.values())
