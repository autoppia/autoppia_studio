import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    capabilities_collection,
    benchmark_tasks_collection,
    companies_collection,
    connectors_collection,
    evals_collection,
    harvester_runs_collection,
    tools_collection,
    trajectories_collection,
)
from app.harvesters import harvest_connector_capabilities
from app.harvesters.base import connector_surface
from app.harvesters.toolkit import ToolkitHarvester
from app.connectors import execute_connector_tool
from app.routes.connectors import connector_toolkit

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


def _serialize_skill(doc: dict[str, Any]) -> dict[str, Any]:
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
        "benchmarkId": doc.get("benchmarkId", ""),
        "evalId": doc.get("evalId", ""),
        "permissions": doc.get("permissions", {}),
        "riskPolicy": doc.get("riskPolicy", ""),
        "inputEntities": doc.get("inputEntities", []),
        "outputEntity": doc.get("outputEntity", ""),
        "outputCard": doc.get("outputCard", {}),
        "runtime": doc.get("runtime", ""),
        "status": doc.get("status", "draft"),
        "source": doc.get("source", ""),
        "harvesterType": doc.get("harvesterType", ""),
        "harvesterRunId": doc.get("harvesterRunId", ""),
        "discovererName": doc.get("discovererName", ""),
        "discovererVersion": doc.get("discovererVersion", ""),
        "judge": doc.get("judge", {}),
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
    doc["createdAt"] = existing.get("createdAt") if existing else doc.get("createdAt", _now())
    doc["updatedAt"] = _now()
    await capabilities_collection.update_one({"capabilityId": doc["capabilityId"]}, {"$set": doc}, upsert=True)
    return _serialize_skill(doc)


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
        _serialize_skill(doc)
        async for doc in capabilities_collection.find({**query, "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", 1)
    ]
    return {"capabilities": [*tools, *trajectories, *skills], "tools": tools, "trajectories": trajectories, "skills": skills}


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
    return {"success": True, "skill": _serialize_skill({**skill, "permissions": updated, "updatedAt": _now()})}


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
    return {"success": True, "skill": _serialize_skill(doc)}


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
