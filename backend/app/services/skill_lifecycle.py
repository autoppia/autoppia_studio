from __future__ import annotations

from typing import Any


def skill_version(doc: dict[str, Any]) -> int:
    try:
        value = int(doc.get("version") or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, value)


def skill_promotion_status(doc: dict[str, Any]) -> str:
    explicit = str(doc.get("promotionStatus") or "").strip().lower()
    if explicit in {"draft", "ready", "published", "archived"}:
        return explicit
    status = str(doc.get("status") or "draft").strip().lower()
    if status in {"draft", "ready", "published", "archived"}:
        return status
    if status in {"approved", "active", "completed"}:
        return "published"
    if status in {"needs_review", "needs_harvest"}:
        return "draft"
    return "draft"


def skill_lifecycle_fields(*, previous: dict[str, Any], next_doc: dict[str, Any], now: str) -> dict[str, Any]:
    previous_status = skill_promotion_status(previous)
    next_status = skill_promotion_status(next_doc)
    update: dict[str, Any] = {"promotionStatus": next_status}
    if next_status == "ready" and not next_doc.get("readyAt"):
        update["readyAt"] = now
    if next_status == "published":
        update["publishedAt"] = next_doc.get("publishedAt") or now
        update["readyAt"] = next_doc.get("readyAt") or previous.get("readyAt") or now
    if next_status == "archived" and not next_doc.get("archivedAt"):
        update["archivedAt"] = now
    if previous_status != next_status:
        update["lastPromotedAt"] = now
    return update


def skill_version_history(doc: dict[str, Any], *, version: int, promotion_status: str) -> list[dict[str, Any]]:
    history = doc.get("versionHistory") if isinstance(doc.get("versionHistory"), list) else []
    normalized = []
    for event in history:
        if not isinstance(event, dict):
            continue
        try:
            event_version = max(1, int(event.get("version") or 1))
        except (TypeError, ValueError):
            event_version = 1
        normalized.append(
            {
                "version": event_version,
                "versionLabel": str(event.get("versionLabel") or f"v{event_version}"),
                "promotionStatus": str(event.get("promotionStatus") or event.get("status") or "draft"),
                "reason": str(event.get("reason") or "updated"),
                "createdAt": event.get("createdAt") or event.get("updatedAt") or doc.get("updatedAt") or doc.get("createdAt"),
            }
        )
    if normalized:
        return sorted(normalized, key=lambda item: (item.get("version") or 1, str(item.get("createdAt") or "")))
    return [
        {
            "version": version,
            "versionLabel": doc.get("versionLabel") or f"v{version}",
            "promotionStatus": promotion_status,
            "reason": "initial_package",
            "createdAt": doc.get("createdAt") or doc.get("updatedAt"),
        }
    ]


def append_skill_version_event(
    previous: dict[str, Any],
    next_doc: dict[str, Any],
    *,
    now: str,
    reason: str,
) -> list[dict[str, Any]]:
    history = [] if not previous else skill_version_history(
        previous,
        version=skill_version(previous),
        promotion_status=skill_promotion_status(previous),
    )
    version = skill_version(next_doc)
    event = {
        "version": version,
        "versionLabel": next_doc.get("versionLabel") or f"v{version}",
        "promotionStatus": skill_promotion_status(next_doc),
        "reason": reason,
        "createdAt": now,
    }
    if not history or any(
        event.get(key) != history[-1].get(key)
        for key in ("version", "promotionStatus", "reason")
    ):
        history.append(event)
    return history[-25:]
