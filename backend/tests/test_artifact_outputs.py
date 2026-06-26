from app.services.artifact_outputs import artifact_approval_relation
from app.services.artifact_outputs import artifact_capability_refs
from app.services.artifact_outputs import artifact_output_contract
from app.services.artifact_outputs import summarize_artifact_outputs


def test_artifact_capability_refs_and_approval_relation_are_shared_contracts():
    metadata = {
        "skillId": "skill-1",
        "trajectoryId": "trajectory-1",
        "toolId": "tool-1",
        "workItemId": "work-1",
        "approvalId": "approval-1",
        "approvalKey": "smtp.send_email:0:abc",
        "approvalState": "pending",
        "approvalBoundary": "send",
    }

    refs = artifact_capability_refs(metadata)
    approval = artifact_approval_relation(metadata)

    assert refs == {
        "skillId": "skill-1",
        "trajectoryId": "trajectory-1",
        "toolId": "tool-1",
        "workItemId": "work-1",
        "linked": True,
    }
    assert approval == {
        "linked": True,
        "approvalId": "approval-1",
        "approvalKey": "smtp.send_email:0:abc",
        "state": "pending",
        "boundary": "send",
        "requiresReview": True,
    }


def test_artifact_output_contract_keeps_business_output_separate_from_trace():
    refs = artifact_capability_refs({"skillId": "skill-1", "workItemId": "work-1"})
    approval = artifact_approval_relation({"requiresReview": True, "policyBoundary": "draft"})
    contract = artifact_output_contract(
        {"artifactId": "artifact-1", "sessionId": "session-1", "sourceTool": "smtp.draft_email"},
        artifact_type="markdown",
        capability_refs=refs,
        approval_relation=approval,
    )

    assert contract["businessOutput"] is True
    assert contract["separatedFromTrace"] is True
    assert contract["runtimeLinked"] is True
    assert contract["capabilityLinked"] is True
    assert contract["workLinked"] is True
    assert contract["source"]["sourceTool"] == "smtp.draft_email"
    assert contract["governance"]["knowledgeReady"] is True
    assert contract["governance"]["reuseReadiness"] == {"ready": False, "blockers": ["requires_review"]}
    assert contract["governance"]["approvalRelation"]["requiresReview"] is True
    assert contract["nextActions"] == [
        "Open the originating Runtime Lab session.",
        "Review linked capability evidence.",
    ]


def test_summarize_artifact_outputs_counts_reuse_ready_business_outputs():
    summary = summarize_artifact_outputs(
        [
            {
                "artifactId": "artifact-ready",
                "title": "Ready summary",
                "artifactType": "markdown",
                "sessionId": "session-1",
                "metadata": {"skillId": "skill-1"},
                "sourceTool": "smtp.draft_email",
            },
            {
                "artifactId": "artifact-review",
                "title": "Pending draft",
                "artifactType": "markdown",
                "sessionId": "session-2",
                "metadata": {"requiresReview": True, "approvalState": "pending"},
            },
            {
                "artifactId": "artifact-binary",
                "title": "Screenshot",
                "artifactType": "png",
                "sessionId": "session-3",
            },
        ]
    )

    assert summary["knowledgeReady"] == 2
    assert summary["reusableAsKnowledge"] == 1
    assert summary["blockedForReuse"] == 1
    assert summary["reviewRequired"] == 1
    assert summary["hardeningPlaybook"] == [
        {
            "gap": "capability_link",
            "count": 2,
            "area": "capabilities",
            "severity": "medium",
            "action": "Link the artifact to a skill, trajectory, tool or work item.",
        },
        {
            "gap": "artifact_review",
            "count": 1,
            "area": "approvals",
            "severity": "high",
            "action": "Complete human review before reusing or delivering this business output.",
        },
        {
            "gap": "knowledge_reuse",
            "count": 1,
            "area": "resources",
            "severity": "medium",
            "action": "Resolve review/runtime/type blockers before saving this artifact as reusable knowledge.",
        },
    ]
    assert summary["sample"][0]["reusableAsKnowledge"] is True
    assert summary["sample"][1]["reusableAsKnowledge"] is False
