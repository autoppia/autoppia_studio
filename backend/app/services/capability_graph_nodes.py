from __future__ import annotations

from typing import Any


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def graph_node(kind: str, node_id: str, label: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{kind}:{node_id}",
        "kind": kind,
        "refId": node_id,
        "label": label or node_id,
        "payload": payload,
    }


def graph_edge(source: str, target: str, relation: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": f"{source}->{relation}->{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "evidence": evidence or {},
    }


def add_node(nodes: dict[str, dict[str, Any]], kind: str, node_id: str, label: str, payload: dict[str, Any]) -> str:
    if not node_id:
        return ""
    node = graph_node(kind, node_id, label, payload)
    nodes.setdefault(node["id"], node)
    return node["id"]


def add_edge(edges: dict[str, dict[str, Any]], source: str, target: str, relation: str, evidence: dict[str, Any] | None = None) -> None:
    if not source or not target:
        return
    edge = graph_edge(source, target, relation, evidence)
    edges.setdefault(edge["id"], edge)


def entity_names(entity_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entity in entity_docs:
        name = str(entity.get("name") or "").strip()
        if name:
            result[name.lower()] = entity
        metadata = entity.get("metadata") if isinstance(entity.get("metadata"), dict) else {}
        aliases = metadata.get("aliases") or metadata.get("businessAliases") or []
        for alias in aliases if isinstance(aliases, list) else []:
            clean = str(alias or "").strip()
            if clean:
                result[clean.lower()] = entity
    return result


def tool_lookup(tool_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tool in tool_docs:
        for key in (tool.get("toolId"), tool.get("name")):
            clean = str(key or "").strip()
            if clean:
                result[clean] = tool
    return result


def metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata")
    return value if isinstance(value, dict) else {}


def runtime_state(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("runtimeState")
    return value if isinstance(value, dict) else {}


def runtime_ref(doc: dict[str, Any], key: str) -> str:
    doc_metadata = metadata(doc)
    state = runtime_state(doc)
    capability_match = state.get("capabilityMatch") if isinstance(state.get("capabilityMatch"), dict) else {}
    capability_match_snake = state.get("capability_match") if isinstance(state.get("capability_match"), dict) else {}
    selected_skill = doc.get("selectedSkill") if isinstance(doc.get("selectedSkill"), dict) else {}
    runtime_evidence = doc.get("runtimeEvidence") if isinstance(doc.get("runtimeEvidence"), dict) else {}
    capability_refs = runtime_evidence.get("capabilityRefs") if isinstance(runtime_evidence.get("capabilityRefs"), dict) else {}
    value = (
        doc.get(key)
        or doc_metadata.get(key)
        or state.get(key)
        or capability_match.get(key)
        or capability_match_snake.get(key)
        or selected_skill.get(key)
        or capability_refs.get(key)
    )
    if not value and key == "matchedSkillId":
        value = selected_skill.get("skillId") or capability_refs.get("skillId")
    return str(value or "").strip()


def runtime_ref_list(doc: dict[str, Any], key: str) -> list[str]:
    doc_metadata = metadata(doc)
    state = runtime_state(doc)
    values: list[Any] = []
    for container in (doc, doc_metadata, state):
        raw = container.get(key) if isinstance(container, dict) else None
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    for container_key in ("operational", "runtimeMetrics", "runtimeEvidence"):
        container = state.get(container_key) if isinstance(state.get(container_key), dict) else doc.get(container_key)
        raw = container.get(key) if isinstance(container, dict) else None
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    if key == "toolIds":
        values.extend(runtime_ref_list(doc, "latestToolIds"))
    return dedupe_strings([str(value or "") for value in values])


def session_runtime_payload(session: dict[str, Any]) -> dict[str, Any]:
    state = runtime_state(session)
    return {
        "sessionId": session.get("sessionId", ""),
        "agentId": session.get("agentId", ""),
        "agentName": session.get("agentName", ""),
        "prompt": session.get("prompt", ""),
        "provider": session.get("provider", ""),
        "runtimeKind": session.get("runtimeKind") or state.get("runtimeKind") or state.get("runtimeType") or "",
        "matchedSkillId": runtime_ref(session, "matchedSkillId"),
        "matchedSkillName": session.get("matchedSkillName") or state.get("matchedSkillName") or "",
        "approvalState": session.get("approvalState") or state.get("approvalState") or "",
        "artifactCount": session.get("artifactCount") or state.get("artifactCount") or 0,
        "pendingApprovalCount": session.get("pendingApprovalCount") or state.get("pendingApprovalCount") or 0,
        "traceIds": session.get("traceIds") or state.get("traceIds") or [],
        "createdAt": session.get("createdAt"),
        "updatedAt": session.get("updatedAt"),
    }


def approval_runtime_payload(approval: dict[str, Any]) -> dict[str, Any]:
    doc_metadata = metadata(approval)
    return {
        "approvalId": approval.get("approvalId", ""),
        "sessionId": approval.get("sessionId", ""),
        "agentId": approval.get("agentId", ""),
        "status": approval.get("status", ""),
        "approvalKey": approval.get("approvalKey", ""),
        "toolName": approval.get("toolName", ""),
        "title": approval.get("title", ""),
        "skillId": doc_metadata.get("skillId", ""),
        "trajectoryId": doc_metadata.get("trajectoryId", ""),
        "toolId": doc_metadata.get("toolId", ""),
        "createdAt": approval.get("createdAt"),
        "updatedAt": approval.get("updatedAt"),
    }


def artifact_runtime_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    doc_metadata = metadata(artifact)
    return {
        "artifactId": artifact.get("artifactId", ""),
        "sessionId": artifact.get("sessionId", ""),
        "artifactType": artifact.get("artifactType") or artifact.get("kind") or "",
        "title": artifact.get("title") or artifact.get("name") or "",
        "sourceTool": artifact.get("sourceTool", ""),
        "skillId": doc_metadata.get("skillId", ""),
        "trajectoryId": doc_metadata.get("trajectoryId", ""),
        "toolId": doc_metadata.get("toolId", ""),
        "createdAt": artifact.get("createdAt"),
        "updatedAt": artifact.get("updatedAt"),
    }


def work_operational(doc: dict[str, Any]) -> dict[str, Any]:
    operational = doc.get("operational")
    return operational if isinstance(operational, dict) else {}


def work_ref_list(doc: dict[str, Any], key: str) -> list[str]:
    raw = work_operational(doc).get(key)
    values = raw if isinstance(raw, list) else []
    return dedupe_strings([str(value or "") for value in values])


def work_item_payload(work_item: dict[str, Any]) -> dict[str, Any]:
    operational = work_operational(work_item)
    orchestration = operational.get("orchestration") if isinstance(operational.get("orchestration"), dict) else {}
    return {
        "workItemId": work_item.get("workItemId", ""),
        "title": work_item.get("title", ""),
        "prompt": work_item.get("prompt", ""),
        "status": work_item.get("status", "TODO"),
        "agentId": work_item.get("agentId", ""),
        "agentName": work_item.get("agentName", ""),
        "runTarget": work_item.get("runTarget", "selected"),
        "triggerType": work_item.get("triggerType", "manual"),
        "scheduleFrequency": work_item.get("scheduleFrequency", "none"),
        "nextRunAt": work_item.get("nextRunAt", ""),
        "maxCreditsPerRun": work_item.get("maxCreditsPerRun", 0),
        "maxBudgetCredits": work_item.get("maxBudgetCredits", 0),
        "maxSteps": work_item.get("maxSteps", 0),
        "sourceTaskId": work_item.get("sourceTaskId", ""),
        "sourceBenchmarkId": work_item.get("sourceBenchmarkId", ""),
        "currentSessionId": work_item.get("currentSessionId", ""),
        "lastRunId": work_item.get("lastRunId", ""),
        "reviewBlocked": bool(operational.get("reviewBlocked") or str(work_item.get("status") or "") == "REVIEW"),
        "pendingApprovalCount": operational.get("pendingApprovalCount", 0),
        "latestArtifactCount": operational.get("latestArtifactCount", 0),
        "persistedArtifactCount": operational.get("persistedArtifactCount", 0),
        "latestCreditsSpent": operational.get("latestCreditsSpent", 0),
        "orchestration": orchestration,
        "createdAt": work_item.get("createdAt"),
        "updatedAt": work_item.get("updatedAt"),
    }


def vector_store_payload(vector_store: dict[str, Any]) -> dict[str, Any]:
    return {
        "vectorDatabaseId": vector_store.get("vectorDatabaseId", ""),
        "name": vector_store.get("name", ""),
        "provider": vector_store.get("provider", "local"),
        "collectionName": vector_store.get("collectionName", ""),
        "status": vector_store.get("status", "ready"),
        "connectorId": vector_store.get("connectorId", ""),
        "createdAt": vector_store.get("createdAt"),
        "updatedAt": vector_store.get("updatedAt"),
    }


def eval_run_label(run: dict[str, Any]) -> str:
    return str(run.get("label") or "pending").strip().lower() or "pending"


def eval_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": run.get("runId", ""),
        "benchmarkRunId": run.get("benchmarkRunId", ""),
        "evalId": run.get("evalId", ""),
        "benchmarkId": run.get("benchmarkId", ""),
        "benchmarkName": run.get("benchmarkName", ""),
        "agentId": run.get("agentId", ""),
        "agentName": run.get("agentName", ""),
        "sessionId": run.get("sessionId", ""),
        "label": eval_run_label(run),
        "judgeType": run.get("judgeType", ""),
        "labelSource": run.get("labelSource", ""),
        "createdAt": run.get("createdAt"),
        "updatedAt": run.get("updatedAt"),
    }


def capability_boundary(doc: dict[str, Any]) -> str:
    explicit = str(doc.get("policyBoundary") or (doc.get("toolContract") if isinstance(doc.get("toolContract"), dict) else {}).get("policyBoundary") or "").strip().lower()
    if explicit in {"read", "draft", "write", "send"}:
        return explicit
    side_effects = str(doc.get("sideEffects") or "").strip().lower()
    if side_effects in {"sends", "send"}:
        return "send"
    if side_effects in {"writes", "write", "deletes", "delete", "mutates", "payments"}:
        return "write"
    if side_effects in {"drafts", "draft"}:
        return "draft"
    return "read"


def policy_boundary_payload(boundary: str) -> dict[str, Any]:
    labels = {
        "read": "Read-only boundary",
        "draft": "Draft artifact boundary",
        "write": "Write side-effect boundary",
        "send": "External send boundary",
    }
    return {
        "boundary": boundary,
        "label": labels.get(boundary, boundary),
        "requiresApprovalByDefault": boundary in {"write", "send"},
        "ordered": boundary in {"read", "draft", "write", "send"},
    }


def approval_mode_payload(mode: str) -> dict[str, Any]:
    clean = mode if mode in {"always", "auto", "never"} else "auto"
    return {
        "approvalMode": clean,
        "label": f"Approval {clean}",
        "humanRequired": clean in {"always", "auto"},
    }


def browser_policy_id(policy: dict[str, Any]) -> str:
    if not policy.get("browserRuntime"):
        return "none"
    browser = policy.get("browserPolicy") if isinstance(policy.get("browserPolicy"), dict) else {}
    if browser.get("restrictedByDomain"):
        return "domain_restricted"
    if browser.get("requiresSandbox"):
        return "sandbox_required"
    return "browser_allowed"


def browser_policy_payload(policy: dict[str, Any]) -> dict[str, Any]:
    browser = policy.get("browserPolicy") if isinstance(policy.get("browserPolicy"), dict) else {}
    policy_id = browser_policy_id(policy)
    return {
        "browserPolicy": policy_id,
        "browserRuntime": bool(policy.get("browserRuntime")),
        "defaultUse": browser.get("defaultUse") or "none",
        "restrictedByDomain": bool(browser.get("restrictedByDomain")),
        "allowedDomains": browser.get("allowedDomains") if isinstance(browser.get("allowedDomains"), list) else [],
        "requiresSandbox": bool(browser.get("requiresSandbox")),
        "leastPrivilege": bool(browser.get("leastPrivilege", True)),
    }
