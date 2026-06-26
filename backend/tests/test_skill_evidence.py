from app.services.skill_evidence import skill_hardening_status
from app.services.skill_evidence import skill_lineage
from app.services.skill_evidence import source_trajectory_evidence


def test_source_trajectory_evidence_serializes_review_and_action_counts() -> None:
    evidence = source_trajectory_evidence(
        [
            {
                "trajectoryId": "traj-1",
                "taskId": "task-1",
                "benchmarkId": "bench-1",
                "evalId": "eval-1",
                "taskName": "Reply to claim status",
                "status": "approved",
                "review": {"label": "pass"},
                "connectorIds": ["erp", "erp", ""],
                "toolIds": ["claims.search", "claims.search", "email.draft"],
                "steps": [{"type": "tool"}, {"type": "artifact"}],
                "createdAt": "2026-06-01T00:00:00Z",
            }
        ]
    )

    assert evidence == [
        {
            "trajectoryId": "traj-1",
            "taskId": "task-1",
            "benchmarkId": "bench-1",
            "evalId": "eval-1",
            "name": "Reply to claim status",
            "status": "approved",
            "judgeLabel": "pass",
            "connectorIds": ["erp"],
            "toolIds": ["claims.search", "email.draft"],
            "actionCount": 2,
            "createdAt": "2026-06-01T00:00:00Z",
            "updatedAt": None,
        }
    ]


def test_skill_lineage_merges_skill_and_trajectory_evidence() -> None:
    lineage = skill_lineage(
        {
            "benchmarkId": "bench-1",
            "evalId": "eval-1",
            "connectorIds": ["erp"],
            "toolIds": ["claims.search"],
            "trajectoryIds": ["traj-1"],
            "source": "manual",
        },
        [
            {
                "benchmarkId": "bench-1",
                "evalId": "eval-2",
                "connectorIds": ["erp", "mail"],
                "toolIds": ["email.draft"],
                "source": "harvester",
            }
        ],
    )

    assert lineage == {
        "trajectoryIds": ["traj-1"],
        "benchmarkIds": ["bench-1"],
        "evalIds": ["eval-1", "eval-2"],
        "connectorIds": ["erp", "mail"],
        "toolIds": ["claims.search", "email.draft"],
        "sources": ["manual", "harvester"],
    }


def test_skill_hardening_status_marks_publishable_skill_hardened() -> None:
    status = skill_hardening_status(
        {
            "whenToUse": "Use for claim status replies.",
            "instructions": "Search claim, summarize status, draft response.",
            "riskPolicy": "Draft only; sending requires approval.",
            "trajectoryIds": ["traj-1"],
            "inputEntities": ["Claim"],
            "expectedArtifacts": ["email_draft"],
        },
        trajectory_docs=[],
        latest_regression={"label": "pass"},
    )

    assert status["state"] == "hardened"
    assert status["passedChecks"] == status["totalChecks"]
    assert status["checks"]["publishableRegression"] is True


def test_skill_hardening_status_requires_passing_regression() -> None:
    status = skill_hardening_status(
        {
            "whenToUse": "Use for claim status replies.",
            "instructions": "Search claim, summarize status, draft response.",
            "riskPolicy": "Draft only; sending requires approval.",
            "trajectoryIds": ["traj-1"],
        },
        trajectory_docs=[],
        latest_regression={"label": "fail"},
    )

    assert status["state"] == "drafting"
    assert status["checks"]["regression"] is True
    assert status["checks"]["publishableRegression"] is False
