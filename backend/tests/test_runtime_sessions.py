from app.services.runtime_sessions import build_runtime_metrics, build_runtime_timeline, build_session_contract, summarize_session_contracts


def test_build_runtime_metrics_dedupes_trace_ids_and_sums_step_latency():
    metrics = build_runtime_metrics(
        action_history=[
            {"action": "browser.navigate", "elapsedSeconds": "1.25", "traceId": "trace-1"},
            {"action": "imap.search_emails", "durationSeconds": 0.75, "trace_id": "trace-2"},
            {"action": "runtime.noop", "latencySeconds": 0, "runId": "trace-1"},
            "bad",
        ],
        runtime_state={"runId": "run-1", "workItemId": "work-1", "traceId": "trace-1"},
        credits_spent=2.5,
        browser_action_count=1,
        connector_action_count=1,
        runtime_kind="hybrid",
    )

    assert metrics == {
        "runtimeKind": "hybrid",
        "creditsSpent": 2.5,
        "durationSeconds": 2.0,
        "lastStepSeconds": 0.75,
        "browserActionCount": 1,
        "connectorActionCount": 1,
        "stepLatencyCount": 2,
        "traceIds": ["trace-1", "run-1", "work-1", "trace-2"],
    }


def test_build_runtime_timeline_normalizes_actions_status_and_trace_fields():
    timeline = build_runtime_timeline(
        [
            {"action": "browser.navigate", "emittedAt": "t-1", "elapsedSeconds": "1.25", "traceId": "trace-browser"},
            {"name": "imap.search_emails", "state": "running", "durationSeconds": 0.5, "trace_id": "trace-mail", "toolCallId": "call-1"},
            {"action": "skill.use", "success": False, "latencySeconds": 0.2, "matchedSkillId": "skill-1"},
            "bad",
            {"action": ""},
        ]
    )

    assert timeline == [
        {
            "index": 0,
            "action": "browser.navigate",
            "label": "Navigate",
            "activity": "browser",
            "status": "ok",
            "emittedAt": "t-1",
            "elapsedSeconds": 1.25,
            "traceId": "trace-browser",
            "toolCallId": "",
            "approvalKey": "",
            "artifactId": "",
            "skillId": "",
        },
        {
            "index": 1,
            "action": "imap.search_emails",
            "label": "imap.search_emails",
            "activity": "tool",
            "status": "pending",
            "emittedAt": "",
            "elapsedSeconds": 0.5,
            "traceId": "trace-mail",
            "toolCallId": "call-1",
            "approvalKey": "",
            "artifactId": "",
            "skillId": "",
        },
        {
            "index": 2,
            "action": "skill.use",
            "label": "Using skill",
            "activity": "skill",
            "status": "failed",
            "emittedAt": "",
            "elapsedSeconds": 0.2,
            "traceId": "",
            "toolCallId": "",
            "approvalKey": "",
            "artifactId": "",
            "skillId": "skill-1",
        },
    ]


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
