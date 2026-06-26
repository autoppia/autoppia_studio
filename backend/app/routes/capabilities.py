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
from app.services.capability_graph_coverage import capability_graph_coverage
from app.services.capability_graph_nodes import add_edge as _add_edge
from app.services.capability_graph_nodes import add_node as _add_node
from app.services.capability_graph_nodes import approval_mode_payload as _approval_mode_payload
from app.services.capability_graph_nodes import approval_runtime_payload as _approval_runtime_payload
from app.services.capability_graph_nodes import artifact_runtime_payload as _artifact_runtime_payload
from app.services.capability_graph_nodes import browser_policy_id as _browser_policy_id
from app.services.capability_graph_nodes import browser_policy_payload as _browser_policy_payload
from app.services.capability_graph_nodes import capability_boundary as _capability_boundary
from app.services.capability_graph_nodes import dedupe_strings as _dedupe_strings
from app.services.capability_graph_nodes import entity_names as _entity_names
from app.services.capability_graph_nodes import eval_run_label as _eval_run_label
from app.services.capability_graph_nodes import eval_run_payload as _eval_run_payload
from app.services.capability_graph_nodes import policy_boundary_payload as _policy_boundary_payload
from app.services.capability_graph_nodes import runtime_ref as _runtime_ref
from app.services.capability_graph_nodes import runtime_ref_list as _runtime_ref_list
from app.services.capability_graph_nodes import session_runtime_payload as _session_runtime_payload
from app.services.capability_graph_nodes import tool_lookup as _tool_lookup
from app.services.capability_graph_nodes import vector_store_payload as _vector_store_payload
from app.services.capability_graph_nodes import work_item_payload as _work_item_payload
from app.services.capability_graph_nodes import work_ref_list as _work_ref_list
from app.services.resource_governance import resource_governance
from app.services.resource_governance import resource_payload
from app.services.resource_governance import resource_read_tools
from app.services.resource_governance import resource_vector_id
from app.services.runtime_policy import serialize_runtime_policy
from app.services.skill_evidence import skill_hardening_status
from app.services.skill_evidence import skill_lineage
from app.services.skill_evidence import source_trajectory_evidence
from app.services.skill_lifecycle import append_skill_version_event
from app.services.skill_lifecycle import skill_lifecycle_fields
from app.services.skill_lifecycle import skill_material_change_keys
from app.services.skill_lifecycle import skill_promotion_status
from app.services.skill_lifecycle import skill_version
from app.services.skill_lifecycle import skill_version_history
from app.services.skill_manifests import skill_io_contract
from app.services.skill_manifests import skill_package_manifest
from app.services.skill_manifests import skill_production_gate
from app.services.skill_regressions import latest_skill_regression
from app.services.skill_regressions import skill_regression_cases
from app.services.skill_regressions import skill_trajectory_docs
from app.services.task_contracts import task_contract_from_record
from app.services.tool_synthesis import capability_tool_synthesis_contract
from app.services.vertical_demos import vertical_demo_payload

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
    tool_synthesis = capability_tool_synthesis_contract(doc)
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
    version = skill_version(doc)
    trajectory_ids = _dedupe_strings([str(value or "") for value in doc.get("trajectoryIds", [])])
    trajectory_docs: list[dict[str, Any]] = []
    latest_regression: dict[str, Any] | None = None
    regression_cases: list[dict[str, Any]] = []
    try:
        for trajectory_id in trajectory_ids:
            trajectory = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
            if trajectory:
                trajectory_docs.append(trajectory)
        latest_regression = await latest_skill_regression(
            doc,
            trajectory_docs=trajectory_docs,
            benchmark_tasks=benchmark_tasks_collection,
            legacy_evals=evals_collection,
            eval_runs=eval_runs_collection,
        )
        regression_cases = await skill_regression_cases(
            doc,
            trajectory_docs=trajectory_docs,
            benchmark_tasks=benchmark_tasks_collection,
            legacy_evals=evals_collection,
        )
    except Exception:
        trajectory_docs = []
        latest_regression = None
        regression_cases = []
    lineage = skill_lineage(doc, trajectory_docs)
    hardening = skill_hardening_status(doc, trajectory_docs=trajectory_docs, latest_regression=latest_regression)
    runtime_policy = serialize_runtime_policy(doc)
    version_history = skill_version_history(doc, version=version, promotion_status=skill_promotion_status(doc))
    package = skill_package_manifest(
        doc,
        version=version,
        promotion_status=skill_promotion_status(doc),
        runtime_policy=runtime_policy,
        lineage=lineage,
        hardening=hardening,
        latest_regression=latest_regression,
        source_trajectories=source_trajectory_evidence(trajectory_docs),
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
        "promotionStatus": skill_promotion_status(doc),
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
    doc["version"] = skill_version(existing or doc)
    doc["versionLabel"] = doc.get("versionLabel") or f"v{doc['version']}"
    doc["promotionStatus"] = skill_promotion_status(doc)
    doc.update(skill_lifecycle_fields(previous=existing or {}, next_doc=doc, now=now))
    doc["versionHistory"] = append_skill_version_event(existing or {}, doc, now=now, reason="upserted")
    doc["updatedAt"] = now
    await capabilities_collection.update_one({"capabilityId": doc["capabilityId"]}, {"$set": doc}, upsert=True)
    return await _serialize_skill(doc)


async def _assert_skill_publishable(skill: dict[str, Any], trajectory_docs: list[dict[str, Any]] | None = None) -> None:
    trajectory_docs = await skill_trajectory_docs(skill, trajectory_docs, trajectories=trajectories_collection)
    latest = await latest_skill_regression(
        skill,
        trajectory_docs=trajectory_docs,
        benchmark_tasks=benchmark_tasks_collection,
        legacy_evals=evals_collection,
        eval_runs=eval_runs_collection,
    )
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
    hardening = skill_hardening_status(skill, trajectory_docs=trajectory_docs, latest_regression=latest)
    gate = skill_production_gate(
        hardening=hardening,
        latest_regression=latest,
        io_contract=skill_io_contract(skill),
    )
    missing = gate.get("blockers") or []
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
    task_docs_by_benchmark_id: dict[str, list[dict[str, Any]]] = {}

    def add_policy_edges(source_node: str, policy: dict[str, Any], *, boundary: str = "", evidence_source: str = "policy") -> None:
        clean_boundary = boundary if boundary in {"read", "draft", "write", "send"} else "read"
        boundary_node = _add_node(nodes, "policy_boundary", clean_boundary, f"{clean_boundary} boundary", _policy_boundary_payload(clean_boundary))
        _add_edge(edges, source_node, boundary_node, "governed_by_boundary", {"source": evidence_source})
        approval_mode = str(policy.get("approvalMode") or "auto")
        approval_node = _add_node(nodes, "approval_mode", approval_mode, f"approval {approval_mode}", _approval_mode_payload(approval_mode))
        _add_edge(edges, source_node, approval_node, "uses_approval_mode", {"source": evidence_source})
        approval_required_for = set(policy.get("approvalRequiredFor") if isinstance(policy.get("approvalRequiredFor"), list) else [])
        if "write" in approval_required_for:
            _add_edge(edges, source_node, boundary_node, "requires_write_approval", {"source": evidence_source})
        if "send" in approval_required_for:
            _add_edge(edges, source_node, boundary_node, "requires_send_approval", {"source": evidence_source})
        if policy.get("browserRuntime"):
            browser_policy_id = _browser_policy_id(policy)
            browser_node = _add_node(nodes, "browser_policy", browser_policy_id, browser_policy_id.replace("_", " "), _browser_policy_payload(policy))
            _add_edge(edges, source_node, browser_node, "uses_browser_policy", {"source": evidence_source})
            browser = policy.get("browserPolicy") if isinstance(policy.get("browserPolicy"), dict) else {}
            if browser.get("requiresSandbox"):
                _add_edge(edges, source_node, browser_node, "requires_browser_sandbox", {"source": evidence_source})
            if browser.get("restrictedByDomain"):
                _add_edge(edges, source_node, browser_node, "restricted_to_domains", {"source": evidence_source})

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
        resource_node = _add_node(nodes, "resource", resource_id, str(resource.get("filename") or resource.get("name") or resource_id), resource_payload(resource))
        if resource_node:
            resource_node_ids.append(resource_node)
        vector_store_id = resource_vector_id(resource)
        connector_id = str(resource.get("connectorId") or resource_governance(resource).get("connectorId") or "")
        if vector_store_id:
            _add_edge(edges, f"vector_store:{vector_store_id}", resource_node, "indexes_resource", {"source": "resource.vectorDatabaseId"})
        if connector_id:
            _add_edge(edges, f"connector:{connector_id}", resource_node, "grounds_connector", {"source": "resource.connectorId"})
        for tool_ref in resource_read_tools(resource):
            tool = tool_by_ref.get(str(tool_ref))
            tool_node = f"tool:{(tool or {}).get('toolId') or tool_ref}"
            _add_edge(edges, resource_node, tool_node, "read_by_tool", {"source": "resource.readTools"})

    for tool in tool_docs:
        tool_id = str(tool.get("toolId") or "")
        tool_node = _add_node(nodes, "tool", tool_id, str(tool.get("name") or tool_id), _serialize_tool(tool))
        _add_edge(edges, f"connector:{tool.get('connectorId')}", tool_node, "exposes_tool", {"source": "tool.connectorId"})
        add_policy_edges(tool_node, serialize_runtime_policy(tool), boundary=_capability_boundary(tool), evidence_source="tool.policy")
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
                task_docs_by_benchmark_id.setdefault(benchmark_id, []).append(task)
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
    skill_docs_by_benchmark_id: dict[str, list[dict[str, Any]]] = {}
    for skill in serialized_skills:
        skill_id = str(skill.get("skillId") or skill.get("capabilityId") or "")
        skill_node = _add_node(nodes, "skill", skill_id, str(skill.get("name") or skill_id), skill)
        add_policy_edges(skill_node, skill.get("runtimePolicy") if isinstance(skill.get("runtimePolicy"), dict) else serialize_runtime_policy(skill), boundary="write" if "write" in ((skill.get("runtimePolicy") or {}).get("approvalRequiredFor") or []) else "read", evidence_source="skill.runtimePolicy")
        if skill_node:
            eval_id = str(skill.get("evalId") or "")
            if eval_id:
                skill_nodes_by_eval_id.setdefault(eval_id, []).append(skill_node)
            benchmark_id = str(skill.get("benchmarkId") or "")
            if benchmark_id:
                skill_nodes_by_benchmark_id.setdefault(benchmark_id, []).append(skill_node)
                skill_docs_by_benchmark_id.setdefault(benchmark_id, []).append(skill)
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

    eval_run_docs_by_benchmark_id: dict[str, list[dict[str, Any]]] = {}
    passing_eval_run_nodes_by_benchmark_id: dict[str, list[str]] = {}
    for run in eval_run_docs:
        run_id = str(run.get("runId") or "")
        run_node = _add_node(nodes, "eval_run", run_id, str(run.get("agentTaskName") or run.get("evalId") or run_id), _eval_run_payload(run))
        benchmark_id = str(run.get("benchmarkId") or "")
        eval_id = str(run.get("evalId") or "")
        session_id = str(run.get("sessionId") or "")
        if benchmark_id:
            eval_run_docs_by_benchmark_id.setdefault(benchmark_id, []).append(run)
            if _eval_run_label(run) == "pass":
                passing_eval_run_nodes_by_benchmark_id.setdefault(benchmark_id, []).append(run_node)
            _add_edge(edges, f"benchmark:{benchmark_id}", run_node, "has_regression_run", {"source": "eval_run.benchmarkId"})
        for task_node in _dedupe_strings([task_nodes_by_eval_id.get(eval_id, ""), *task_nodes_by_benchmark_id.get(benchmark_id, [])]):
            _add_edge(edges, task_node, run_node, "evaluated_by_run", {"source": "eval_run.evalId"})
        for skill_node in _dedupe_strings([*skill_nodes_by_eval_id.get(eval_id, []), *skill_nodes_by_benchmark_id.get(benchmark_id, [])]):
            _add_edge(edges, run_node, skill_node, "gates_skill", {"source": "eval_run.evalId"})
        if session_id:
            _add_edge(edges, run_node, f"session:{session_id}", "replayed_session", {"source": "eval_run.sessionId"})

    vertical_demo_payloads: list[dict[str, Any]] = []
    for benchmark in benchmark_docs:
        benchmark_id = str(benchmark.get("benchmarkId") or "")
        demo_payload = vertical_demo_payload(
            benchmark=benchmark,
            tasks=task_docs_by_benchmark_id.get(benchmark_id, []),
            skills=skill_docs_by_benchmark_id.get(benchmark_id, []),
            runs=eval_run_docs_by_benchmark_id.get(benchmark_id, []),
        )
        if not demo_payload:
            continue
        vertical_demo_payloads.append(demo_payload)
        demo_node = _add_node(
            nodes,
            "vertical_demo",
            f"{benchmark_id}:vertical_demo",
            demo_payload.get("objective") or f"{benchmark_id} vertical demo",
            demo_payload,
        )
        _add_edge(edges, f"benchmark:{benchmark_id}", demo_node, "validates_vertical_demo", {"source": "benchmark.metadata.verticalDemo"})
        for task_node in task_nodes_by_benchmark_id.get(benchmark_id, []):
            _add_edge(edges, task_node, demo_node, "covers_demo_step", {"source": "task.benchmarkId"})
        for skill_node in skill_nodes_by_benchmark_id.get(benchmark_id, []):
            _add_edge(edges, skill_node, demo_node, "implements_demo_capability", {"source": "skill.benchmarkId"})
        for run_node in passing_eval_run_nodes_by_benchmark_id.get(benchmark_id, []):
            _add_edge(edges, run_node, demo_node, "proves_demo_replay", {"source": "eval_run.label"})

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
        work_policy = {
            "approvalMode": "auto",
            "approvalRequiredFor": ["write", "send"],
            "browserRuntime": bool(work_item.get("browserEnabled", True)),
            "browserPolicy": {
                "defaultUse": work_item.get("browserDefaultUse") or "exception",
                "restrictedByDomain": bool(work_item.get("browserRestrictedByDomain")) or bool(work_item.get("allowedDomains")),
                "allowedDomains": work_item.get("allowedDomains") if isinstance(work_item.get("allowedDomains"), list) else [],
                "requiresSandbox": bool(work_item.get("browserEnabled", True)),
                "leastPrivilege": True,
            },
        }
        add_policy_edges(work_node, work_policy, boundary="write", evidence_source="work.policy")
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
            "coverage": capability_graph_coverage(
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
                vertical_demo_payloads=vertical_demo_payloads,
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
    material_changed = bool(skill_material_change_keys(skill, candidate_skill, touched_keys=set(update)))
    previous_promotion_status = skill_promotion_status(skill)
    if material_changed:
        next_version = skill_version(skill) + 1
        update["version"] = next_version
        update["versionLabel"] = f"v{next_version}"
    candidate_skill = {**skill, **update}
    update.update(skill_lifecycle_fields(previous=skill, next_doc=candidate_skill, now=now))
    candidate_skill = {**skill, **update}
    next_promotion_status = skill_promotion_status(candidate_skill)
    if material_changed or previous_promotion_status != next_promotion_status:
        event_reason = "promotion_status_change" if previous_promotion_status != next_promotion_status else "material_update"
        update["versionHistory"] = append_skill_version_event(
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
