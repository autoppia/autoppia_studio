from app.services.runtime_sessions import (
    build_runtime_audit_trail,
    build_runtime_evidence,
    build_runtime_lab,
    build_runtime_metrics,
    build_runtime_policy_boundary,
    build_runtime_timeline,
    build_session_contract,
    summarize_session_contracts,
)


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


def test_build_runtime_policy_boundary_counts_side_effect_boundaries_and_approvals():
    boundary = build_runtime_policy_boundary(
        action_history=[
            {"action": "imap.search_emails"},
            {"action": "smtp.draft_email"},
            {"action": "crm.update_record", "approvalRequired": True},
            {"action": "smtp.send_email", "approvalKey": "approval-send"},
            "bad",
        ],
        runtime_state={
            "pendingConnectorApproval": "smtp.send_email:0:abc",
            "approvedConnectorToolCalls": ["crm.update_record:0:def"],
        },
        artifact_count=2,
        pending_approval_count=1,
    )

    assert boundary == {
        "boundaries": {"read": 1, "draft": 3, "write": 1, "send": 1},
        "approvalRequiredFor": ["write", "send"],
        "pendingApprovalCount": 1,
        "approvedApprovalCount": 1,
        "artifactCount": 2,
        "hasHumanBoundary": True,
    }


def test_build_runtime_evidence_summarizes_trace_capability_and_outputs():
    evidence = build_runtime_evidence(
        {
            "runtimeKind": "hybrid",
            "browserActionCount": 1,
            "connectorActionCount": 2,
            "creditsSpent": 3.25,
            "matchedSkillId": "skill-1",
            "matchedSkillName": "Draft claim reply",
            "workItemId": "work-1",
            "runId": "run-1",
            "pendingConnectorApproval": "smtp.send_email:0:abc",
            "runtimeMetrics": {
                "runtimeKind": "hybrid",
                "traceIds": ["run-1", "trace-1", "trace-2"],
                "durationSeconds": 4.5,
            },
            "runtimeTimeline": [
                {"action": "browser.navigate", "status": "ok"},
                {"action": "imap.search_emails", "status": "pending"},
                {"action": "skill.use", "status": "failed"},
            ],
            "runtimePolicyBoundary": {"approvalRequiredFor": ["send"], "hasHumanBoundary": True},
        },
        artifact_count=2,
        pending_approval_count=1,
    )

    assert evidence["summary"] == {
        "runtimeKind": "hybrid",
        "toolCalls": 2,
        "browserSteps": 1,
        "artifacts": 2,
        "pendingApprovals": 1,
        "creditsSpent": 3.25,
        "durationSeconds": 4.5,
    }
    assert evidence["trace"] == {
        "traceIds": ["run-1", "trace-1", "trace-2"],
        "traceCount": 3,
        "timelineSteps": 3,
        "failedSteps": 1,
        "pendingSteps": 1,
        "lastTraceId": "trace-2",
        "replayReady": False,
    }
    assert evidence["capabilityRefs"] == {
        "skillId": "skill-1",
        "skillName": "Draft claim reply",
        "workItemId": "work-1",
        "runId": "run-1",
        "linked": True,
    }
    assert evidence["approvalBoundary"] == {
        "approvalRequiredFor": ["send"],
        "hasHumanBoundary": True,
        "pendingConnectorApproval": "smtp.send_email:0:abc",
    }
    assert evidence["outputs"] == {"artifactCount": 2, "hasBusinessOutput": True}


