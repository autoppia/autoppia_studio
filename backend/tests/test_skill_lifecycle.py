from app.services.skill_lifecycle import (
    append_skill_version_event,
    skill_lifecycle_fields,
    skill_promotion_status,
    skill_version,
    skill_version_history,
)


def test_skill_lifecycle_normalizes_version_and_promotion_status():
    assert skill_version({"version": "3"}) == 3
    assert skill_version({"version": "invalid"}) == 1
    assert skill_promotion_status({"promotionStatus": "published", "status": "draft"}) == "published"
    assert skill_promotion_status({"status": "approved"}) == "published"
    assert skill_promotion_status({"status": "needs_harvest"}) == "draft"


def test_skill_lifecycle_fields_marks_publish_and_archive_timestamps():
    published = skill_lifecycle_fields(
        previous={"promotionStatus": "ready", "readyAt": "t-ready"},
        next_doc={"promotionStatus": "published"},
        now="t-now",
    )
    archived = skill_lifecycle_fields(
        previous={"promotionStatus": "published"},
        next_doc={"promotionStatus": "archived"},
        now="t-archive",
    )

    assert published == {
        "promotionStatus": "published",
        "publishedAt": "t-now",
        "readyAt": "t-ready",
        "lastPromotedAt": "t-now",
    }
    assert archived == {
        "promotionStatus": "archived",
        "archivedAt": "t-archive",
        "lastPromotedAt": "t-archive",
    }


def test_skill_version_history_normalizes_and_appends_events():
    previous = {
        "versionHistory": [
            {"version": "2", "status": "ready", "reason": "material_update", "updatedAt": "t-2"},
            "bad",
            {"version": "1", "promotionStatus": "draft", "reason": "initial", "createdAt": "t-1"},
        ]
    }
    history = skill_version_history(previous, version=2, promotion_status="ready")
    appended = append_skill_version_event(
        previous,
        {"version": 3, "promotionStatus": "published", "versionLabel": "v3"},
        now="t-3",
        reason="promotion_status_change",
    )

    assert [event["version"] for event in history] == [1, 2]
    assert history[1]["promotionStatus"] == "ready"
    assert appended[-1] == {
        "version": 3,
        "versionLabel": "v3",
        "promotionStatus": "published",
        "reason": "promotion_status_change",
        "createdAt": "t-3",
    }
