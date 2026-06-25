import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    approvals_collection,
    artifacts_collection,
    benchmarks_collection,
    capabilities_collection,
    benchmark_tasks_collection,
    companies_collection,
    connectors_collection,
    entities_collection,
    eval_runs_collection,
    evals_collection,
    harvester_runs_collection,
    knowledge_documents_collection,
    sessions_collection,
    tools_collection,
    trajectories_collection,
    vector_databases_collection,
    work_items_collection,
)
from app.harvesters import harvest_connector_capabilities
from app.harvesters.base import connector_surface
from app.harvesters.toolkit import ToolkitHarvester
from app.connectors import execute_connector_tool
from app.routes.connectors import connector_toolkit
from app.services.runtime_policy import serialize_runtime_policy
from app.services.skill_readiness import skill_reusability_ready
from app.services.task_contracts import task_contract_from_record, task_contract_ready

router = APIRouter()


class ToolCreateRequest(BaseModel):
    email: str
    connectorId: str
    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    outputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "additionalProperties": True})
    executionType: str = "api_call"
    sideEffects: str = "reads"
    permissions: dict[str, Any] = Field(default_factory=dict)
    riskLevel: str = "low"
    inputEntities: list[str] = Field(default_factory=list)
    outputEntity: str = ""
    outputCard: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


class CapabilityApprovalUpdateRequest(BaseModel):
    email: str = ""
    approval: str


class SkillUpdateRequest(BaseModel):
    email: str = ""
    name: str | None = None
    description: str | None = None
    whenToUse: str | None = None
    instructions: str | None = None
    preconditions: list[str] | None = None
    expectedArtifacts: list[str] | None = None
    riskPolicy: str | None = None
    status: str | None = None
    inputEntities: list[str] | None = None
    outputEntity: str | None = None
    outputCard: dict[str, Any] | None = None
    trajectoryIds: list[str] | None = None


class CompanyTrajectoryCreateRequest(BaseModel):
    email: str
    name: str
    intent: str = ""
    prompt: str = ""
    connectorIds: list[str] = Field(default_factory=list)
    toolIds: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    validations: list[dict[str, Any]] = Field(default_factory=list)
    recoverySteps: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "draft"


class PromoteTrajectoryRequest(BaseModel):
    email: str = ""
    name: str = ""
    whenToUse: str = ""
    instructions: str = ""
    preconditions: list[str] = Field(default_factory=list)
    expectedArtifacts: list[str] = Field(default_factory=list)
    permissions: dict[str, Any] = Field(default_factory=dict)
    riskPolicy: str = "human_approval_for_writes"
    inputEntities: list[str] = Field(default_factory=list)
    outputEntity: str = ""
    outputCard: dict[str, Any] = Field(default_factory=dict)


class ToolTestRequest(BaseModel):
    email: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class TrajectoryReviewRequest(BaseModel):
    email: str = ""
    label: str = "approved"
    notes: str = ""


class CompanyCapabilityPublishRequest(BaseModel):
    connectorId: str


class ConnectorBenchmarkHarvestRequest(BaseModel):
    benchmarkId: str = ""
    evalIds: list[str] = Field(default_factory=list)


