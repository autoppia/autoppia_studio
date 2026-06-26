from __future__ import annotations

from typing import Any


KNOWLEDGE_READY_TYPES = {"markdown", "text", "html", "pdf", "csv", "json"}

ARTIFACT_HARDENING_ACTIONS = {
    "runtime_link": {
        "area": "runtime",
        "severity": "high",
        "action": "Link the artifact to the originating Runtime Lab session and trace.",
    },
    "capability_link": {
        "area": "capabilities",
        "severity": "medium",
        "action": "Link the artifact to a skill, trajectory, tool or work item.",
    },
    "artifact_review": {
        "area": "approvals",
        "severity": "high",
        "action": "Complete human review before reusing or delivering this business output.",
    },
    "knowledge_reuse": {
        "area": "resources",
        "severity": "medium",
        "action": "Resolve review/runtime/type blockers before saving this artifact as reusable knowledge.",
    },
    "delivery_review": {
        "area": "approvals",
        "severity": "high",
        "action": "Resolve artifact review or approval before delivering the business output.",
    },
}


def _clean_type(value: Any) -> str:
    clean = str(value or "markdown").strip().lower()
    return clean or "markdown"


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _count_by(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _hardening_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = ARTIFACT_HARDENING_ACTIONS.get(
            gap,
            {
                "area": "artifacts",
                "severity": "medium",
                "action": "Review this artifact output before production reuse.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


def _approval_state(doc: dict[str, Any], metadata: dict[str, Any]) -> str:
    state = str(metadata.get("approvalState") or metadata.get("approvalStatus") or doc.get("approvalState") or "").strip().lower()
    if state:
        return state
    if metadata.get("requiresReview") or metadata.get("approvalId") or metadata.get("approvalKey"):
        return "pending"
    return "not_required"


def artifact_capability_refs(metadata: dict[str, Any]) -> dict[str, Any]:
    refs = {
        "skillId": str(metadata.get("skillId") or ""),
        "trajectoryId": str(metadata.get("trajectoryId") or ""),
        "toolId": str(metadata.get("toolId") or ""),
        "workItemId": str(metadata.get("workItemId") or ""),
    }
    refs["linked"] = any(refs[key] for key in ("skillId", "trajectoryId", "toolId", "workItemId"))
    return refs


def artifact_approval_relation(metadata: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(metadata.get("approvalId") or "")
    approval_key = str(metadata.get("approvalKey") or "")
    approval_state = str(metadata.get("approvalState") or metadata.get("approvalStatus") or "")
    boundary = str(metadata.get("approvalBoundary") or metadata.get("policyBoundary") or "")
    resolved = approval_state in {"approved", "rejected"}
    requires_review = not resolved and bool(metadata.get("requiresReview") or approval_id or approval_key or approval_state in {"pending", "required"})
    return {
        "linked": bool(approval_id or approval_key or requires_review),
        "approvalId": approval_id,
        "approvalKey": approval_key,
        "state": approval_state or ("pending" if requires_review else "not_required"),
        "boundary": boundary,
        "requiresReview": requires_review,
    }


def artifact_output_contract(
    doc: dict[str, Any],
    *,
    artifact_type: str,
    capability_refs: dict[str, Any],
    approval_relation: dict[str, Any],
) -> dict[str, Any]:
    session_id = str(doc.get("sessionId", ""))
    source_tool = str(doc.get("sourceTool", ""))
    knowledge_ready = artifact_type in KNOWLEDGE_READY_TYPES
    reuse_ready = knowledge_ready and not approval_relation["requiresReview"] and bool(session_id)
    reuse_blockers = [
        blocker
        for blocker in [
            "not_knowledge_ready" if not knowledge_ready else "",
            "requires_review" if approval_relation["requiresReview"] else "",
            "missing_runtime_session" if not session_id else "",
        ]
        if blocker
    ]
    return {
        "artifactId": doc.get("artifactId", ""),
        "outputKind": artifact_type,
        "businessOutput": True,
        "separatedFromTrace": True,
        "runtimeLinked": bool(session_id),
        "capabilityLinked": bool(capability_refs.get("linked")),
        "workLinked": bool(capability_refs.get("workItemId")),
        "source": {
            "sessionId": session_id,
            "sourceTool": source_tool,
            "skillId": capability_refs["skillId"],
            "trajectoryId": capability_refs["trajectoryId"],
            "toolId": capability_refs["toolId"],
            "workItemId": capability_refs["workItemId"],
        },
        "governance": {
            "approvalState": approval_relation["state"],
            "requiresReview": approval_relation["requiresReview"],
            "approvalRelation": approval_relation,
            "deliveryReady": bool(session_id) and bool(capability_refs.get("linked")) and not approval_relation["requiresReview"],
            "knowledgeReady": knowledge_ready,
            "reuseReadiness": {
                "ready": reuse_ready,
                "blockers": reuse_blockers,
            },
        },
        "nextActions": [
            action
            for action in [
                "Open the originating Runtime Lab session." if session_id else "",
                "Review linked capability evidence." if capability_refs.get("linked") else "",
                "Save to Resources if this output should become reusable knowledge." if reuse_ready else "",
            ]
            if action
        ],
    }


def summarize_artifact_outputs(artifacts: list[dict[str, Any]], *, sample_limit: int = 8, gap_limit: int = 10) -> dict[str, Any]:
    runtime_linked = 0
    capability_linked = 0
    work_linked = 0
    knowledge_ready = 0
    reusable_as_knowledge = 0
    review_required = 0
    delivery_ready = 0
    delivery_blocked = 0
    output_kinds: list[str] = []
    approval_states: list[str] = []
    source_tools: list[str] = []
    samples: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    gap_counts: dict[str, int] = {}

    for doc in artifacts:
        metadata = _metadata(doc)
        artifact_type = _clean_type(doc.get("artifactType") or doc.get("kind") or doc.get("contentType"))
        session_id = str(doc.get("sessionId") or metadata.get("sessionId") or "").strip()
        skill_id = str(metadata.get("skillId") or doc.get("skillId") or "").strip()
        trajectory_id = str(metadata.get("trajectoryId") or doc.get("trajectoryId") or "").strip()
        tool_id = str(metadata.get("toolId") or doc.get("toolId") or "").strip()
        work_item_id = str(metadata.get("workItemId") or doc.get("workItemId") or "").strip()
        source_tool = str(doc.get("sourceTool") or metadata.get("sourceTool") or "").strip()
        approval_state = _approval_state(doc, metadata)
        review_resolved = approval_state in {"approved", "rejected"}
        requires_review = bool(
            not review_resolved
            and (metadata.get("requiresReview") or approval_state in {"pending", "required", "review"})
        )

        output_kinds.append(artifact_type)
        approval_states.append(approval_state)
        if source_tool:
            source_tools.append(source_tool)
        if session_id:
            runtime_linked += 1
        if skill_id or trajectory_id or tool_id or work_item_id:
            capability_linked += 1
        if work_item_id:
            work_linked += 1
        if artifact_type in KNOWLEDGE_READY_TYPES:
            knowledge_ready += 1
        if requires_review:
            review_required += 1
        artifact_delivery_ready = bool(session_id) and bool(skill_id or trajectory_id or tool_id or work_item_id) and not requires_review
        if artifact_delivery_ready:
            delivery_ready += 1
        else:
            delivery_blocked += 1
        if artifact_type in KNOWLEDGE_READY_TYPES and session_id and not requires_review:
            reusable_as_knowledge += 1

        title = str(doc.get("title") or doc.get("name") or doc.get("artifactId") or "Artifact").strip()
        if not session_id:
            gaps.append({"key": "runtime_link", "label": f"{title} is not linked to a Runtime Lab session.", "target": "runtime"})
            gap_counts["runtime_link"] = gap_counts.get("runtime_link", 0) + 1
        if not (skill_id or trajectory_id or tool_id or work_item_id):
            gaps.append({"key": "capability_link", "label": f"{title} is not linked to a skill, trajectory, tool or work item.", "target": "capabilities"})
            gap_counts["capability_link"] = gap_counts.get("capability_link", 0) + 1
        if requires_review and approval_state not in {"approved", "rejected"}:
            gaps.append({"key": "artifact_review", "label": f"{title} is waiting for human review before use.", "target": "approvals"})
            gap_counts["artifact_review"] = gap_counts.get("artifact_review", 0) + 1
            gap_counts["delivery_review"] = gap_counts.get("delivery_review", 0) + 1
        if artifact_type in KNOWLEDGE_READY_TYPES and not (session_id and not requires_review):
            gap_counts["knowledge_reuse"] = gap_counts.get("knowledge_reuse", 0) + 1

        if len(samples) < sample_limit:
            samples.append(
                {
                    "artifactId": str(doc.get("artifactId") or ""),
                    "title": title,
                    "outputKind": artifact_type,
                    "runtimeLinked": bool(session_id),
                    "capabilityLinked": bool(skill_id or trajectory_id or tool_id or work_item_id),
                    "workLinked": bool(work_item_id),
                    "knowledgeReady": artifact_type in KNOWLEDGE_READY_TYPES,
                    "reusableAsKnowledge": artifact_type in KNOWLEDGE_READY_TYPES and bool(session_id) and not requires_review,
                    "deliveryReady": artifact_delivery_ready,
                    "approvalState": approval_state,
                    "requiresReview": requires_review,
                    "source": {
                        "sessionId": session_id,
                        "skillId": skill_id,
                        "trajectoryId": trajectory_id,
                        "toolId": tool_id,
                        "workItemId": work_item_id,
                        "sourceTool": source_tool,
                    },
                }
            )

    total = len(artifacts)
    return {
        "total": total,
        "businessOutputs": total,
        "separatedFromTrace": total,
        "runtimeLinked": runtime_linked,
        "capabilityLinked": capability_linked,
        "workLinked": work_linked,
        "knowledgeReady": knowledge_ready,
        "reusableAsKnowledge": reusable_as_knowledge,
        "blockedForReuse": max(0, knowledge_ready - reusable_as_knowledge),
        "reviewRequired": review_required,
        "deliveryReady": delivery_ready,
        "deliveryBlocked": delivery_blocked,
        "businessOutputDeliveryGate": {
            "state": "ready" if total and delivery_blocked == 0 else ("no_artifacts" if not total else "blocked"),
            "ready": bool(total) and delivery_blocked == 0,
            "total": total,
            "readyOutputs": delivery_ready,
            "blockedOutputs": delivery_blocked,
            "checks": {
                "businessOutputsPresent": total > 0,
                "runtimeLinked": total > 0 and runtime_linked == total,
                "capabilityLinked": total > 0 and capability_linked == total,
                "reviewsResolved": total > 0 and review_required == 0,
            },
            "blockers": [
                blocker
                for blocker, blocked in [
                    ("businessOutputsPresent", total == 0),
                    ("runtimeLinked", total > 0 and runtime_linked < total),
                    ("capabilityLinked", total > 0 and capability_linked < total),
                    ("reviewsResolved", total > 0 and review_required > 0),
                ]
                if blocked
            ],
        },
        "outputKinds": _count_by(output_kinds),
        "approvalStates": _count_by(approval_states),
        "sourceTools": _count_by(source_tools),
        "hardeningPlaybook": _hardening_playbook(gap_counts),
        "sample": samples,
        "gaps": gaps[:gap_limit],
    }
