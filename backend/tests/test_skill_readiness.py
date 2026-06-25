from app.services.skill_readiness import skill_reusability_checks, skill_reusability_ready


def test_skill_reusability_ready_requires_activation_instructions_and_outputs():
    skill = {
        "whenToUse": "Use when a customer asks about claim status.",
        "instructions": "Check ERP state, draft response and stop before sending.",
        "expectedArtifacts": ["draft_email"],
        "riskPolicy": "human_approval_for_writes",
        "trajectoryIds": ["traj-1"],
    }

    assert skill_reusability_ready(skill) is True
    assert skill_reusability_checks(skill) == {
        "activation": True,
        "instructions": True,
        "artifacts": True,
        "policy": True,
        "evidence": True,
    }


def test_skill_reusability_accepts_source_trajectory_activation():
    skill = {
        "trajectoryIds": ["traj-1"],
        "instructions": "Replay approved path with parameterized inputs.",
        "preconditions": ["claim id available"],
        "runtimePolicy": {"approvalMode": "auto"},
    }

    assert skill_reusability_ready(skill) is True


def test_skill_reusability_accepts_portable_skill_package_evidence():
    skill = {
        "instructions": "Use the packaged workflow with parameterized inputs.",
        "skillPackage": {
            "format": "autoppia.agent_skill",
            "activation": {"description": "Use for claim status follow-up."},
            "ioContract": {"outputs": {"artifacts": ["draft_email"]}},
            "policies": {"runtimePolicy": {"approvalMode": "always"}},
            "evidence": {
                "lineage": {"trajectoryIds": ["traj-1"]},
                "regressionSuite": {"benchmarkIds": ["bench-1"], "evalIds": ["task-1"]},
            },
        },
    }

    assert skill_reusability_checks(skill) == {
        "activation": True,
        "instructions": True,
        "artifacts": True,
        "policy": True,
        "evidence": True,
    }
    assert skill_reusability_ready(skill) is True


def test_skill_reusability_rejects_missing_package_metadata():
    assert skill_reusability_ready({"instructions": "Do it"}) is False
