from app.services.skill_eval_gates import build_skill_eval_gate
from app.services.skill_eval_gates import summarize_skill_eval_gates


def test_build_skill_eval_gate_blocks_missing_regression_with_next_action():
    gate = build_skill_eval_gate({"capabilityId": "skill-1", "name": "Reply claim"})

    assert gate["state"] == "missing"
    assert gate["hasRegression"] is False
    assert gate["publishable"] is False
    assert gate["blockers"] == ["publishableRegression"]
    assert gate["nextActions"] == ["Run a linked benchmark regression before publishing this skill."]


def test_build_skill_eval_gate_tracks_pending_failing_and_passing_runs():
    skill = {
        "capabilityId": "skill-1",
        "name": "Reply claim",
        "lineage": {"benchmarkIds": ["bench-1"], "evalIds": ["task-1"]},
        "skillPackage": {
            "evidence": {
                "regressionSuite": {"benchmarkIds": ["bench-1"], "evalIds": ["task-1"]},
            }
        },
    }

    pending = build_skill_eval_gate(skill, runs_by_eval_id={"task-1": [{"runId": "run-pending", "label": "running"}]})
    failing = build_skill_eval_gate(skill, runs_by_benchmark_id={"bench-1": [{"runId": "run-fail", "label": "fail"}]})
    passing = build_skill_eval_gate(skill, runs_by_eval_id={"task-1": [{"runId": "run-pass", "label": "pass"}]})

    assert pending["state"] == "pending"
    assert pending["linkedRunIds"] == ["run-pending"]
    assert pending["nextActions"] == ["Wait for the linked regression run to finish before publishing this skill."]
    assert failing["state"] == "failing"
    assert failing["blockers"] == ["failingRegression"]
    assert failing["nextActions"] == ["Inspect failing regression traces and fix the skill before publishing."]
    assert passing["state"] == "passing"
    assert passing["publishable"] is True
    assert passing["blockers"] == []


def test_build_skill_eval_gate_uses_latest_linked_run_as_authoritative_evidence():
    skill = {
        "capabilityId": "skill-1",
        "lineage": {"evalIds": ["task-1"]},
        "skillPackage": {
            "evidence": {
                "regressionSuite": {"evalIds": ["task-1"], "publishable": True},
                "latestRegression": {"label": "pass"},
            }
        },
    }

    failing_latest = build_skill_eval_gate(
        skill,
        runs_by_eval_id={
            "task-1": [
                {"runId": "run-old-pass", "evalId": "task-1", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"},
                {"runId": "run-new-fail", "evalId": "task-1", "label": "fail", "createdAt": "2026-06-26T10:00:00+00:00"},
            ]
        },
    )
    passing_latest = build_skill_eval_gate(
        skill,
        runs_by_eval_id={
            "task-1": [
                {"runId": "run-old-fail", "evalId": "task-1", "label": "fail", "createdAt": "2026-06-25T10:00:00+00:00"},
                {"runId": "run-new-pass", "evalId": "task-1", "label": "pass", "createdAt": "2026-06-26T10:00:00+00:00"},
            ]
        },
    )

    assert failing_latest["state"] == "failing"
    assert failing_latest["publishable"] is False
    assert failing_latest["blockers"] == ["failingRegression"]
    assert failing_latest["latestRun"]["runId"] == "run-new-fail"
    assert passing_latest["state"] == "passing"
    assert passing_latest["publishable"] is True
    assert passing_latest["blockers"] == []
    assert passing_latest["latestRun"]["runId"] == "run-new-pass"


def test_summarize_skill_eval_gates_uses_per_skill_gate_contract_samples():
    summary = summarize_skill_eval_gates(
        [
            {"capabilityId": "skill-pass", "lineage": {"evalIds": ["task-pass"]}},
            {"capabilityId": "skill-fail", "lineage": {"benchmarkIds": ["bench-fail"]}},
            {"capabilityId": "skill-missing"},
        ],
        [
            {"runId": "run-pass", "evalId": "task-pass", "label": "pass"},
            {"runId": "run-fail", "benchmarkId": "bench-fail", "label": "fail"},
        ],
    )

    assert summary["totalSkills"] == 3
    assert summary["benchmarkLinked"] == 2
    assert summary["regressionLinked"] == 2
    assert summary["passing"] == 1
    assert summary["failing"] == 1
    assert summary["missing"] == 1
    assert summary["blockedByRegression"] == 1
    assert summary["hardeningPlaybook"] == [
        {
            "gap": "failingRegression",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Inspect failing regression traces and fix the skill before publishing.",
        },
        {
            "gap": "publishableRegression",
            "count": 1,
            "area": "evals",
            "severity": "high",
            "action": "Run linked benchmark regressions for skills missing publishable evidence.",
        },
    ]
    assert summary["sample"][1]["nextActions"] == ["Inspect failing regression traces and fix the skill before publishing."]