def test_build_runtime_lab_projects_control_plane_timeline_and_outputs():
    lab = build_runtime_lab(
        {
            "sessionId": "session-1",
            "runtimeKind": "hybrid",
            "sourceKind": "work",
            "agentId": "agent-1",
            "agentName": "Claims Agent",
            "workItemId": "work-1",
            "runId": "run-1",
            "connectorActionCount": 1,
            "matchedSkillId": "skill-1",
            "matchedSkillName": "Draft claim reply",
            "pendingConnectorApproval": "smtp.send_email:0:abc",
            "creditsSpent": 2.5,
            "runtimeMetrics": {
                "runtimeKind": "hybrid",
                "connectorActionCount": 1,
                "traceIds": ["run-1", "trace-tool"],
                "durationSeconds": 3.0,
                "lastStepSeconds": 0.75,
            },
            "runtimePolicyBoundary": {"approvalRequiredFor": ["send"], "hasHumanBoundary": True},
            "runtimeEvidence": {
                "trace": {
                    "traceIds": ["run-1", "trace-tool"],
                    "failedSteps": 0,
                    "pendingSteps": 1,
                    "replayReady": False,
                }
            },
            "runtimeTimeline": [
                {"index": 0, "activity": "browser", "action": "browser.navigate", "label": "Navigate", "status": "ok", "traceId": "trace-browser", "elapsedSeconds": 1.0},
                {"index": 1, "activity": "tool", "action": "imap.search_emails", "label": "imap.search_emails", "status": "ok", "traceId": "trace-tool", "elapsedSeconds": 0.75},
                {"index": 2, "activity": "skill", "action": "skill.use", "label": "Using skill", "status": "pending", "traceId": "trace-skill", "elapsedSeconds": 0.25},
            ],
            "runtimeState": {"approvedConnectorToolCalls": ["smtp.send_email:0:abc"]},
            "latestAction": "skill.use",
            "latestActivityAt": "t-3",
        },
        artifact_count=2,
        pending_approval_count=1,
    )

    assert lab["controlPlane"]["runtimeKind"] == "hybrid"
    assert lab["controlPlane"]["workItemId"] == "work-1"
    assert lab["timeline"]["steps"] == 3
    assert lab["timeline"]["browserSteps"] == 1
    assert lab["timeline"]["toolSteps"] == 1
    assert lab["timeline"]["skillSteps"] == 1
    assert lab["timeline"]["pendingSteps"] == 1
    assert lab["timeline"]["traceIds"] == ["run-1", "trace-tool"]
    assert lab["toolCalls"]["total"] == 1
    assert lab["toolCalls"]["approved"] == 1
    assert lab["toolCalls"]["sample"][0]["action"] == "imap.search_emails"
    assert lab["skillMatch"] == {"matched": True, "skillId": "skill-1", "skillName": "Draft claim reply"}
    assert lab["approvals"] == {
        "pending": 1,
        "approvedConnectorCalls": 1,
        "requiredFor": ["send"],
        "hasHumanBoundary": True,
    }
    assert lab["outputs"] == {
        "artifacts": 2,
        "hasBusinessOutput": True,
        "creditsSpent": 2.5,
        "durationSeconds": 3.0,
        "lastStepSeconds": 0.75,
    }


def test_build_runtime_audit_trail_records_uniform_events_and_boundaries():
    audit = build_runtime_audit_trail(
        {
            "sessionId": "session-1",
            "createdAt": "t-0",
            "latestActivityAt": "t-3",
            "pendingConnectorApproval": "smtp.send_email:0:abc",
            "runtimePolicyBoundary": {
                "boundaries": {"read": 1, "draft": 1, "write": 0, "send": 1},
                "approvalRequiredFor": ["send"],
                "hasHumanBoundary": True,
            },
            "runtimeState": {
                "matchedSkillId": "skill-1",
                "matchedSkillName": "Draft claim reply",
                "matchedTrajectoryId": "traj-1",
            },
        },
        action_history=[
            {"action": "browser.navigate", "emittedAt": "t-1", "traceId": "trace-browser"},
            {"action": "smtp.send_email", "emittedAt": "t-2", "approvalKey": "approval-send", "traceId": "trace-send"},
        ],
        artifact_count=1,
        pending_approval_count=1,
    )

    assert audit["sessionId"] == "session-1"
    assert audit["uniform"] is True
    assert audit["approvalRequiredFor"] == ["send"]
    assert audit["hasHumanBoundary"] is True
    assert audit["artifactCount"] == 1
    assert audit["pendingApprovalCount"] == 1
    assert [event["event"] for event in audit["events"]] == [
        "session.started",
        "browser.action",
        "tool.action",
        "approval.boundary",
        "skill.matched",
        "approval.pending",
        "artifact.created",
    ]
    assert audit["events"][2]["boundary"] == "send"
    assert audit["events"][3]["traceId"] == "approval-send"
    assert audit["events"][4]["skillId"] == "skill-1"


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
