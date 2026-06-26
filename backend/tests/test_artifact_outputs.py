from app.services.artifact_outputs import artifact_approval_relation
from app.services.artifact_outputs import artifact_capability_refs
from app.services.artifact_outputs import artifact_output_contract


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
    assert contract["governance"]["approvalRelation"]["requiresReview"] is True
    assert contract["nextActions"] == [
        "Open the originating Runtime Lab session.",
        "Review linked capability evidence.",
        "Save to Resources if this output should become reusable knowledge.",
    ]