class CompanyCapabilityHarvestRequest(ConnectorBenchmarkHarvestRequest):
    connectorId: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_company(company_id: str) -> dict[str, Any]:
    company = await companies_collection.find_one({"companyId": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def _connector(connector_id: str) -> dict[str, Any]:
    connector = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


def _serialize_tool(doc: dict[str, Any]) -> dict[str, Any]:
    tool_synthesis = _tool_synthesis_contract(doc)
    return {
        "capabilityId": doc.get("toolId", ""),
        "capabilityKind": "tool",
        "toolId": doc.get("toolId", ""),
        "companyId": doc.get("companyId", ""),
        "connectorId": doc.get("connectorId", ""),
        "connectorName": doc.get("connectorName", ""),
        "name": doc.get("name", ""),
        "displayName": doc.get("displayName", ""),
        "description": doc.get("description", ""),
        "inputSchema": doc.get("inputSchema", {}),
        "outputSchema": doc.get("outputSchema", {}),
        "executionType": doc.get("executionType", ""),
        "surface": doc.get("surface", ""),
        "runtimeRequirements": doc.get("runtimeRequirements", []),
        "sideEffects": doc.get("sideEffects", "reads"),
        "permissions": doc.get("permissions", {}),
        "policyBoundary": doc.get("policyBoundary", ""),
        "approvalPolicy": doc.get("approvalPolicy", {}),
        "scopes": doc.get("scopes", []),
        "toolContract": doc.get("toolContract", {}),
        "riskLevel": doc.get("riskLevel", "low"),
        "inputEntities": doc.get("inputEntities", []),
        "outputEntity": doc.get("outputEntity", ""),
        "outputCard": doc.get("outputCard", {}),
        "status": doc.get("status", "draft"),
        "source": doc.get("source", ""),
        "discovererName": doc.get("discovererName", ""),
        "discovererVersion": doc.get("discovererVersion", ""),
        "discoveryScope": doc.get("discoveryScope", ""),
        "discoveryRelevance": doc.get("discoveryRelevance", {}),
        "discoveryEvidence": doc.get("discoveryEvidence", []),
        "toolSynthesis": tool_synthesis,
        "lastTestAt": doc.get("lastTestAt"),
        "lastTestStatus": doc.get("lastTestStatus"),
        "lastTestResult": doc.get("lastTestResult"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _schema_has_properties(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    properties = schema.get("properties")
    return schema.get("type") == "object" and isinstance(properties, dict) and bool(properties)


def _permission_list(permissions: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = permissions.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    return _dedupe_strings(values)


def _tool_synthesis_contract(doc: dict[str, Any]) -> dict[str, Any]:
    input_schema = doc.get("inputSchema") if isinstance(doc.get("inputSchema"), dict) else {}
    output_schema = doc.get("outputSchema") if isinstance(doc.get("outputSchema"), dict) else {}
    permissions = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    side_effects = str(doc.get("sideEffects") or "").strip() or "reads"
    risk_level = str(doc.get("riskLevel") or "").strip() or "low"
    input_entities = [str(item).strip() for item in doc.get("inputEntities", []) if str(item).strip()] if isinstance(doc.get("inputEntities"), list) else []
    output_entity = str(doc.get("outputEntity") or "").strip()
    scopes = _permission_list(permissions, "scopes", "oauthScopes", "requiredScopes")
    approval = str(permissions.get("approval") or "").strip()
    gaps = []
    if not _schema_has_properties(input_schema):
        gaps.append("typed input schema")
    if not output_schema:
        gaps.append("output schema")
    if not side_effects:
        gaps.append("side effects")
    if not risk_level:
        gaps.append("risk classification")
    if side_effects.lower() in {"writes", "deletes", "sends"} and not approval:
        gaps.append("approval policy")
    if not scopes and not _permission_list(permissions, "readTools", "writeTools"):
        gaps.append("scopes or permissions")
    return {
        "toolId": doc.get("toolId", ""),
        "action": doc.get("name", ""),
        "atomic": True,
        "typedInput": _schema_has_properties(input_schema),
        "typedOutput": bool(output_schema),
        "sideEffects": side_effects,
        "riskLevel": risk_level,
        "riskClassification": {
            "level": risk_level,
            "requiresApproval": bool(approval == "always" or side_effects.lower() in {"writes", "deletes", "sends"} or risk_level.lower() in {"high", "critical"}),
            "approvalMode": approval or "auto",
        },
        "permissions": {
            "scopes": scopes,
            "readTools": _permission_list(permissions, "readTools"),
            "writeTools": _permission_list(permissions, "writeTools"),
            "approval": approval or "auto",
        },
        "entityBindings": {
            "inputEntities": input_entities,
            "outputEntity": output_entity,
            "declared": bool(input_entities or output_entity),
        },
        "readiness": {
            "status": "ready" if not gaps else "needs_hardening",
            "gaps": gaps,
        },
    }


def _serialize_trajectory(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "capabilityId": doc.get("trajectoryId", ""),
        "capabilityKind": "trajectory",
        "trajectoryId": doc.get("trajectoryId", ""),
        "companyId": doc.get("companyId", ""),
        "agentId": doc.get("agentId", ""),
        "connectorIds": doc.get("connectorIds", []),
        "toolIds": doc.get("toolIds", []),
        "runtimeRequirements": doc.get("runtimeRequirements", []),
        "name": doc.get("name") or doc.get("taskName", ""),
        "intent": doc.get("intent") or doc.get("prompt", ""),
        "description": doc.get("prompt", ""),
        "successCriteria": doc.get("successCriteria", ""),
        "benchmarkId": doc.get("benchmarkId", ""),
        "evalId": doc.get("evalId", ""),
        "taskId": doc.get("taskId", ""),
        "finalUrl": doc.get("finalUrl", ""),
        "judge": doc.get("judge", {}),
        "review": doc.get("review", {}),
        "harvester": doc.get("harvester", {}),
        "metadata": doc.get("metadata", {}),
        "trajectory": doc.get("trajectory", []),
        "steps": doc.get("steps") or doc.get("trajectory") or doc.get("actions", []),
        "validations": doc.get("validations", []),
        "recoverySteps": doc.get("recoverySteps", []),
        "status": doc.get("status", "draft"),
        "source": doc.get("source", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _serialize_skill(doc: dict[str, Any]) -> dict[str, Any]:
    status = str(doc.get("status", "draft") or "draft")
    version = _skill_version(doc)
    trajectory_ids = _dedupe_strings([str(value or "") for value in doc.get("trajectoryIds", [])])
    trajectory_docs: list[dict[str, Any]] = []
    latest_regression: dict[str, Any] | None = None
    regression_cases: list[dict[str, Any]] = []
    try:
        for trajectory_id in trajectory_ids:
            trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
            if trajectory:
                trajectory_docs.append(trajectory)
        latest_regression = await _latest_skill_regression(doc, trajectory_docs=trajectory_docs)
        regression_cases = await _skill_regression_cases(doc, trajectory_docs=trajectory_docs)
    except Exception:
        trajectory_docs = []
        latest_regression = None
        regression_cases = []
    lineage = _skill_lineage(doc, trajectory_docs)
    hardening = _skill_hardening_status(doc, trajectory_docs=trajectory_docs, latest_regression=latest_regression)
    runtime_policy = serialize_runtime_policy(doc)
    version_history = _skill_version_history(doc, version=version, promotion_status=_skill_promotion_status(doc))
    package = _skill_package_manifest(
        doc,
        version=version,
        promotion_status=_skill_promotion_status(doc),
        runtime_policy=runtime_policy,
        lineage=lineage,
        hardening=hardening,
        latest_regression=latest_regression,
        source_trajectories=_source_trajectory_evidence(trajectory_docs),
        regression_cases=regression_cases,
        version_history=version_history,
    )
    return {
        "capabilityId": doc.get("capabilityId", ""),
        "capabilityKind": "skill",
        "skillId": doc.get("capabilityId", ""),
        "companyId": doc.get("companyId", ""),
        "agentId": doc.get("agentId", ""),
        "connectorIds": doc.get("connectorIds", []),
        "toolIds": doc.get("toolIds", []),
        "trajectoryIds": doc.get("trajectoryIds", []),
        "runtimeRequirements": doc.get("runtimeRequirements", []),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "whenToUse": doc.get("whenToUse", ""),
        "instructions": doc.get("instructions", ""),
        "preconditions": doc.get("preconditions", []),
        "expectedArtifacts": doc.get("expectedArtifacts", []),
        "benchmarkId": doc.get("benchmarkId", ""),
        "evalId": doc.get("evalId", ""),
        "permissions": doc.get("permissions", {}),
        "riskPolicy": doc.get("riskPolicy", ""),
        "runtimePolicy": runtime_policy,
        "inputEntities": doc.get("inputEntities", []),
        "outputEntity": doc.get("outputEntity", ""),
        "outputCard": doc.get("outputCard", {}),
        "runtime": doc.get("runtime", ""),
        "status": status,
        "promotionStatus": _skill_promotion_status(doc),
        "version": version,
        "versionLabel": doc.get("versionLabel") or f"v{version}",
        "publishedAt": doc.get("publishedAt"),
        "readyAt": doc.get("readyAt"),
        "archivedAt": doc.get("archivedAt"),
        "lastPromotedAt": doc.get("lastPromotedAt"),
        "versionHistory": version_history,
        "source": doc.get("source", ""),
        "harvesterType": doc.get("harvesterType", ""),
        "harvesterRunId": doc.get("harvesterRunId", ""),
        "discovererName": doc.get("discovererName", ""),
        "discovererVersion": doc.get("discovererVersion", ""),
        "judge": doc.get("judge", {}),
        "lineage": lineage,
        "latestRegression": latest_regression,
        "hardeningStatus": hardening,
        "skillPackage": package,
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _clean_approval_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"always", "auto", "never"}:
        raise HTTPException(status_code=400, detail="approval must be one of always, auto or never")
    return mode


def _requires_harvester(connector: dict[str, Any]) -> bool:
    provider = str(connector.get("provider") or "").lower()
    surface = connector_surface(connector)
    connector_type = str(connector.get("type") or "").lower()
    ui_or_runtime_surface = surface in {"webapp", "desktop", "cli", "repo", "mixed"}
    custom_api_or_web = connector_type in {"api", "web"} and provider != "official"
    return provider == "custom" or custom_api_or_web or ui_or_runtime_surface


def _uses_default_toolkit(connector: dict[str, Any]) -> bool:
    return not _requires_harvester(connector)


async def _upsert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    upserted_tools = []
    for tool in tools:
        existing = await tools_collection.find_one({"toolId": tool["toolId"]}, {"_id": 0})
        created_at = existing.get("createdAt") if existing else tool.get("createdAt", _now())
        tool["createdAt"] = created_at
        tool["updatedAt"] = _now()
        await tools_collection.update_one({"toolId": tool["toolId"]}, {"$set": tool}, upsert=True)
        upserted_tools.append(_serialize_tool(tool))
    return upserted_tools


async def _upsert_trajectory(doc: dict[str, Any]) -> dict[str, Any]:
    existing = await trajectories_collection.find_one({"trajectoryId": doc["trajectoryId"]}, {"_id": 0})
    doc["createdAt"] = existing.get("createdAt") if existing else doc.get("createdAt", _now())
    doc["updatedAt"] = _now()
    await trajectories_collection.update_one({"trajectoryId": doc["trajectoryId"]}, {"$set": doc}, upsert=True)
    return _serialize_trajectory(doc)


async def _upsert_skill(doc: dict[str, Any]) -> dict[str, Any]:
    existing = await capabilities_collection.find_one({"capabilityId": doc["capabilityId"]}, {"_id": 0})
    now = _now()
    doc["createdAt"] = existing.get("createdAt") if existing else doc.get("createdAt", now)
    doc["version"] = _skill_version(existing or doc)
    doc["versionLabel"] = doc.get("versionLabel") or f"v{doc['version']}"
    doc["promotionStatus"] = _skill_promotion_status(doc)
    doc.update(_skill_lifecycle_fields(previous=existing or {}, next_doc=doc, now=now))
    doc["versionHistory"] = _append_skill_version_event(existing or {}, doc, now=now, reason="upserted")
    doc["updatedAt"] = now
    await capabilities_collection.update_one({"capabilityId": doc["capabilityId"]}, {"$set": doc}, upsert=True)
    return await _serialize_skill(doc)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def _graph_node(kind: str, node_id: str, label: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{kind}:{node_id}",
        "kind": kind,
        "refId": node_id,
        "label": label or node_id,
        "payload": payload,
    }


def _graph_edge(source: str, target: str, relation: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": f"{source}->{relation}->{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "evidence": evidence or {},
    }


def _add_node(nodes: dict[str, dict[str, Any]], kind: str, node_id: str, label: str, payload: dict[str, Any]) -> str:
    if not node_id:
        return ""
    node = _graph_node(kind, node_id, label, payload)
    nodes.setdefault(node["id"], node)
    return node["id"]


def _add_edge(edges: dict[str, dict[str, Any]], source: str, target: str, relation: str, evidence: dict[str, Any] | None = None) -> None:
    if not source or not target:
        return
    edge = _graph_edge(source, target, relation, evidence)
    edges.setdefault(edge["id"], edge)


def _entity_names(entity_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
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


def _tool_lookup(tool_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tool in tool_docs:
        for key in (tool.get("toolId"), tool.get("name")):
            clean = str(key or "").strip()
            if clean:
                result[clean] = tool
    return result


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _runtime_state(doc: dict[str, Any]) -> dict[str, Any]:
    runtime_state = doc.get("runtimeState")
    return runtime_state if isinstance(runtime_state, dict) else {}


def _runtime_ref(doc: dict[str, Any], key: str) -> str:
    metadata = _metadata(doc)
    runtime_state = _runtime_state(doc)
    capability_match = runtime_state.get("capabilityMatch") if isinstance(runtime_state.get("capabilityMatch"), dict) else {}
    capability_match_snake = runtime_state.get("capability_match") if isinstance(runtime_state.get("capability_match"), dict) else {}
    selected_skill = doc.get("selectedSkill") if isinstance(doc.get("selectedSkill"), dict) else {}
    runtime_evidence = doc.get("runtimeEvidence") if isinstance(doc.get("runtimeEvidence"), dict) else {}
    capability_refs = runtime_evidence.get("capabilityRefs") if isinstance(runtime_evidence.get("capabilityRefs"), dict) else {}
    value = (
        doc.get(key)
        or metadata.get(key)
        or runtime_state.get(key)
        or capability_match.get(key)
        or capability_match_snake.get(key)
        or selected_skill.get(key)
        or capability_refs.get(key)
    )
    if not value and key == "matchedSkillId":
        value = selected_skill.get("skillId") or capability_refs.get("skillId")
    return str(value or "").strip()


def _runtime_ref_list(doc: dict[str, Any], key: str) -> list[str]:
    metadata = _metadata(doc)
    runtime_state = _runtime_state(doc)
    values: list[Any] = []
    for container in (doc, metadata, runtime_state):
        raw = container.get(key) if isinstance(container, dict) else None
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    for container_key in ("operational", "runtimeMetrics", "runtimeEvidence"):
        container = runtime_state.get(container_key) if isinstance(runtime_state.get(container_key), dict) else doc.get(container_key)
        raw = container.get(key) if isinstance(container, dict) else None
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    if key == "toolIds":
        values.extend(_runtime_ref_list(doc, "latestToolIds"))
    return _dedupe_strings([str(value or "") for value in values])


def _session_runtime_payload(session: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _runtime_state(session)
    return {
        "sessionId": session.get("sessionId", ""),
        "agentId": session.get("agentId", ""),
        "agentName": session.get("agentName", ""),
        "prompt": session.get("prompt", ""),
        "provider": session.get("provider", ""),
        "runtimeKind": session.get("runtimeKind") or runtime_state.get("runtimeKind") or runtime_state.get("runtimeType") or "",
        "matchedSkillId": _runtime_ref(session, "matchedSkillId"),
        "matchedSkillName": session.get("matchedSkillName") or runtime_state.get("matchedSkillName") or "",
        "approvalState": session.get("approvalState") or runtime_state.get("approvalState") or "",
        "artifactCount": session.get("artifactCount") or runtime_state.get("artifactCount") or 0,
        "pendingApprovalCount": session.get("pendingApprovalCount") or runtime_state.get("pendingApprovalCount") or 0,
        "traceIds": session.get("traceIds") or runtime_state.get("traceIds") or [],
        "createdAt": session.get("createdAt"),
        "updatedAt": session.get("updatedAt"),
    }


def _approval_runtime_payload(approval: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(approval)
    return {
        "approvalId": approval.get("approvalId", ""),
        "sessionId": approval.get("sessionId", ""),
        "agentId": approval.get("agentId", ""),
        "status": approval.get("status", ""),
        "approvalKey": approval.get("approvalKey", ""),
        "toolName": approval.get("toolName", ""),
        "title": approval.get("title", ""),
        "skillId": metadata.get("skillId", ""),
        "trajectoryId": metadata.get("trajectoryId", ""),
        "toolId": metadata.get("toolId", ""),
        "createdAt": approval.get("createdAt"),
        "updatedAt": approval.get("updatedAt"),
    }


def _artifact_runtime_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(artifact)
    return {
        "artifactId": artifact.get("artifactId", ""),
        "sessionId": artifact.get("sessionId", ""),
        "artifactType": artifact.get("artifactType") or artifact.get("kind") or "",
        "title": artifact.get("title") or artifact.get("name") or "",
        "sourceTool": artifact.get("sourceTool", ""),
        "skillId": metadata.get("skillId", ""),
        "trajectoryId": metadata.get("trajectoryId", ""),
        "toolId": metadata.get("toolId", ""),
        "createdAt": artifact.get("createdAt"),
        "updatedAt": artifact.get("updatedAt"),
    }


def _work_operational(doc: dict[str, Any]) -> dict[str, Any]:
    operational = doc.get("operational")
    return operational if isinstance(operational, dict) else {}


def _work_ref_list(doc: dict[str, Any], key: str) -> list[str]:
    operational = _work_operational(doc)
    raw = operational.get(key)
    values = raw if isinstance(raw, list) else []
    return _dedupe_strings([str(value or "") for value in values])


def _work_item_payload(work_item: dict[str, Any]) -> dict[str, Any]:
    operational = _work_operational(work_item)
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


def _resource_contract(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource.get("resourceContract")
    return contract if isinstance(contract, dict) else {}


def _resource_indexing(resource: dict[str, Any]) -> dict[str, Any]:
    contract = _resource_contract(resource)
    indexing = contract.get("indexing")
    return indexing if isinstance(indexing, dict) else {}


def _resource_governance(resource: dict[str, Any]) -> dict[str, Any]:
    contract = _resource_contract(resource)
    governance = contract.get("governance")
    return governance if isinstance(governance, dict) else {}


def _resource_read_tools(resource: dict[str, Any]) -> list[str]:
    contract = _resource_contract(resource)
    raw = contract.get("readTools") or resource.get("readTools")
    return _dedupe_strings([str(value or "") for value in raw]) if isinstance(raw, list) else []


def _resource_indexed(resource: dict[str, Any]) -> bool:
    indexing = _resource_indexing(resource)
    status = str(resource.get("status") or indexing.get("status") or "").lower()
    return bool(indexing.get("indexed")) or status in {"indexed", "ready", "active", "completed"}


def _resource_citable(resource: dict[str, Any]) -> bool:
    governance = _resource_governance(resource)
    citability = governance.get("citability") if isinstance(governance.get("citability"), dict) else {}
    return bool(citability.get("citable") or _resource_indexed(resource))


def _resource_payload(resource: dict[str, Any]) -> dict[str, Any]:
    contract = _resource_contract(resource)
    indexing = _resource_indexing(resource)
    governance = _resource_governance(resource)
    citability = governance.get("citability") if isinstance(governance.get("citability"), dict) else {}
    return {
        "resourceId": resource.get("resourceId") or resource.get("documentId", ""),
        "documentId": resource.get("documentId", ""),
        "resourceKind": resource.get("resourceKind") or contract.get("resourceKind") or "document",
        "filename": resource.get("filename") or resource.get("name") or resource.get("title") or "",
        "status": resource.get("status", "uploaded"),
        "source": resource.get("source", "upload"),
        "connectorId": resource.get("connectorId") or governance.get("connectorId") or "",
        "vectorDatabaseId": resource.get("vectorDatabaseId") or indexing.get("vectorDatabaseId") or "",
        "vectorDatabaseName": resource.get("vectorDatabaseName") or indexing.get("vectorDatabaseName") or "",
        "vectorCollectionName": resource.get("vectorCollectionName") or indexing.get("vectorCollectionName") or "",
        "contentType": resource.get("contentType", ""),
        "size": resource.get("size", 0),
        "indexed": _resource_indexed(resource),
        "citable": _resource_citable(resource),
        "citationLabel": citability.get("citationLabel") or resource.get("filename") or "",
        "readTools": _resource_read_tools(resource),
        "resourceContract": contract,
        "createdAt": resource.get("createdAt"),
        "updatedAt": resource.get("updatedAt"),
    }


def _vector_store_payload(vector_store: dict[str, Any]) -> dict[str, Any]:
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


def _eval_run_label(run: dict[str, Any]) -> str:
    return str(run.get("label") or "pending").strip().lower() or "pending"


def _eval_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": run.get("runId", ""),
        "benchmarkRunId": run.get("benchmarkRunId", ""),
        "evalId": run.get("evalId", ""),
        "benchmarkId": run.get("benchmarkId", ""),
        "benchmarkName": run.get("benchmarkName", ""),
        "agentId": run.get("agentId", ""),
        "agentName": run.get("agentName", ""),
        "sessionId": run.get("sessionId", ""),
        "label": _eval_run_label(run),
        "judgeType": run.get("judgeType", ""),
        "labelSource": run.get("labelSource", ""),
        "createdAt": run.get("createdAt"),
        "updatedAt": run.get("updatedAt"),
    }


def _capability_graph_coverage(
    *,
    entity_docs: list[dict[str, Any]],
    resource_docs: list[dict[str, Any]],
    vector_store_docs: list[dict[str, Any]],
    tool_docs: list[dict[str, Any]],
    benchmark_docs: list[dict[str, Any]],
    task_docs: list[dict[str, Any]],
    trajectory_docs: list[dict[str, Any]],
    skill_docs: list[dict[str, Any]],
    eval_run_docs: list[dict[str, Any]],
    session_docs: list[dict[str, Any]],
    approval_docs: list[dict[str, Any]],
    artifact_docs: list[dict[str, Any]],
    work_item_docs: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    edge_relations = {edge.get("relation") for edge in edges}
    ready_tools = sum(1 for tool in tool_docs if str(tool.get("status") or "").lower() == "ready")
    ready_skills = sum(1 for skill in skill_docs if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in {"ready", "published", "approved"})
    reusable_skills = sum(1 for skill in skill_docs if skill_reusability_ready(skill))
    complete_tasks = sum(1 for task in task_docs if task_contract_ready(task))
    vector_store_ids = {str(store.get("vectorDatabaseId") or "") for store in vector_store_docs if str(store.get("vectorDatabaseId") or "")}
    resource_vector_ids = {
        str(resource.get("vectorDatabaseId") or _resource_indexing(resource).get("vectorDatabaseId") or "")
        for resource in resource_docs
        if str(resource.get("vectorDatabaseId") or _resource_indexing(resource).get("vectorDatabaseId") or "")
    }
    return {
        "entities": {"total": len(entity_docs), "linked": "input_entity" in edge_relations or "output_entity" in edge_relations},
        "resources": {
            "total": len(resource_docs),
            "indexed": sum(1 for resource in resource_docs if _resource_indexed(resource)),
            "citable": sum(1 for resource in resource_docs if _resource_citable(resource)),
            "withResourceContract": sum(1 for resource in resource_docs if bool(_resource_contract(resource))),
            "withReadTools": sum(1 for resource in resource_docs if bool(_resource_read_tools(resource))),
            "vectorStores": len(vector_store_docs),
            "linkedVectorStores": len(resource_vector_ids & vector_store_ids) if vector_store_ids else 0,
            "linkedToConnectors": "grounds_connector" in edge_relations,
            "linkedToTools": "read_by_tool" in edge_relations,
            "linkedToTasks": "grounds_task" in edge_relations,
            "linkedToSkills": "grounds_skill" in edge_relations,
        },
        "tools": {"total": len(tool_docs), "ready": ready_tools, "governed": sum(1 for tool in tool_docs if isinstance(tool.get("toolContract"), dict))},
        "benchmarks": {"total": len(benchmark_docs), "tasks": len(task_docs), "tasksWithContracts": complete_tasks},
        "evals": {
            "runs": len(eval_run_docs),
            "pass": sum(1 for run in eval_run_docs if _eval_run_label(run) == "pass"),
            "fail": sum(1 for run in eval_run_docs if _eval_run_label(run) == "fail"),
            "pending": sum(1 for run in eval_run_docs if _eval_run_label(run) == "pending"),
            "linkedToTasks": "evaluated_by_run" in edge_relations,
            "linkedToSkills": "gates_skill" in edge_relations,
            "linkedToRuntime": "replayed_session" in edge_relations,
        },
        "trajectories": {"total": len(trajectory_docs), "approved": sum(1 for item in trajectory_docs if str(item.get("status") or "").lower() == "approved")},
        "skills": {"total": len(skill_docs), "ready": ready_skills, "reusable": reusable_skills},
        "runtime": {
            "sessions": len(session_docs),
            "approvals": len(approval_docs),
            "pendingApprovals": sum(1 for item in approval_docs if str(item.get("status") or "").lower() == "pending"),
            "artifacts": len(artifact_docs),
            "linkedSessions": "exercised_skill" in edge_relations or "exercised_trajectory" in edge_relations or "exercised_tool" in edge_relations,
            "linkedApprovals": "requires_approval" in edge_relations,
            "linkedArtifacts": "produced_artifact" in edge_relations,
        },
        "work": {
            "total": len(work_item_docs),
            "scheduled": sum(1 for item in work_item_docs if str(item.get("triggerType") or "").lower() == "scheduled"),
            "running": sum(1 for item in work_item_docs if str(item.get("status") or "").upper() == "RUNNING"),
            "review": sum(1 for item in work_item_docs if str(item.get("status") or "").upper() == "REVIEW"),
            "blockedByApproval": sum(1 for item in work_item_docs if bool(_work_operational(item).get("reviewBlocked")) or str(item.get("status") or "").upper() == "REVIEW"),
            "linkedToTasks": "scheduled_from_task" in edge_relations,
            "linkedToRuntime": "opened_session" in edge_relations,
            "linkedToCapabilities": "orchestrates_skill" in edge_relations or "orchestrates_trajectory" in edge_relations or "orchestrates_tool" in edge_relations,
        },
        "promotionPath": {
            "hasTaskToTrajectory": "produced_trajectory" in edge_relations,
            "hasTrajectoryToSkill": "promoted_to" in edge_relations,
            "hasToolToSkill": "used_by_skill" in edge_relations,
        },
    }


def _skill_version(doc: dict[str, Any]) -> int:
    try:
        value = int(doc.get("version") or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, value)


def _skill_promotion_status(doc: dict[str, Any]) -> str:
    explicit = str(doc.get("promotionStatus") or "").strip().lower()
    if explicit in {"draft", "ready", "published", "archived"}:
        return explicit
    status = str(doc.get("status") or "draft").strip().lower()
    if status in {"draft", "ready", "published", "archived"}:
        return status
    if status in {"approved", "active", "completed"}:
        return "published"
    if status in {"needs_review", "needs_harvest"}:
        return "draft"
    return "draft"


def _skill_lifecycle_fields(*, previous: dict[str, Any], next_doc: dict[str, Any], now: str) -> dict[str, Any]:
    previous_status = _skill_promotion_status(previous)
    next_status = _skill_promotion_status(next_doc)
    update: dict[str, Any] = {"promotionStatus": next_status}
    if next_status == "ready" and not next_doc.get("readyAt"):
        update["readyAt"] = now
    if next_status == "published":
        update["publishedAt"] = next_doc.get("publishedAt") or now
        update["readyAt"] = next_doc.get("readyAt") or previous.get("readyAt") or now
    if next_status == "archived" and not next_doc.get("archivedAt"):
        update["archivedAt"] = now
    if previous_status != next_status:
        update["lastPromotedAt"] = now
    return update


def _skill_version_history(doc: dict[str, Any], *, version: int, promotion_status: str) -> list[dict[str, Any]]:
    history = doc.get("versionHistory") if isinstance(doc.get("versionHistory"), list) else []
    normalized = []
    for event in history:
        if not isinstance(event, dict):
            continue
        try:
            event_version = max(1, int(event.get("version") or 1))
        except (TypeError, ValueError):
            event_version = 1
        normalized.append(
            {
                "version": event_version,
                "versionLabel": str(event.get("versionLabel") or f"v{event_version}"),
                "promotionStatus": str(event.get("promotionStatus") or event.get("status") or "draft"),
                "reason": str(event.get("reason") or "updated"),
                "createdAt": event.get("createdAt") or event.get("updatedAt") or doc.get("updatedAt") or doc.get("createdAt"),
            }
        )
    if normalized:
        return sorted(normalized, key=lambda item: (item.get("version") or 1, str(item.get("createdAt") or "")))
    return [
        {
            "version": version,
            "versionLabel": doc.get("versionLabel") or f"v{version}",
            "promotionStatus": promotion_status,
            "reason": "initial_package",
            "createdAt": doc.get("createdAt") or doc.get("updatedAt"),
        }
    ]


def _append_skill_version_event(
    previous: dict[str, Any],
    next_doc: dict[str, Any],
    *,
    now: str,
    reason: str,
) -> list[dict[str, Any]]:
    history = [] if not previous else _skill_version_history(
        previous,
        version=_skill_version(previous),
        promotion_status=_skill_promotion_status(previous),
    )
    version = _skill_version(next_doc)
    event = {
        "version": version,
        "versionLabel": next_doc.get("versionLabel") or f"v{version}",
        "promotionStatus": _skill_promotion_status(next_doc),
        "reason": reason,
        "createdAt": now,
    }
    if not history or any(
        event.get(key) != history[-1].get(key)
        for key in ("version", "promotionStatus", "reason")
    ):
        history.append(event)
    return history[-25:]


def _skill_package_manifest(
    skill: dict[str, Any],
    *,
    version: int,
    promotion_status: str,
    runtime_policy: dict[str, Any],
    lineage: dict[str, Any],
    hardening: dict[str, Any],
    latest_regression: dict[str, Any] | None,
    source_trajectories: list[dict[str, Any]],
    regression_cases: list[dict[str, Any]],
    version_history: list[dict[str, Any]],
) -> dict[str, Any]:
    package_id = str(skill.get("capabilityId") or skill.get("skillId") or "")
    input_entities = skill.get("inputEntities", [])
    preconditions = skill.get("preconditions", [])
    output_entity = skill.get("outputEntity", "")
    expected_artifacts = skill.get("expectedArtifacts", [])
    output_card = skill.get("outputCard", {})
    io_contract = {
        "inputs": {
            "entities": input_entities,
            "preconditions": preconditions,
        },
        "outputs": {
            "entity": output_entity,
            "artifacts": expected_artifacts,
            "outputCard": output_card,
        },
        "declared": bool(input_entities or preconditions or output_entity or expected_artifacts or output_card),
    }
    return {
        "format": "autoppia.agent_skill",
        "manifestVersion": 1,
        "packageId": package_id,
        "metadata": {
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "version": version,
            "versionLabel": skill.get("versionLabel") or f"v{version}",
            "promotionStatus": promotion_status,
            "source": skill.get("source", ""),
            "createdAt": skill.get("createdAt"),
            "updatedAt": skill.get("updatedAt"),
        },
        "activation": {
            "description": skill.get("whenToUse", ""),
            "preconditions": preconditions,
        },
        "interface": {
            "inputEntities": input_entities,
            "outputEntity": output_entity,
            "expectedArtifacts": expected_artifacts,
            "outputCard": output_card,
            "ioContract": io_contract,
        },
        "ioContract": io_contract,
        "execution": {
            "instructions": skill.get("instructions", ""),
            "connectorIds": lineage.get("connectorIds", []),
            "toolIds": lineage.get("toolIds", []),
            "trajectoryIds": lineage.get("trajectoryIds", []),
            "runtimeRequirements": skill.get("runtimeRequirements", []),
            "runtime": skill.get("runtime", ""),
        },
        "policies": {
            "riskPolicy": skill.get("riskPolicy", ""),
            "permissions": skill.get("permissions", {}),
            "runtimePolicy": runtime_policy,
        },
        "evidence": {
            "lineage": lineage,
            "sourceTrajectories": source_trajectories,
            "latestRegression": latest_regression,
            "hardeningStatus": hardening,
            "versionHistory": version_history,
            "regressionSuite": {
                "benchmarkIds": lineage.get("benchmarkIds", []),
                "evalIds": lineage.get("evalIds", []),
                "cases": regression_cases,
                "publishable": bool(latest_regression and latest_regression.get("label") == "pass"),
            },
        },
        "progressiveDisclosure": {
            "summaryFields": ["metadata", "activation", "interface", "ioContract", "policies"],
            "fullFields": ["execution", "evidence"],
        },
    }


def _source_trajectory_evidence(trajectory_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for trajectory in trajectory_docs:
        actions = trajectory.get("steps") or trajectory.get("trajectory") or trajectory.get("actions") or []
        judge = trajectory.get("judge") if isinstance(trajectory.get("judge"), dict) else {}
        review = trajectory.get("review") if isinstance(trajectory.get("review"), dict) else {}
        evidence.append(
            {
                "trajectoryId": trajectory.get("trajectoryId", ""),
                "taskId": trajectory.get("taskId", ""),
                "benchmarkId": trajectory.get("benchmarkId", ""),
                "evalId": trajectory.get("evalId", ""),
                "name": trajectory.get("name") or trajectory.get("taskName", ""),
                "status": trajectory.get("status", ""),
                "judgeLabel": judge.get("label") or review.get("label") or "",
                "connectorIds": _dedupe_strings([str(value or "") for value in trajectory.get("connectorIds") or []]),
                "toolIds": _dedupe_strings([str(value or "") for value in trajectory.get("toolIds") or []]),
                "actionCount": len(actions) if isinstance(actions, list) else 0,
                "createdAt": trajectory.get("createdAt"),
                "updatedAt": trajectory.get("updatedAt"),
            }
        )
    return evidence


def _skill_lineage(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]]) -> dict[str, Any]:
    benchmark_ids = _dedupe_strings([str(skill.get("benchmarkId") or "")])
    eval_ids = _dedupe_strings([str(skill.get("evalId") or "")])
    connector_ids = _dedupe_strings([str(value or "") for value in skill.get("connectorIds") or []])
    tool_ids = _dedupe_strings([str(value or "") for value in skill.get("toolIds") or []])
    trajectory_ids = _dedupe_strings([str(value or "") for value in skill.get("trajectoryIds") or []])
    sources = _dedupe_strings([str(skill.get("source") or "")])

    for trajectory in trajectory_docs:
        benchmark_ids.extend(_dedupe_strings([str(trajectory.get("benchmarkId") or "")]))
        eval_ids.extend(_dedupe_strings([str(trajectory.get("evalId") or "")]))
        connector_ids.extend(_dedupe_strings([str(value or "") for value in trajectory.get("connectorIds") or []]))
        tool_ids.extend(_dedupe_strings([str(value or "") for value in trajectory.get("toolIds") or []]))
        sources.extend(_dedupe_strings([str(trajectory.get("source") or "")]))

    return {
        "trajectoryIds": _dedupe_strings(trajectory_ids),
        "benchmarkIds": _dedupe_strings(benchmark_ids),
        "evalIds": _dedupe_strings(eval_ids),
        "connectorIds": _dedupe_strings(connector_ids),
        "toolIds": _dedupe_strings(tool_ids),
        "sources": _dedupe_strings(sources),
    }


def _regression_case_key(case: dict[str, Any]) -> str:
    return str(case.get("taskId") or case.get("evalId") or f"{case.get('source')}:{case.get('benchmarkId')}:{case.get('name')}")


def _serialize_regression_case(doc: dict[str, Any], *, source: str) -> dict[str, Any]:
    task_contract = task_contract_from_record(doc)
    return {
        "source": source,
        "taskId": doc.get("taskId", ""),
        "evalId": doc.get("evalId", ""),
        "benchmarkId": doc.get("benchmarkId", ""),
        "name": doc.get("name") or doc.get("taskName") or doc.get("agentTaskName") or "",
        "businessIntent": task_contract.get("businessIntent") or "",
        "successCriteria": task_contract.get("successCriteria") or "",
        "riskClass": task_contract.get("riskClass") or "",
        "expectedArtifacts": task_contract.get("expectedArtifacts") or [],
        "allowedSystems": task_contract.get("allowedSystems") or [],
    }


async def _skill_regression_cases(skill: dict[str, Any], *, trajectory_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    company_id = str(skill.get("companyId") or "")
    email = str(skill.get("email") or "")
    task_ids = _dedupe_strings([str(trajectory.get("taskId") or "") for trajectory in trajectory_docs])
    benchmark_ids = _dedupe_strings(
        [
            str(skill.get("benchmarkId") or ""),
            *[str(trajectory.get("benchmarkId") or "") for trajectory in trajectory_docs],
        ]
    )
    eval_ids = _dedupe_strings(
        [
            str(skill.get("evalId") or ""),
            *[str(trajectory.get("evalId") or "") for trajectory in trajectory_docs],
        ]
    )

    cases_by_key: dict[str, dict[str, Any]] = {}

    async def collect(collection: Any, query: dict[str, Any], source: str, limit: int = 100) -> None:
        if company_id:
            query["companyId"] = company_id
        if email:
            query["email"] = email
        docs = await collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=limit)
        for doc in docs:
            case = _serialize_regression_case(doc, source=source)
            key = _regression_case_key(case)
            if key:
                cases_by_key.setdefault(key, case)

    if task_ids:
        await collect(benchmark_tasks_collection, {"taskId": {"$in": task_ids}}, "benchmark_task")
    if benchmark_ids:
        await collect(benchmark_tasks_collection, {"benchmarkId": {"$in": benchmark_ids}}, "benchmark_task")
    if eval_ids:
        await collect(evals_collection, {"evalId": {"$in": eval_ids}}, "legacy_eval")
    if benchmark_ids:
        await collect(evals_collection, {"benchmarkId": {"$in": benchmark_ids}}, "legacy_eval")

    return list(cases_by_key.values())[:100]


def _skill_hardening_status(
    skill: dict[str, Any],
    *,
    trajectory_docs: list[dict[str, Any]],
    latest_regression: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = {
        "activation": bool(str(skill.get("whenToUse") or "").strip()),
        "instructions": bool(str(skill.get("instructions") or "").strip()),
        "riskPolicy": bool(str(skill.get("riskPolicy") or "").strip()),
        "lineage": bool(skill.get("trajectoryIds") or trajectory_docs),
        "regression": latest_regression is not None,
        "publishableRegression": bool(latest_regression and latest_regression.get("label") == "pass"),
        "entities": bool((skill.get("inputEntities") or []) or str(skill.get("outputEntity") or "").strip()),
        "artifacts": bool(skill.get("expectedArtifacts") or skill.get("outputCard")),
    }
    passed = sum(1 for value in checks.values() if value)
    return {
        "checks": checks,
        "passedChecks": passed,
        "totalChecks": len(checks),
        "score": round(passed / len(checks), 3) if checks else 0.0,
        "state": "hardened" if checks["activation"] and checks["instructions"] and checks["riskPolicy"] and checks["lineage"] and checks["publishableRegression"] else "drafting",
    }


async def _skill_eval_ids(
    skill: dict[str, Any],
    trajectory_docs: list[dict[str, Any]] | None = None,
) -> list[str]:
    eval_ids = _dedupe_strings([str(skill.get("evalId") or "")])
    benchmark_id = str(skill.get("benchmarkId") or "")
    company_id = str(skill.get("companyId") or "")
    email = str(skill.get("email") or "")

    if trajectory_docs is None:
        trajectory_ids = _dedupe_strings([str(value or "") for value in (skill.get("trajectoryIds") or [])])
        trajectory_docs = []
        for trajectory_id in trajectory_ids:
            trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
            if trajectory:
                trajectory_docs.append(trajectory)

    eval_ids.extend(
        _dedupe_strings([str(trajectory.get("evalId") or "") for trajectory in trajectory_docs])
    )

    if benchmark_id:
        legacy_query: dict[str, Any] = {"benchmarkId": benchmark_id}
        task_query: dict[str, Any] = {"benchmarkId": benchmark_id}
        if company_id:
            legacy_query["companyId"] = company_id
            task_query["companyId"] = company_id
        if email:
            legacy_query["email"] = email
            task_query["email"] = email

        legacy_evals = await evals_collection.find(legacy_query, {"_id": 0, "evalId": 1}).to_list(length=500)
        benchmark_tasks = await benchmark_tasks_collection.find(task_query, {"_id": 0, "taskId": 1}).to_list(length=500)
        eval_ids.extend(_dedupe_strings([str(doc.get("evalId") or "") for doc in legacy_evals]))
        eval_ids.extend(_dedupe_strings([str(doc.get("taskId") or "") for doc in benchmark_tasks]))

    return _dedupe_strings(eval_ids)


async def _latest_skill_regression(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    eval_ids = await _skill_eval_ids(skill, trajectory_docs=trajectory_docs)
    if not eval_ids:
        return None
    runs = await eval_runs_collection.find({"evalId": {"$in": eval_ids}}, {"_id": 0}).sort("createdAt", -1).to_list(length=100)
    if not runs:
        return None
    latest = runs[0]
    return {
        "evalId": latest.get("evalId", ""),
        "runId": latest.get("runId", ""),
        "label": str(latest.get("label") or "").strip().lower(),
        "createdAt": latest.get("createdAt"),
    }


async def _skill_trajectory_docs(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if trajectory_docs is not None:
        return trajectory_docs
    docs: list[dict[str, Any]] = []
    for trajectory_id in _dedupe_strings([str(value or "") for value in (skill.get("trajectoryIds") or [])]):
        trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
        if trajectory:
            docs.append(trajectory)
    return docs


async def _assert_skill_publishable(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]] | None = None) -> None:
    trajectory_docs = await _skill_trajectory_docs(skill, trajectory_docs)
    latest = await _latest_skill_regression(skill, trajectory_docs=trajectory_docs)
    if not latest:
        raise HTTPException(
            status_code=400,
            detail="Skill cannot be published without benchmark evidence. Run the linked eval first.",
        )
    if latest.get("label") != "pass":
        raise HTTPException(
            status_code=400,
            detail=f"Skill cannot be published because the latest benchmark run is {latest.get('label') or 'pending'}.",
        )
    hardening = _skill_hardening_status(skill, trajectory_docs=trajectory_docs, latest_regression=latest)
    checks = hardening.get("checks") or {}
    io_declared = bool(
        skill.get("preconditions")
        or skill.get("expectedArtifacts")
        or skill.get("inputEntities")
        or str(skill.get("outputEntity") or "").strip()
        or skill.get("outputCard")
    )
    required = {
        "activation": bool(checks.get("activation")),
        "instructions": bool(checks.get("instructions")),
        "riskPolicy": bool(checks.get("riskPolicy")),
        "sourceTrajectory": bool(checks.get("lineage")),
        "ioContract": io_declared,
        "publishableRegression": bool(checks.get("publishableRegression")),
    }
    missing = [key for key, ready in required.items() if not ready]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill cannot be published until hardening is complete. Missing: {', '.join(missing)}.",
        )


async def _create_capability_run(
    *,
    connector: dict[str, Any],
    run_kind: str,
    harvester_type: str,
    logs: list[str],
) -> dict[str, Any]:
    now = _now()
    run = {
        "harvesterRunId": str(uuid.uuid4()),
        "runKind": run_kind,
        "email": connector.get("email", ""),
        "companyId": connector.get("companyId", ""),
        "connectorId": connector.get("connectorId", ""),
        "connectorName": connector.get("name", ""),
        "harvesterType": harvester_type,
        "surface": connector_surface(connector),
        "status": "running",
        "discoveredTools": 0,
        "generatedTrajectories": 0,
        "generatedSkills": 0,
        "logs": logs,
        "errors": [],
        "startedAt": now,
        "completedAt": "",
        "createdAt": now,
        "updatedAt": now,
    }
    await harvester_runs_collection.insert_one(dict(run))
    return run


async def _complete_capability_run(run: dict[str, Any], result: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
    completed = _now()
    update = {
        "harvesterType": result.get("harvesterType", run.get("harvesterType", "")),
        "surface": result.get("surface", run["surface"]),
        "status": "completed",
        "discoveredTools": len(tools),
        "generatedTrajectories": len(result.get("trajectories", [])),
        "generatedSkills": len(result.get("skills", [])),
        "logs": [*run["logs"], *result.get("logs", [])],
        "completedAt": completed,
        "updatedAt": completed,
    }
    await harvester_runs_collection.update_one({"harvesterRunId": run["harvesterRunId"]}, {"$set": update})
    run.update(update)
    return run


async def _benchmark_tasks(connector: dict[str, Any], body: ConnectorBenchmarkHarvestRequest) -> list[dict[str, Any]]:
    if body.evalIds:
        query: dict[str, Any] = {"evalId": {"$in": body.evalIds}}
    elif body.benchmarkId:
        query = {
            "$or": [
                {"benchmarkId": body.benchmarkId},
                {"agentId": body.benchmarkId},
            ]
        }
    else:
        raise HTTPException(status_code=400, detail="Select a benchmark or at least one task before running a harvester.")

    query["email"] = connector.get("email", "")
    cursor = evals_collection.find(query, {"_id": 0}).sort("createdAt", 1)
    tasks = await cursor.to_list(length=200)
    if not tasks:
        task_query = dict(query)
        if body.evalIds:
            task_query = {"taskId": {"$in": body.evalIds}, "email": connector.get("email", "")}
        task_cursor = benchmark_tasks_collection.find(task_query, {"_id": 0}).sort("createdAt", 1)
        raw_tasks = await task_cursor.to_list(length=200)
        tasks = [
            {
                "evalId": task.get("taskId", ""),
                "taskId": task.get("taskId", ""),
                "email": task.get("email", ""),
                "companyId": task.get("companyId", ""),
                "benchmarkId": task.get("benchmarkId", ""),
                "agentId": task.get("agentId", ""),
                "agentTaskName": task.get("taskName") or task.get("name", ""),
                "prompt": task.get("prompt", ""),
                "initialUrl": (task.get("metadata") or {}).get("startUrl", "") if isinstance(task.get("metadata"), dict) else "",
                "successCriteria": task.get("successCriteria", ""),
                "createdAt": task.get("createdAt"),
            }
            for task in raw_tasks
        ]
    if not tasks:
        raise HTTPException(status_code=404, detail="Benchmark tasks not found for this connector/company.")
    return tasks


def _task_skill_name(connector: dict[str, Any], task: dict[str, Any]) -> str:
    task_name = str(task.get("agentTaskName") or "").strip()
    if task_name:
        return task_name
    prompt = str(task.get("prompt") or "Task").strip()
    compact = " ".join(prompt.split())[:64]
    return f"{connector.get('name', 'Connector')} - {compact}"


def _skill_status_for_connector(connector: dict[str, Any]) -> str:
    return "draft" if connector_surface(connector) == "api" else "needs_harvest"


def _ensure_connector_belongs_to_company(connector: dict[str, Any], company_id: str) -> None:
    if connector.get("companyId") != company_id:
        raise HTTPException(status_code=400, detail="Connector does not belong to this company")


async def _publish_default_tools_for_connector(connector: dict[str, Any]) -> dict[str, Any]:
    if not _uses_default_toolkit(connector):
        raise HTTPException(
            status_code=400,
            detail="This connector needs benchmark-based harvesting because it is custom, private, or UI-driven.",
        )

    run = await _create_capability_run(
        connector=connector,
        run_kind="tool_publication",
        harvester_type="default_toolkit_publisher",
        logs=["Publishing known Autoppia default tools for this official connector."],
    )
    try:
        result = await ToolkitHarvester("default_toolkit_publisher", source="default_toolkit").harvest(connector)
        upserted_tools = await _upsert_tools(result.get("tools", []))
        run = await _complete_capability_run(run, result, upserted_tools)
        return {"success": True, "run": run, "tools": upserted_tools}
    except Exception as exc:
        failed = _now()
        update = {"status": "failed", "errors": [str(exc)], "completedAt": failed, "updatedAt": failed}
        await harvester_runs_collection.update_one({"harvesterRunId": run["harvesterRunId"]}, {"$set": update})
        run.update(update)
        return {"success": False, "run": run, "tools": []}


async def _harvest_capabilities_for_connector(
    connector: dict[str, Any],
    body: ConnectorBenchmarkHarvestRequest,
) -> dict[str, Any]:
    if _uses_default_toolkit(connector):
        raise HTTPException(
            status_code=400,
            detail="Official connectors already ship with default tools. Publish default tools instead of running a harvester.",
        )

    tasks = await _benchmark_tasks(connector, body)
    surface = connector_surface(connector)
    connector_type = str(connector.get("type") or "").lower()
    connector_id = str(connector.get("connectorId") or "")
    runtime_requirements = list(connector_toolkit(connector).get("runtimeRequirements") or [])
    run = await _create_capability_run(
        connector=connector,
        run_kind="benchmark_harvester",
        harvester_type="api_harvester" if surface == "api" else "webapp_harvester",
        logs=[f"Harvester run started with {len(tasks)} benchmark tasks."],
    )
    try:
        tools: list[dict[str, Any]] = []
        if connector_type == "api":
            result = await harvest_connector_capabilities(connector)
            tools = await _upsert_tools(result.get("tools", []))
            tool_ids = [tool["toolId"] for tool in tools]
            logs = result.get("logs", [])
        else:
            tool_ids = []
            logs = ["Web connector harvesting is task-first: no generic browser tools were published."]

        trajectories = []
        skills = []
        now = _now()
        benchmark_id = body.benchmarkId or str(tasks[0].get("benchmarkId") or tasks[0].get("agentId") or "")
        for task in tasks:
            eval_id = str(task.get("evalId") or uuid.uuid4())
            prompt = str(task.get("prompt") or "")
            trajectory_id = f"{connector_id}:{eval_id}:trajectory"
            capability_id = f"{connector_id}:{eval_id}:skill"
            trajectory = await _upsert_trajectory(
                {
                    "trajectoryId": trajectory_id,
                    "email": connector.get("email", ""),
                    "companyId": connector.get("companyId", ""),
                    "agentId": task.get("agentId", ""),
                    "webId": connector_id if connector_type == "web" else "",
                    "name": _task_skill_name(connector, task),
                    "intent": prompt,
                    "prompt": prompt,
                    "successCriteria": task.get("successCriteria", ""),
                    "benchmarkId": benchmark_id,
                    "evalId": eval_id,
                    "connectorIds": [connector_id],
                    "toolIds": tool_ids if connector_type == "api" else [],
                    "runtimeRequirements": runtime_requirements,
                    "steps": [],
                    "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}},
                    "validations": [{"type": "user_or_benchmark_confirmation", "criteria": task.get("successCriteria", "")}],
                    "recoverySteps": [],
                    "status": "draft" if connector_type == "api" else "needs_harvest",
                    "source": "benchmark_harvester",
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
            skill = await _upsert_skill(
                {
                    "capabilityId": capability_id,
                    "capabilityKind": "skill",
                    "email": connector.get("email", ""),
                    "companyId": connector.get("companyId", ""),
                    "agentId": task.get("agentId", ""),
                    "webId": connector_id if connector_type == "web" else "",
                    "name": _task_skill_name(connector, task),
                    "description": prompt,
                    "whenToUse": prompt,
                    "instructions": prompt,
                    "preconditions": [],
                    "expectedArtifacts": [],
                    "connectorIds": [connector_id],
                    "toolIds": tool_ids if connector_type == "api" else [],
                    "trajectoryIds": [trajectory_id],
                    "runtimeRequirements": runtime_requirements,
                    "benchmarkId": benchmark_id,
                    "evalId": eval_id,
                    "permissions": {"connectorId": connector_id, "requiresBenchmarkApproval": True},
                    "riskPolicy": "human_approval_for_writes",
                    "runtime": "api_tool_executor" if connector_type == "api" else "web_trajectory_harvester",
                    "status": _skill_status_for_connector(connector),
                    "source": "benchmark_harvester",
                    "harvesterType": run.get("harvesterType", ""),
                    "harvesterRunId": run.get("harvesterRunId", ""),
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
            trajectories.append(trajectory)
            skills.append(skill)

        completed = _now()
        update = {
            "benchmarkId": benchmark_id,
            "status": "completed",
            "discoveredTools": len(tools),
            "generatedTrajectories": len(trajectories),
            "generatedSkills": len(skills),
            "logs": [*run["logs"], *logs, f"Generated {len(skills)} task-scoped skill drafts."],
            "completedAt": completed,
            "updatedAt": completed,
        }
        await harvester_runs_collection.update_one({"harvesterRunId": run["harvesterRunId"]}, {"$set": update})
        run.update(update)
        return {"success": True, "run": run, "tools": tools, "trajectories": trajectories, "skills": skills}
    except Exception as exc:
        failed = _now()
        update = {"status": "failed", "errors": [str(exc)], "completedAt": failed, "updatedAt": failed}
        await harvester_runs_collection.update_one({"harvesterRunId": run["harvesterRunId"]}, {"$set": update})
        run.update(update)
        return {"success": False, "run": run, "tools": [], "trajectories": [], "skills": []}


@router.get("/companies/{company_id}/capabilities")
async def list_company_capabilities(company_id: str, email: str = ""):
    await _ensure_company(company_id)
    query: dict[str, Any] = {"companyId": company_id}
    if email:
        query["email"] = email

    tools = [_serialize_tool(doc) async for doc in tools_collection.find(query, {"_id": 0}).sort("createdAt", 1)]
    trajectories = [_serialize_trajectory(doc) async for doc in trajectories_collection.find(query, {"_id": 0}).sort("createdAt", 1)]
    skills = [
        await _serialize_skill(doc)
        async for doc in capabilities_collection.find({**query, "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", 1)
    ]
    return {"capabilities": [*tools, *trajectories, *skills], "tools": tools, "trajectories": trajectories, "skills": skills}


@router.get("/companies/{company_id}/capability-graph")
async def get_company_capability_graph(company_id: str, email: str = ""):
    await _ensure_company(company_id)
    query: dict[str, Any] = {"companyId": company_id}
    if email:
        query["email"] = email

    connector_docs = await connectors_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=500)
    entity_docs = await entities_collection.find(query, {"_id": 0}).sort("name", 1).to_list(length=500)
    resource_docs = await knowledge_documents_collection.find(query, {"_id": 0, "storagePath": 0}).sort("createdAt", 1).to_list(length=1000)
    vector_store_docs = await vector_databases_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=500)
    tool_docs = await tools_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    benchmark_docs = await benchmarks_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=500)
    task_docs = await benchmark_tasks_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    trajectory_docs = await trajectories_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    skill_docs = await capabilities_collection.find({**query, "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    session_docs = await sessions_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    approval_docs = await approvals_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    artifact_docs = await artifacts_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    work_item_docs = await work_items_collection.find(query, {"_id": 0}).sort("createdAt", 1).to_list(length=1000)
    linked_eval_ids = _dedupe_strings([
        *[str(task.get("taskId") or "") for task in task_docs],
        *[str(task.get("evalId") or "") for task in task_docs],
        *[str(trajectory.get("evalId") or "") for trajectory in trajectory_docs],
        *[str(skill.get("evalId") or "") for skill in skill_docs],
    ])
    linked_benchmark_ids = _dedupe_strings([
        *[str(benchmark.get("benchmarkId") or "") for benchmark in benchmark_docs],
        *[str(task.get("benchmarkId") or "") for task in task_docs],
        *[str(trajectory.get("benchmarkId") or "") for trajectory in trajectory_docs],
        *[str(skill.get("benchmarkId") or "") for skill in skill_docs],
    ])
    eval_run_filters: list[dict[str, Any]] = []
    if linked_eval_ids:
        eval_run_filters.append({"evalId": {"$in": linked_eval_ids}})
    if linked_benchmark_ids:
        eval_run_filters.append({"benchmarkId": {"$in": linked_benchmark_ids}})
    eval_run_query: dict[str, Any] = {"$or": eval_run_filters} if eval_run_filters else dict(query)
    if email:
        eval_run_query["email"] = email
    eval_run_docs = await eval_runs_collection.find(eval_run_query, {"_id": 0, "actions": 0, "screenshots": 0}).sort("createdAt", 1).to_list(length=1000)

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    entity_by_name = _entity_names(entity_docs)
    tool_by_ref = _tool_lookup(tool_docs)
    resource_node_ids: list[str] = []
    task_nodes_by_eval_id: dict[str, str] = {}
    task_nodes_by_benchmark_id: dict[str, list[str]] = {}

    for connector in connector_docs:
        connector_id = str(connector.get("connectorId") or "")
        _add_node(nodes, "connector", connector_id, str(connector.get("name") or connector_id), {
            "connectorId": connector_id,
            "type": connector.get("type", ""),
            "status": connector.get("status", ""),
            "provider": connector.get("provider", ""),
        })

    for entity in entity_docs:
        entity_id = str(entity.get("entityId") or entity.get("name") or "")
        entity_node = _add_node(nodes, "entity", entity_id, str(entity.get("name") or entity_id), {
            "entityId": entity.get("entityId", ""),
            "name": entity.get("name", ""),
            "sourceConnectorId": entity.get("sourceConnectorId", ""),
            "source": entity.get("source", ""),
        })
        connector_node = f"connector:{entity.get('sourceConnectorId')}"
        _add_edge(edges, connector_node, entity_node, "maps_entity", {"source": "entity.sourceConnectorId"})

    for vector_store in vector_store_docs:
        vector_store_id = str(vector_store.get("vectorDatabaseId") or "")
        vector_node = _add_node(nodes, "vector_store", vector_store_id, str(vector_store.get("name") or vector_store.get("collectionName") or vector_store_id), _vector_store_payload(vector_store))
        connector_id = str(vector_store.get("connectorId") or "")
        if connector_id:
            _add_edge(edges, f"connector:{connector_id}", vector_node, "backs_vector_store", {"source": "vector_store.connectorId"})

    for resource in resource_docs:
        resource_id = str(resource.get("resourceId") or resource.get("documentId") or "")
        resource_node = _add_node(nodes, "resource", resource_id, str(resource.get("filename") or resource.get("name") or resource_id), _resource_payload(resource))
        if resource_node:
            resource_node_ids.append(resource_node)
        vector_store_id = str(resource.get("vectorDatabaseId") or _resource_indexing(resource).get("vectorDatabaseId") or "")
        connector_id = str(resource.get("connectorId") or _resource_governance(resource).get("connectorId") or "")
        if vector_store_id:
            _add_edge(edges, f"vector_store:{vector_store_id}", resource_node, "indexes_resource", {"source": "resource.vectorDatabaseId"})
        if connector_id:
            _add_edge(edges, f"connector:{connector_id}", resource_node, "grounds_connector", {"source": "resource.connectorId"})
        for tool_ref in _resource_read_tools(resource):
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, resource_node, tool_node, "read_by_tool", {"source": "resource.readTools"})

    for tool in tool_docs:
        tool_id = str(tool.get("toolId") or "")
        tool_node = _add_node(nodes, "tool", tool_id, str(tool.get("name") or tool_id), _serialize_tool(tool))
        _add_edge(edges, f"connector:{tool.get('connectorId')}", tool_node, "exposes_tool", {"source": "tool.connectorId"})
        for entity_name in tool.get("inputEntities") or []:
            entity = entity_by_name.get(str(entity_name).lower())
            entity_id = str((entity or {}).get("entityId") or entity_name)
            entity_node = _add_node(nodes, "entity", entity_id, str((entity or {}).get("name") or entity_name), entity or {"name": entity_name})
            _add_edge(edges, entity_node, tool_node, "input_entity", {"source": "tool.inputEntities"})
        output_entity = str(tool.get("outputEntity") or "")
        if output_entity:
            entity = entity_by_name.get(output_entity.lower())
            entity_id = str((entity or {}).get("entityId") or output_entity)
            entity_node = _add_node(nodes, "entity", entity_id, str((entity or {}).get("name") or output_entity), entity or {"name": output_entity})
            _add_edge(edges, tool_node, entity_node, "output_entity", {"source": "tool.outputEntity"})

    for benchmark in benchmark_docs:
        benchmark_id = str(benchmark.get("benchmarkId") or "")
        _add_node(nodes, "benchmark", benchmark_id, str(benchmark.get("name") or benchmark_id), {
            "benchmarkId": benchmark_id,
            "agentId": benchmark.get("agentId", ""),
            "status": benchmark.get("status", ""),
            "description": benchmark.get("description", ""),
        })

    for task in task_docs:
        task_id = str(task.get("taskId") or "")
        task_contract = task_contract_from_record(task)
        task_node = _add_node(nodes, "task", task_id, str(task.get("name") or task.get("taskName") or task_id), {
            "taskId": task_id,
            "benchmarkId": task.get("benchmarkId", ""),
            "status": task.get("status", ""),
            "businessIntent": task_contract["businessIntent"],
            "allowedSystems": task_contract["allowedSystems"],
            "expectedArtifacts": task_contract["expectedArtifacts"],
            "riskClass": task_contract["riskClass"],
            "successCriteria": task_contract["successCriteria"],
            "taskContract": task_contract,
        })
        if task_node:
            task_nodes_by_eval_id[task_id] = task_node
            eval_id = str(task.get("evalId") or "")
            if eval_id:
                task_nodes_by_eval_id[eval_id] = task_node
            benchmark_id = str(task.get("benchmarkId") or "")
            if benchmark_id:
                task_nodes_by_benchmark_id.setdefault(benchmark_id, []).append(task_node)
        _add_edge(edges, f"benchmark:{task.get('benchmarkId')}", task_node, "contains_task", {"source": "benchmark_tasks"})
        if task.get("trajectoryId"):
            _add_edge(edges, task_node, f"trajectory:{task.get('trajectoryId')}", "produced_trajectory", {"source": "task.trajectoryId"})
        if "knowledge" in {str(system or "").lower() for system in task_contract["allowedSystems"]}:
            for resource_node in resource_node_ids:
                _add_edge(edges, resource_node, task_node, "grounds_task", {"source": "task.allowedSystems"})

    for trajectory in trajectory_docs:
        trajectory_id = str(trajectory.get("trajectoryId") or "")
        trajectory_node = _add_node(nodes, "trajectory", trajectory_id, str(trajectory.get("taskName") or trajectory.get("name") or trajectory_id), _serialize_trajectory(trajectory))
        _add_edge(edges, f"benchmark:{trajectory.get('benchmarkId')}", trajectory_node, "evaluated_by", {"source": "trajectory.benchmarkId"})
        _add_edge(edges, f"task:{trajectory.get('taskId')}", trajectory_node, "produced_trajectory", {"source": "trajectory.taskId"})
        for connector_id in trajectory.get("connectorIds") or []:
            _add_edge(edges, f"connector:{connector_id}", trajectory_node, "used_in_trajectory", {"source": "trajectory.connectorIds"})
        for tool_ref in trajectory.get("toolIds") or []:
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, tool_node, trajectory_node, "used_in_trajectory", {"source": "trajectory.toolIds"})

    serialized_skills = [await _serialize_skill(skill) for skill in skill_docs]
    skill_nodes_by_eval_id: dict[str, list[str]] = {}
    skill_nodes_by_benchmark_id: dict[str, list[str]] = {}
    for skill in serialized_skills:
        skill_id = str(skill.get("skillId") or skill.get("capabilityId") or "")
        skill_node = _add_node(nodes, "skill", skill_id, str(skill.get("name") or skill_id), skill)
        if skill_node:
            eval_id = str(skill.get("evalId") or "")
            if eval_id:
                skill_nodes_by_eval_id.setdefault(eval_id, []).append(skill_node)
            benchmark_id = str(skill.get("benchmarkId") or "")
            if benchmark_id:
                skill_nodes_by_benchmark_id.setdefault(benchmark_id, []).append(skill_node)
        for trajectory_id in skill.get("trajectoryIds") or []:
            _add_edge(edges, f"trajectory:{trajectory_id}", skill_node, "promoted_to", {"source": "skill.trajectoryIds"})
        for tool_ref in skill.get("toolIds") or []:
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, tool_node, skill_node, "used_by_skill", {"source": "skill.toolIds"})
            if str(tool_ref).startswith("knowledge."):
                for resource_node in resource_node_ids:
                    _add_edge(edges, resource_node, skill_node, "grounds_skill", {"source": "skill.toolIds"})
        for entity_name in skill.get("inputEntities") or []:
            entity = entity_by_name.get(str(entity_name).lower())
            entity_id = str((entity or {}).get("entityId") or entity_name)
            entity_node = _add_node(nodes, "entity", entity_id, str((entity or {}).get("name") or entity_name), entity or {"name": entity_name})
            _add_edge(edges, entity_node, skill_node, "input_entity", {"source": "skill.inputEntities"})
        output_entity = str(skill.get("outputEntity") or "")
        if output_entity:
            entity = entity_by_name.get(output_entity.lower())
            entity_id = str((entity or {}).get("entityId") or output_entity)
            entity_node = _add_node(nodes, "entity", entity_id, str((entity or {}).get("name") or output_entity), entity or {"name": output_entity})
            _add_edge(edges, skill_node, entity_node, "output_entity", {"source": "skill.outputEntity"})

    for run in eval_run_docs:
        run_id = str(run.get("runId") or "")
        run_node = _add_node(nodes, "eval_run", run_id, str(run.get("agentTaskName") or run.get("evalId") or run_id), _eval_run_payload(run))
        benchmark_id = str(run.get("benchmarkId") or "")
        eval_id = str(run.get("evalId") or "")
        session_id = str(run.get("sessionId") or "")
        if benchmark_id:
            _add_edge(edges, f"benchmark:{benchmark_id}", run_node, "has_regression_run", {"source": "eval_run.benchmarkId"})
        for task_node in _dedupe_strings([task_nodes_by_eval_id.get(eval_id, ""), *task_nodes_by_benchmark_id.get(benchmark_id, [])]):
            _add_edge(edges, task_node, run_node, "evaluated_by_run", {"source": "eval_run.evalId"})
        for skill_node in _dedupe_strings([*skill_nodes_by_eval_id.get(eval_id, []), *skill_nodes_by_benchmark_id.get(benchmark_id, [])]):
            _add_edge(edges, run_node, skill_node, "gates_skill", {"source": "eval_run.evalId"})
        if session_id:
            _add_edge(edges, run_node, f"session:{session_id}", "replayed_session", {"source": "eval_run.sessionId"})

    for session in session_docs:
        session_id = str(session.get("sessionId") or "")
        session_node = _add_node(nodes, "session", session_id, str(session.get("prompt") or session_id), _session_runtime_payload(session))
        skill_id = _runtime_ref(session, "matchedSkillId") or _runtime_ref(session, "skillId")
        trajectory_id = _runtime_ref(session, "trajectoryId")
        if skill_id:
            _add_edge(edges, session_node, f"skill:{skill_id}", "exercised_skill", {"source": "session.runtimeState.matchedSkillId"})
        if trajectory_id:
            _add_edge(edges, session_node, f"trajectory:{trajectory_id}", "exercised_trajectory", {"source": "session.runtimeState.trajectoryId"})
        for tool_ref in _runtime_ref_list(session, "toolIds"):
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, session_node, tool_node, "exercised_tool", {"source": "session.runtimeState.toolIds"})

    for approval in approval_docs:
        approval_id = str(approval.get("approvalId") or "")
        approval_node = _add_node(nodes, "approval", approval_id, str(approval.get("title") or approval.get("approvalKey") or approval_id), _approval_runtime_payload(approval))
        session_id = str(approval.get("sessionId") or "")
        if session_id:
            _add_edge(edges, f"session:{session_id}", approval_node, "requested_approval", {"source": "approval.sessionId"})
        for ref_key, node_kind in (("skillId", "skill"), ("trajectoryId", "trajectory"), ("toolId", "tool")):
            ref = _runtime_ref(approval, ref_key)
            if ref:
                _add_edge(edges, f"{node_kind}:{ref}", approval_node, "requires_approval", {"source": f"approval.metadata.{ref_key}"})

    for artifact in artifact_docs:
        artifact_id = str(artifact.get("artifactId") or "")
        artifact_node = _add_node(nodes, "artifact", artifact_id, str(artifact.get("title") or artifact.get("name") or artifact_id), _artifact_runtime_payload(artifact))
        session_id = str(artifact.get("sessionId") or "")
        if session_id:
            _add_edge(edges, f"session:{session_id}", artifact_node, "created_artifact", {"source": "artifact.sessionId"})
        for ref_key, node_kind in (("skillId", "skill"), ("trajectoryId", "trajectory"), ("toolId", "tool")):
            ref = _runtime_ref(artifact, ref_key)
            if ref:
                _add_edge(edges, f"{node_kind}:{ref}", artifact_node, "produced_artifact", {"source": f"artifact.metadata.{ref_key}"})

    for work_item in work_item_docs:
        work_item_id = str(work_item.get("workItemId") or "")
        work_node = _add_node(nodes, "work_item", work_item_id, str(work_item.get("title") or work_item_id), _work_item_payload(work_item))
        source_benchmark_id = str(work_item.get("sourceBenchmarkId") or "")
        source_task_id = str(work_item.get("sourceTaskId") or "")
        if source_benchmark_id:
            _add_edge(edges, f"benchmark:{source_benchmark_id}", work_node, "scheduled_from_benchmark", {"source": "work.sourceBenchmarkId"})
        if source_task_id:
            _add_edge(edges, f"task:{source_task_id}", work_node, "scheduled_from_task", {"source": "work.sourceTaskId"})
        session_ids = _dedupe_strings([str(work_item.get("currentSessionId") or ""), *_work_ref_list(work_item, "latestSessionIds")])
        for session_id in session_ids:
            _add_edge(edges, work_node, f"session:{session_id}", "opened_session", {"source": "work.currentSessionId"})
        for skill_id in _work_ref_list(work_item, "latestMatchedSkillIds"):
            _add_edge(edges, work_node, f"skill:{skill_id}", "orchestrates_skill", {"source": "work.operational.latestMatchedSkillIds"})
        for trajectory_id in _work_ref_list(work_item, "latestMatchedTrajectoryIds"):
            _add_edge(edges, work_node, f"trajectory:{trajectory_id}", "orchestrates_trajectory", {"source": "work.operational.latestMatchedTrajectoryIds"})
        for tool_ref in _work_ref_list(work_item, "latestToolIds"):
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, work_node, tool_node, "orchestrates_tool", {"source": "work.operational.latestToolIds"})

    edge_list = list(edges.values())
    return {
        "graph": {
            "companyId": company_id,
            "nodes": list(nodes.values()),
            "edges": edge_list,
            "coverage": _capability_graph_coverage(
                entity_docs=entity_docs,
                resource_docs=resource_docs,
                vector_store_docs=vector_store_docs,
                tool_docs=tool_docs,
                benchmark_docs=benchmark_docs,
                task_docs=task_docs,
                trajectory_docs=trajectory_docs,
                skill_docs=serialized_skills,
                eval_run_docs=eval_run_docs,
                session_docs=session_docs,
                approval_docs=approval_docs,
                artifact_docs=artifact_docs,
                work_item_docs=work_item_docs,
                edges=edge_list,
            ),
        }
    }


@router.get("/companies/{company_id}/tools")
async def list_company_tools(company_id: str, email: str = ""):
    await _ensure_company(company_id)
    query: dict[str, Any] = {"companyId": company_id}
    if email:
        query["email"] = email
    return {"tools": [_serialize_tool(doc) async for doc in tools_collection.find(query, {"_id": 0}).sort("createdAt", 1)]}


@router.post("/companies/{company_id}/tools")
async def create_company_tool(company_id: str, body: ToolCreateRequest):
    await _ensure_company(company_id)
    connector = await _connector(body.connectorId)
    if connector.get("companyId") != company_id:
        raise HTTPException(status_code=400, detail="Connector does not belong to this company")
    now = _now()
    tool_id = str(uuid.uuid4())
    doc = {
        "toolId": tool_id,
        "email": body.email,
        "companyId": company_id,
        "connectorId": body.connectorId,
        "connectorName": connector.get("name", ""),
        "name": body.name,
        "displayName": body.name.split(".")[-1].replace("_", " ").title(),
        "description": body.description,
        "inputSchema": body.inputSchema,
        "outputSchema": body.outputSchema,
        "executionType": body.executionType,
        "surface": connector_surface(connector),
        "runtimeRequirements": connector_toolkit(connector).get("runtimeRequirements", []),
        "sideEffects": body.sideEffects,
        "permissions": body.permissions,
        "riskLevel": body.riskLevel,
        "inputEntities": body.inputEntities,
        "outputEntity": body.outputEntity,
        "outputCard": body.outputCard,
        "status": body.status,
        "source": "manual",
        "createdAt": now,
        "updatedAt": now,
    }
    await tools_collection.insert_one(doc)
    return {"success": True, "tool": _serialize_tool(doc)}


@router.patch("/tools/{tool_id}/approval")
async def update_tool_approval(tool_id: str, body: CapabilityApprovalUpdateRequest):
    tool = await tools_collection.find_one({"toolId": tool_id}, {"_id": 0})
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if body.email and tool.get("email") != body.email:
        raise HTTPException(status_code=404, detail="Tool not found")
    permissions = tool.get("permissions") if isinstance(tool.get("permissions"), dict) else {}
    updated = {**permissions, "approval": _clean_approval_mode(body.approval)}
    await tools_collection.update_one({"toolId": tool_id}, {"$set": {"permissions": updated, "updatedAt": _now()}})
    return {"success": True, "tool": _serialize_tool({**tool, "permissions": updated, "updatedAt": _now()})}


@router.patch("/skills/{skill_id}/approval")
async def update_skill_approval(skill_id: str, body: CapabilityApprovalUpdateRequest):
    skill = await capabilities_collection.find_one({"capabilityId": skill_id, "capabilityKind": "skill"}, {"_id": 0})
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if body.email and skill.get("email") != body.email:
        raise HTTPException(status_code=404, detail="Skill not found")
    permissions = skill.get("permissions") if isinstance(skill.get("permissions"), dict) else {}
    updated = {**permissions, "approval": _clean_approval_mode(body.approval)}
    await capabilities_collection.update_one({"capabilityId": skill_id}, {"$set": {"permissions": updated, "updatedAt": _now()}})
    return {"success": True, "skill": await _serialize_skill({**skill, "permissions": updated, "updatedAt": _now()})}


@router.patch("/skills/{skill_id}")
async def update_company_skill(skill_id: str, body: SkillUpdateRequest):
    skill = await capabilities_collection.find_one({"capabilityId": skill_id, "capabilityKind": "skill"}, {"_id": 0})
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if body.email and skill.get("email") != body.email:
        raise HTTPException(status_code=404, detail="Skill not found")

    update: dict[str, Any] = {}
    trajectory_docs: list[dict[str, Any]] | None = None
    if body.name is not None:
        update["name"] = body.name.strip() or skill.get("name", "") or "Skill"
    if body.description is not None:
        update["description"] = body.description.strip()
    if body.whenToUse is not None:
        update["whenToUse"] = body.whenToUse.strip()
    if body.instructions is not None:
        update["instructions"] = body.instructions.strip()
    if body.preconditions is not None:
        update["preconditions"] = _dedupe_strings(body.preconditions)
    if body.expectedArtifacts is not None:
        update["expectedArtifacts"] = _dedupe_strings(body.expectedArtifacts)
    if body.riskPolicy is not None:
        update["riskPolicy"] = body.riskPolicy.strip() or skill.get("riskPolicy", "")
    if body.status is not None:
        update["status"] = body.status.strip() or skill.get("status", "")
    if body.inputEntities is not None:
        update["inputEntities"] = _dedupe_strings(body.inputEntities)
    if body.outputEntity is not None:
        update["outputEntity"] = body.outputEntity.strip()
    if body.outputCard is not None:
        update["outputCard"] = body.outputCard
    if body.trajectoryIds is not None:
        trajectory_ids = _dedupe_strings(body.trajectoryIds)
        trajectory_docs = []
        for trajectory_id in trajectory_ids:
            trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
            if not trajectory:
                raise HTTPException(status_code=404, detail=f"Trajectory not found: {trajectory_id}")
            if trajectory.get("companyId") != skill.get("companyId"):
                raise HTTPException(status_code=400, detail="Trajectory does not belong to this company")
            trajectory_docs.append(trajectory)
        update["trajectoryIds"] = trajectory_ids
        update["connectorIds"] = _dedupe_strings([
            connector_id
            for trajectory in trajectory_docs
            for connector_id in (trajectory.get("connectorIds") or [])
        ]) or skill.get("connectorIds", [])
        update["toolIds"] = _dedupe_strings([
            tool_id
            for trajectory in trajectory_docs
            for tool_id in (trajectory.get("toolIds") or [])
        ]) or skill.get("toolIds", [])
        update["runtimeRequirements"] = _dedupe_strings([
            requirement
            for trajectory in trajectory_docs
            for requirement in (trajectory.get("runtimeRequirements") or [])
        ]) or skill.get("runtimeRequirements", [])
        benchmark_ids = _dedupe_strings([str(trajectory.get("benchmarkId") or "") for trajectory in trajectory_docs])
        eval_ids = _dedupe_strings([str(trajectory.get("evalId") or "") for trajectory in trajectory_docs])
        update["benchmarkId"] = benchmark_ids[0] if benchmark_ids else skill.get("benchmarkId", "")
        update["evalId"] = eval_ids[0] if eval_ids else skill.get("evalId", "")

    candidate_skill = {**skill, **update}
    if str(candidate_skill.get("status") or "").strip().lower() == "published":
        await _assert_skill_publishable(candidate_skill, trajectory_docs=trajectory_docs)

    now = _now()
    material_keys = {"name", "description", "whenToUse", "instructions", "preconditions", "expectedArtifacts", "riskPolicy", "status", "inputEntities", "outputEntity", "outputCard", "trajectoryIds", "connectorIds", "toolIds", "runtimeRequirements", "benchmarkId", "evalId"}
    material_changed = any(key in update and skill.get(key) != candidate_skill.get(key) for key in material_keys)
    previous_promotion_status = _skill_promotion_status(skill)
    if material_changed:
        next_version = _skill_version(skill) + 1
        update["version"] = next_version
        update["versionLabel"] = f"v{next_version}"
    candidate_skill = {**skill, **update}
    update.update(_skill_lifecycle_fields(previous=skill, next_doc=candidate_skill, now=now))
    candidate_skill = {**skill, **update}
    next_promotion_status = _skill_promotion_status(candidate_skill)
    if material_changed or previous_promotion_status != next_promotion_status:
        event_reason = "promotion_status_change" if previous_promotion_status != next_promotion_status else "material_update"
        update["versionHistory"] = _append_skill_version_event(
            skill,
            candidate_skill,
            now=now,
            reason=event_reason,
        )
    update["updatedAt"] = now
    await capabilities_collection.update_one({"capabilityId": skill_id}, {"$set": update})
    refreshed = {**skill, **update}
    return {"success": True, "skill": await _serialize_skill(refreshed)}


@router.post("/tools/{tool_id}/test")
async def test_company_tool(tool_id: str, body: ToolTestRequest):
    tool = await tools_collection.find_one({"toolId": tool_id}, {"_id": 0})
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if body.email and tool.get("email") != body.email:
        raise HTTPException(status_code=404, detail="Tool not found")
    now = _now()
    try:
        result = await execute_connector_tool(
            company_id=str(tool.get("companyId") or ""),
            tool_name=str(tool.get("name") or ""),
            arguments=body.arguments,
        )
        await tools_collection.update_one(
            {"toolId": tool_id},
            {"$set": {"lastTestAt": now, "lastTestStatus": "passed" if result.get("success") else "failed", "lastTestResult": result, "updatedAt": now}},
        )
        return {"success": bool(result.get("success")), "result": result}
    except Exception as exc:
        result = {"tool": tool.get("name", ""), "success": False, "error": str(exc)}
        await tools_collection.update_one(
            {"toolId": tool_id},
            {"$set": {"lastTestAt": now, "lastTestStatus": "failed", "lastTestResult": result, "updatedAt": now}},
        )
        return {"success": False, "result": result}


@router.post("/connectors/{connector_id}/publish-tools")
async def publish_connector_tools(connector_id: str):
    connector = await _connector(connector_id)
    return await _publish_default_tools_for_connector(connector)


@router.post("/companies/{company_id}/capabilities/publish-tools")
async def publish_company_connector_tools(company_id: str, body: CompanyCapabilityPublishRequest):
    await _ensure_company(company_id)
    connector = await _connector(body.connectorId)
    _ensure_connector_belongs_to_company(connector, company_id)
    return await _publish_default_tools_for_connector(connector)


@router.post("/companies/{company_id}/capabilities/harvest")
async def harvest_company_capabilities(company_id: str, body: CompanyCapabilityHarvestRequest):
    await _ensure_company(company_id)
    connector = await _connector(body.connectorId)
    _ensure_connector_belongs_to_company(connector, company_id)
    return await _harvest_capabilities_for_connector(connector, body)


@router.post("/connectors/{connector_id}/harvest-benchmark")
async def harvest_connector_benchmark(connector_id: str, body: ConnectorBenchmarkHarvestRequest):
    connector = await _connector(connector_id)
    return await _harvest_capabilities_for_connector(connector, body)


@router.post("/connectors/{connector_id}/harvest")
async def harvest_connector(connector_id: str):
    connector = await _connector(connector_id)
    if _uses_default_toolkit(connector):
        raise HTTPException(
            status_code=400,
            detail="Official connectors already ship with default tools. Use /publish-tools instead of running a harvester.",
        )

    run = await _create_capability_run(
        connector=connector,
        run_kind="harvester",
        harvester_type="",
        logs=["Harvester run started for a custom/private or UI-driven connector."],
    )

    try:
        result = await harvest_connector_capabilities(connector)
        upserted_tools = await _upsert_tools(result.get("tools", []))
        run = await _complete_capability_run(run, result, upserted_tools)
        return {"success": True, "run": run, "tools": upserted_tools}
    except Exception as exc:
        failed = _now()
        update = {"status": "failed", "errors": [str(exc)], "completedAt": failed, "updatedAt": failed}
        await harvester_runs_collection.update_one({"harvesterRunId": run["harvesterRunId"]}, {"$set": update})
        run.update(update)
        return {"success": False, "run": run, "tools": []}


@router.get("/companies/{company_id}/harvester-runs")
async def list_harvester_runs(company_id: str, email: str = ""):
    await _ensure_company(company_id)
    query: dict[str, Any] = {"companyId": company_id}
    if email:
        query["email"] = email
    cursor = harvester_runs_collection.find(query, {"_id": 0}).sort("createdAt", -1)
    return {"runs": await cursor.to_list(length=500)}


@router.post("/companies/{company_id}/trajectories")
async def create_company_trajectory(company_id: str, body: CompanyTrajectoryCreateRequest):
    await _ensure_company(company_id)
    now = _now()
    trajectory_id = str(uuid.uuid4())
    doc = {
        "trajectoryId": trajectory_id,
        "email": body.email,
        "companyId": company_id,
        "agentId": "",
        "webId": "",
        "name": body.name,
        "intent": body.intent or body.prompt,
        "prompt": body.prompt or body.intent,
        "connectorIds": body.connectorIds,
        "toolIds": body.toolIds,
        "runtimeRequirements": [],
        "steps": body.steps,
        "inputSchema": body.inputSchema,
        "validations": body.validations,
        "recoverySteps": body.recoverySteps,
        "status": body.status,
        "source": "manual",
        "createdAt": now,
        "updatedAt": now,
    }
    await trajectories_collection.insert_one(doc)
    return {"success": True, "trajectory": _serialize_trajectory(doc)}


@router.post("/trajectories/{trajectory_id}/promote-to-skill")
async def promote_trajectory_to_skill(trajectory_id: str, body: PromoteTrajectoryRequest):
    trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    now = _now()
    capability_id = str(uuid.uuid4())
    doc = {
        "capabilityId": capability_id,
        "capabilityKind": "skill",
        "email": body.email or trajectory.get("email", ""),
        "companyId": trajectory.get("companyId", ""),
        "agentId": trajectory.get("agentId", ""),
        "webId": trajectory.get("webId", ""),
        "name": body.name or trajectory.get("name") or trajectory.get("taskName") or "Skill",
        "description": trajectory.get("prompt") or trajectory.get("intent", ""),
        "whenToUse": body.whenToUse or trajectory.get("intent") or trajectory.get("prompt", ""),
        "instructions": body.instructions or trajectory.get("prompt") or trajectory.get("intent", ""),
        "preconditions": _dedupe_strings(body.preconditions),
        "expectedArtifacts": _dedupe_strings(body.expectedArtifacts),
        "connectorIds": trajectory.get("connectorIds", []),
        "toolIds": trajectory.get("toolIds", []),
        "trajectoryIds": [trajectory_id],
        "runtimeRequirements": trajectory.get("runtimeRequirements", []),
        "permissions": body.permissions,
        "riskPolicy": body.riskPolicy,
        "inputEntities": body.inputEntities or trajectory.get("inputEntities", []),
        "outputEntity": body.outputEntity or trajectory.get("outputEntity", ""),
        "outputCard": body.outputCard or trajectory.get("outputCard", {}),
        "runtime": "trajectory_executor_with_recovery",
        "status": "ready",
        "promotionStatus": "ready",
        "version": 1,
        "versionLabel": "v1",
        "versionHistory": [
            {
                "version": 1,
                "versionLabel": "v1",
                "promotionStatus": "ready",
                "reason": "promoted_from_trajectory",
                "createdAt": now,
            }
        ],
        "readyAt": now,
        "lastPromotedAt": now,
        "source": "manual_promotion",
        "harvesterType": trajectory.get("harvester", {}).get("adapter", "") if isinstance(trajectory.get("harvester"), dict) else trajectory.get("harvesterType", ""),
        "harvesterRunId": trajectory.get("harvesterRunId", ""),
        "judge": trajectory.get("judge", {}),
        "createdAt": now,
        "updatedAt": now,
    }
    await capabilities_collection.insert_one(doc)
    await trajectories_collection.update_one(
        {"trajectoryId": trajectory_id},
        {"$set": {"status": "promoted", "promotedSkillId": capability_id, "updatedAt": now}},
    )
    return {"success": True, "skill": await _serialize_skill(doc)}


@router.post("/trajectories/{trajectory_id}/review")
async def review_trajectory(trajectory_id: str, body: TrajectoryReviewRequest):
    trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    if body.email and trajectory.get("email") != body.email:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    label = str(body.label or "").lower().strip()
    if label not in {"approved", "rejected", "needs_review"}:
        raise HTTPException(status_code=400, detail="label must be approved, rejected, or needs_review")
    now = _now()
    status = "approved" if label == "approved" else "rejected" if label == "rejected" else "needs_review"
    review = {
        "label": label,
        "reviewerEmail": body.email,
        "notes": body.notes,
        "reviewedAt": now,
    }
    await trajectories_collection.update_one(
        {"trajectoryId": trajectory_id},
        {"$set": {"status": status, "review": review, "updatedAt": now}},
    )
    updated = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0}) or {**trajectory, "status": status, "review": review}
    return {"success": True, "trajectory": _serialize_trajectory(updated)}
