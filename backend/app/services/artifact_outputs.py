from __future__ import annotations

from typing import Any


KNOWLEDGE_READY_TYPES = {"markdown", "text", "html", "pdf", "csv", "json"}


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


def _approval_state(doc: dict[str, Any], metadata: dict[str, Any]) -> str:
    state = str(metadata.get("approvalState") or metadata.get("approvalStatus") or doc.get("approvalState") or "").strip().lower()
    if state:
        return state
    if metadata.get("requiresReview") or metadata.get("approvalId") or metadata.get("approvalKey"):
        return "pending"
    return "not_required"


def summarize_artifact_outputs(artifacts: list[dict[str, Any]], *, sample_limit: int = 8, gap_limit: int = 10) -> dict[str, Any]:
    runtime_linked = 0
    capability_linked = 0
    work_linked = 0
    knowledge_ready = 0
    review_required = 0
    output_kinds: list[str] = []
    approval_states: list[str] = []
    source_tools: list[str] = []
    samples: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []

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
        requires_review = bool(metadata.get("requiresReview") or approval_state in {"pending", "required", "review"})

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

        title = str(doc.get("title") or doc.get("name") or doc.get("artifactId") or "Artifact").strip()
        if not session_id:
            gaps.append({"key": "runtime_link", "label": f"{title} is not linked to a Runtime Lab session.", "target": "runtime"})
        if not (skill_id or trajectory_id or tool_id or work_item_id):
            gaps.append({"key": "capability_link", "label": f"{title} is not linked to a skill, trajectory, tool or work item.", "target": "capabilities"})
        if requires_review and approval_state not in {"approved", "rejected"}:
            gaps.append({"key": "artifact_review", "label": f"{title} is waiting for human review before use.", "target": "approvals"})

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
        "reviewRequired": review_required,
        "outputKinds": _count_by(output_kinds),
        "approvalStates": _count_by(approval_states),
        "sourceTools": _count_by(source_tools),
        "sample": samples,
        "gaps": gaps[:gap_limit],
    }
