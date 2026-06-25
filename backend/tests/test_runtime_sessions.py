from app.services.runtime_sessions import build_session_contract, summarize_session_contracts


def test_build_session_contract_serializes_runtime_skill_artifacts_and_trace():
    summary = {
        "sessionId": "session-1",
        "runtimeKind": "hybrid",
        "sourceKind": "work",
        "agentId": "agent-1",
        "agentName": "Claims Agent",
        "workItemId": "work-1",
        "runId": "run-1",
        "creditsSpent": 2.5,
        "runtimeMetrics": {"runtimeKind": "hybrid", "durationSeconds": 3.25, "lastStepSeconds": 0.5},
        "runtimePolicyBoundary": {"hasHumanBoundary": True},
        "runtimeLab": {
            "skillMatch": {"matched": True, "skillId": "skill-1", "skillName": "Draft claim reply"},
            "approvals": {"approvedConnectorCalls": 1, "requiredFor": ["send"], "hasHumanBoundary": True},
            "outputs": {"hasBusinessOutput": True, "creditsSpent": 2.5},
        },
        "runtimeEvidence": {
            "trace": {
                "traceIds": ["run-1", "trace-1"],
                "traceCount": 2,
                "timelineSteps": 3,
                "replayReady": True,
            }
        },
    }

    contract = build_session_contract(summary, artifact_count=2, pending_approval_count=1)

    assert contract["contractVersion"] == "2026-06-25"
    assert contract["agentRuntime"] == {
        "runtimeKind": "hybrid",
        "sourceKind": "work",
        "agentId": "agent-1",
        "agentName": "Claims Agent",
        "workItemId": "work-1",
        "runId": "run-1",
    }
    assert contract["selectedSkill"] == {"matched": True, "skillId": "skill-1", "skillName": "Draft claim reply"}
    assert contract["approvalState"] == {
        "pending": 1,
        "approvedConnectorCalls": 1,
        "requiredFor": ["send"],
        "hasHumanBoundary": True,
    }
    assert contract["artifactState"] == {"count": 2, "hasBusinessOutput": True}
    assert contract["costState"]["creditsSpent"] == 2.5
    assert contract["costState"]["durationSeconds"] == 3.25
    assert contract["traceState"]["traceIds"] == ["run-1", "trace-1"]
    assert contract["traceState"]["replayReady"] is True


def test_summarize_session_contracts_counts_buildable_contract_shape():
    contract = build_session_contract(
        {
            "sessionId": "session-1",
            "runtimeKind": "api",
            "runtimeLab": {"skillMatch": {"matched": True, "skillId": "skill-1"}},
            "runtimeEvidence": {"trace": {"traceIds": ["trace-1"], "replayReady": True}},
        },
        artifact_count=1,
        pending_approval_count=0,
    )

    summary = summarize_session_contracts([{"sessionId": "session-1", "sessionContract": contract}])

    assert summary["withContract"] == 1
    assert summary["selectedSkill"] == 1
    assert summary["artifactOutputs"] == 1
    assert summary["traceIds"] == 1
    assert summary["replayReady"] == 1
    assert summary["runtimeKinds"] == [{"name": "api", "count": 1}]
