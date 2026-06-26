from app.services.promotion_pipeline import summarize_promotion_pipeline


def test_promotion_pipeline_exposes_hardening_playbook_for_incomplete_flow():
    summary = summarize_promotion_pipeline(
        tasks=[
            {
                "taskId": "task-1",
                "businessIntent": "Reply to claim status",
                "allowedSystems": ["email", "erp"],
                "expectedArtifacts": ["draft_email"],
                "successCriteria": "Draft exists.",
                "riskClass": "draft",
            },
            {"taskId": "task-2"},
        ],
        trajectories=[
            {"trajectoryId": "traj-1", "taskId": "task-1", "status": "approved"},
            {"trajectoryId": "traj-2", "taskId": "task-2", "status": "candidate"},
        ],
        skills=[
            {
                "capabilityId": "skill-1",
                "trajectoryIds": ["traj-missing"],
                "instructions": "Draft reply.",
            }
        ],
    )

    assert summary["tasks"]["withTrajectory"] == 2
    assert summary["trajectories"]["approved"] == 1
    assert summary["skills"]["withApprovedTrajectory"] == 0
    assert summary["gaps"] == [
        {
            "key": "trajectory_approval",
            "label": "Some generated trajectories are not approved for promotion.",
            "target": "capabilities",
        },
        {
            "key": "trajectory_to_skill",
            "label": "Some skills are not linked to approved source trajectories.",
            "target": "capabilities",
        },
        {
            "key": "skill_hardening",
            "label": "Some promoted skills are missing reusable package hardening.",
            "target": "capabilities",
        },
        {
            "key": "publish_skill",
            "label": "Approved task/trajectory evidence exists but no skill is published.",
            "target": "capabilities",
        },
    ]
    assert summary["hardeningPlaybook"] == [
        {
            "gap": "publish_skill",
            "count": 1,
            "area": "release",
            "severity": "medium",
            "action": "Publish a hardened skill once task and approved trajectory evidence exist.",
        },
        {
            "gap": "skill_hardening",
            "count": 1,
            "area": "skills",
            "severity": "high",
            "action": "Harden promoted skills with activation, instructions, artifacts, policy and evidence.",
        },
        {
            "gap": "trajectory_approval",
            "count": 1,
            "area": "judging",
            "severity": "high",
            "action": "Judge and approve generated trajectories before skill promotion.",
        },
        {
            "gap": "trajectory_to_skill",
            "count": 1,
            "area": "skills",
            "severity": "high",
            "action": "Link skills to approved source trajectories before treating them as reusable capabilities.",
        },
    ]


def test_promotion_pipeline_flags_legacy_pending_trajectory_rows():
    summary = summarize_promotion_pipeline(
        tasks=[
            {
                "taskId": "task-1",
                "businessIntent": "Reply to claim status",
                "allowedSystems": ["email", "erp"],
                "expectedArtifacts": ["draft_email"],
                "successCriteria": "Draft exists.",
                "riskClass": "draft",
            }
        ],
        trajectories=[
            {"trajectoryId": "traj-1", "taskId": "task-1", "status": "approved"},
            {"trajectoryId": "legacy-pending", "taskId": "task-2", "status": "needs_harvest"},
        ],
        skills=[
            {
                "capabilityId": "skill-1",
                "trajectoryIds": ["traj-1"],
                "whenToUse": "Use for claim replies.",
                "instructions": "Draft reply.",
                "expectedArtifacts": ["draft_email"],
                "riskPolicy": "human_approval_for_writes",
            }
        ],
    )

    assert summary["ready"] is False
    assert summary["trajectories"]["legacyPendingRows"] == 1
    assert {
        "key": "pending_trajectory_rows",
        "label": "Pending harvest work is still represented as trajectory rows.",
        "target": "data_model",
    } in summary["gaps"]
    assert {
        "gap": "pending_trajectory_rows",
        "count": 1,
        "area": "data_model",
        "severity": "medium",
        "action": "Keep pending harvest work in benchmark tasks; trajectories should contain generated execution evidence only.",
    } in summary["hardeningPlaybook"]
