from __future__ import annotations

from typing import Any

from app.database import agents_collection, benchmark_tasks_collection, benchmarks_collection, connectors_collection, tools_collection, trajectories_collection
from app.services.custom_connector_executors import has_custom_connector_executor
from app.services.agent_harvesters import HarvestTask, get_agent_harvester
from app.services.skills import approve_trajectory_as_skill
from app.services.trajectory_judges import build_trajectory_judge_context, get_trajectory_judge


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _metadata(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("metadata") if isinstance(task.get("metadata"), dict) else {}


def _task_contract(task: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(task)
    contract = metadata.get("taskContract")
    return contract if isinstance(contract, dict) else {}


def _expected_tools(task: dict[str, Any]) -> list[str]:
    metadata = _metadata(task)
    evaluator = task.get("evaluator") if isinstance(task.get("evaluator"), dict) else {}
    tools = _list(metadata.get("expectedTools")) or _list(evaluator.get("expectedTools"))
    return [str(item) for item in tools if str(item or "").strip()]


def _allowed_systems(task: dict[str, Any]) -> list[str]:
    contract = _task_contract(task)
    systems = _list(task.get("allowedSystems")) + _list(_metadata(task).get("allowedSystems")) + _list(contract.get("allowedSystems"))
    result = []
    seen = set()
    for item in systems:
        clean = str(item or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _tool_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    return tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}


def _tool_has_runtime_executor(tool: dict[str, Any]) -> bool:
    metadata = _tool_metadata(tool)
    connector_type = str(tool.get("connectorType") or metadata.get("connectorType") or "").lower()
    is_custom = connector_type == "custom" or bool(metadata.get("customConnector"))
    status = str(tool.get("implementationStatus") or metadata.get("implementationStatus") or "").lower()
    if is_custom:
        return has_custom_connector_executor(tool)
    return status in {"ready", "implemented", "active"} or bool(tool.get("executor") or tool.get("runtimeExecutor") or metadata.get("executor"))


def _tool_execution_ready(tool: dict[str, Any]) -> bool:
    execution_type = str(tool.get("executionType") or "").lower()
    if execution_type == "connector_tool":
        return _tool_has_runtime_executor(tool)
    if execution_type in {"api_call", "knowledge_search", "browser_automation"}:
        return True
    return _tool_has_runtime_executor(tool)


def _tool_strategy_payload(tool: dict[str, Any]) -> dict[str, Any]:
    metadata = _tool_metadata(tool)
    return {
        "toolId": str(tool.get("toolId") or ""),
        "name": str(tool.get("name") or ""),
        "connectorId": str(tool.get("connectorId") or ""),
        "executionType": str(tool.get("executionType") or ""),
        "implementationStatus": str(tool.get("implementationStatus") or metadata.get("implementationStatus") or ""),
        "executionReady": _tool_execution_ready(tool),
        "hasRuntimeExecutor": _tool_has_runtime_executor(tool),
    }


def _implementation_gaps(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for tool in tools:
        if str(tool.get("executionType") or "").lower() != "connector_tool":
            continue
        if _tool_has_runtime_executor(tool):
            continue
        gaps.append(
            {
                "kind": "connector_tool_executor_missing",
                "toolId": str(tool.get("toolId") or ""),
                "toolName": str(tool.get("name") or ""),
                "connectorId": str(tool.get("connectorId") or ""),
                "nextAction": "Implement or attach a connector executor before this task can be executed end to end.",
            }
        )
    return gaps


def task_harvest_has_implementation_gaps(task_harvest: dict[str, Any] | None) -> bool:
    if not isinstance(task_harvest, dict):
        return False
    if int(task_harvest.get("implementationRequiredCount") or 0) > 0:
        return True
    for result in task_harvest.get("results") or []:
        if not isinstance(result, dict):
            continue
        if str(result.get("status") or "") == "implementation_required":
            return True
        strategy = result.get("strategy") if isinstance(result.get("strategy"), dict) else {}
        if strategy.get("implementationGaps"):
            return True
    if str(task_harvest.get("status") or "") == "implementation_required":
        return True
    if task_harvest.get("implementationGaps"):
        return True
    strategy = task_harvest.get("strategy") if isinstance(task_harvest.get("strategy"), dict) else {}
    return bool(strategy.get("implementationGaps"))


async def plan_task_strategy(task: dict[str, Any], *, agent_config: dict[str, Any] | None = None) -> dict[str, Any]:
    company_id = str(task.get("companyId") or (agent_config or {}).get("companyId") or "")
    metadata = _metadata(task)
    expected_tools = _expected_tools(task)
    allowed_systems = _allowed_systems(task)
    connectors = await connectors_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=200) if company_id else []
    tools = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500) if company_id else []
    tool_names = {str(tool.get("name") or "") for tool in tools}
    tools_by_name = {str(tool.get("name") or ""): tool for tool in tools if str(tool.get("name") or "")}
    matched_tools = [tools_by_name[name] for name in expected_tools if name in tools_by_name]
    matched_execution_types = {str(tool.get("executionType") or "").lower() for tool in matched_tools}
    matched_tool_payloads = [_tool_strategy_payload(tool) for tool in matched_tools]
    implementation_gaps = _implementation_gaps(matched_tools)
    connector_types = {str(connector.get("type") or "").lower() for connector in connectors}

    evidence: list[dict[str, Any]] = []
    if expected_tools:
        evidence.append({"kind": "expected_tools", "values": expected_tools})
    if allowed_systems:
        evidence.append({"kind": "allowed_systems", "values": allowed_systems})
    if metadata.get("customConnector") or "connector_tool" in matched_execution_types:
        strategy = "connector_tool"
        reason = "Task targets a custom connector tool or connector implementation gap."
    elif metadata.get("prefersApi") or "api_call" in matched_execution_types:
        strategy = "api_tool"
        reason = "Task metadata or matched tool execution type indicates an API path."
    elif metadata.get("usesKnowledge") or "knowledge_search" in matched_execution_types or any("knowledge" in value.lower() for value in expected_tools + allowed_systems):
        strategy = "knowledge"
        reason = "Task is grounded in company knowledge or a knowledge connector is available."
    elif metadata.get("requiresBrowser") or "browser_automation" in matched_execution_types or any(str(system).startswith(("http://", "https://")) for system in allowed_systems):
        strategy = "browser"
        reason = "Task needs a web surface or browser-capable connector."
    elif "knowledge" in connector_types:
        strategy = "knowledge"
        reason = "A company knowledge connector is available."
    elif "web" in connector_types:
        strategy = "browser"
        reason = "A browser-capable connector is available."
    elif expected_tools:
        strategy = "api_tool"
        reason = "Task declares expected tools even though matching tool records are not ready yet."
    else:
        strategy = "model_agent"
        reason = "No API, knowledge, or browser-specific evidence is available yet."

    runtime_requirements = {
        "api_tool": ["connector_runtime", "network"],
        "connector_tool": ["connector_runtime"],
        "knowledge": ["knowledge", "vectorstore"],
        "browser": ["browser"],
        "model_agent": [],
    }[strategy]
    if implementation_gaps:
        execution_readiness = "implementation_required"
    elif matched_tools and all(item.get("executionReady") for item in matched_tool_payloads):
        execution_readiness = "ready"
    elif matched_tools:
        execution_readiness = "partial"
    else:
        execution_readiness = "planning_ready" if strategy == "model_agent" else "unknown"
    return {
        "strategy": strategy,
        "preferenceOrder": ["api_tool", "connector_tool", "knowledge", "browser", "model_agent"],
        "reason": reason,
        "executionReadiness": execution_readiness,
        "canExecuteEndToEnd": not implementation_gaps,
        "implementationGaps": implementation_gaps,
        "runtimeRequirements": runtime_requirements,
        "expectedTools": expected_tools,
        "matchedTools": matched_tool_payloads,
        "allowedSystems": allowed_systems,
        "availableConnectors": sorted({str(connector.get("connectorId") or "") for connector in connectors if connector.get("connectorId")}),
        "availableTools": sorted(name for name in tool_names if name),
        "evidence": evidence,
    }


def _agent_config_for_task(task: dict[str, Any], benchmark: dict[str, Any] | None = None) -> dict[str, Any]:
    benchmark = benchmark or {}
    return {
        "agentId": task.get("agentId") or benchmark.get("agentId") or "",
        "companyId": task.get("companyId") or benchmark.get("companyId") or "",
        "email": task.get("email") or benchmark.get("email") or "",
        "name": benchmark.get("agentName") or "Company Task Harvester",
        "websiteUrl": benchmark.get("websiteUrl") or "",
        "runtimeKind": "model_agent",
        "runtimeProfile": {"kind": "model_agent"},
        "runtimeType": "task_harvester",
        "runtimeCapabilities": {"browser": True, "apiCalls": True, "knowledge": True, "humanApprovalForWrites": True},
        "runtimeSpec": {
            "browserEnabled": True,
            "browserMode": "headless",
            "tools": {"browser": True, "connectors": True, "skills": True, "knowledge": True},
            "approvalRequiredFor": ["write", "send"],
        },
    }


async def harvest_task(task_id: str, *, harvester_name: str = "") -> dict[str, Any]:
    task = await benchmark_tasks_collection.find_one({"taskId": task_id}, {"_id": 0})
    if not task:
        raise ValueError("Benchmark task not found")
    agent_config = {}
    agent_id = str(task.get("agentId") or "")
    if agent_id:
        agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0}) or {}
    benchmark = await benchmarks_collection.find_one({"benchmarkId": task.get("benchmarkId", "")}, {"_id": 0}) or {}
    if not agent_config:
        agent_config = _agent_config_for_task(task, benchmark)
    strategy = await plan_task_strategy(task, agent_config=agent_config)
    task = {
        **task,
        "metadata": {
            **_metadata(task),
            "taskHarvesterStrategy": strategy,
        },
    }
    await benchmark_tasks_collection.update_one(
        {"taskId": task_id},
        {"$set": {"harvesterStrategy": strategy, "metadata.taskHarvesterStrategy": strategy}},
    )
    if not strategy.get("canExecuteEndToEnd", True):
        await benchmark_tasks_collection.update_one(
            {"taskId": task_id},
            {
                "$set": {
                    "status": "implementation_required",
                    "trajectoryId": "",
                    "implementationGaps": strategy.get("implementationGaps") or [],
                }
            },
        )
        return {
            "taskId": task_id,
            "benchmarkId": task.get("benchmarkId", ""),
            "trajectoryId": "",
            "status": "implementation_required",
            "summary": "Task cannot be harvested end to end until required connector executors are implemented.",
            "strategy": strategy,
            "implementationGaps": strategy.get("implementationGaps") or [],
        }
    await benchmark_tasks_collection.update_one(
        {"taskId": task_id},
        {
            "$set": {
                "implementationGaps": [],
                "trajectoryId": "",
            }
        },
    )
    agent_config = {
        **agent_config,
        "taskHarvesterStrategy": strategy,
        "runtimeSpec": {
            **(agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}),
            "taskStrategy": strategy["strategy"],
        },
    }
    result = await get_agent_harvester(harvester_name or None).harvest_task(agent_config, HarvestTask(task))
    return {"taskId": task_id, "benchmarkId": task.get("benchmarkId", ""), "strategy": strategy, **result}


async def harvest_benchmark_tasks(
    benchmark_id: str,
    *,
    harvester_name: str = "",
    task_ids: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "benchmarkId": benchmark_id,
        "status": {"$in": ["needs_harvest", "draft", "harvester_pending", "harvest_failed", "implementation_required"]},
    }
    if task_ids:
        query["taskId"] = {"$in": task_ids}
    cursor = benchmark_tasks_collection.find(query, {"_id": 0}).sort("createdAt", 1)
    tasks = await cursor.to_list(length=max(1, int(limit or 25)))
    results = []
    for task in tasks:
        results.append(await harvest_task(str(task.get("taskId") or ""), harvester_name=harvester_name))
    return {
        "benchmarkId": benchmark_id,
        "count": len(results),
        "results": results,
        "harvestedCount": sum(1 for item in results if item.get("status") in {"harvested", "approved"}),
        "failedCount": sum(1 for item in results if item.get("status") == "harvest_failed"),
        "implementationRequiredCount": sum(1 for item in results if item.get("status") == "implementation_required"),
        "harvested": sum(1 for item in results if item.get("status") in {"harvested", "approved"}),
        "failed": sum(1 for item in results if item.get("status") == "harvest_failed"),
    }


async def judge_and_promote_benchmark_trajectories(
    benchmark_id: str,
    *,
    task_ids: list[str] | None = None,
    judge_name: str = "rules",
    min_confidence: float = 0.75,
    limit: int = 50,
) -> dict[str, Any]:
    query: dict[str, Any] = {"benchmarkId": benchmark_id, "status": "harvested"}
    if task_ids:
        query["taskId"] = {"$in": task_ids}
    cursor = trajectories_collection.find(query, {"_id": 0}).sort("updatedAt", -1)
    trajectories = await cursor.to_list(length=max(1, int(limit or 50)))
    judge = get_trajectory_judge(judge_name or "rules")
    results = []
    promoted = 0
    pending_review = 0
    for trajectory in trajectories:
        agent_config = {}
        agent_id = str(trajectory.get("agentId") or "")
        if agent_id:
            agent_config = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0}) or {}
        judgement = await judge.judge(build_trajectory_judge_context(trajectory=trajectory, agent_config=agent_config))
        confidence = float(judgement.get("confidence") or 0)
        passed = judgement.get("label") == "pass" and confidence >= min_confidence
        capability_id = ""
        if passed:
            capability_id = await approve_trajectory_as_skill(trajectory, judge=judgement)
            promoted += 1
        else:
            pending_review += 1
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory.get("trajectoryId")},
            {
                "$set": {
                    "judge": judgement,
                    "needsHumanReview": not passed,
                    "status": "approved" if passed else "review_required",
                    "capabilityId": capability_id,
                    "updatedAt": judgement.get("updatedAt") or trajectory.get("updatedAt"),
                }
            },
        )
        results.append(
            {
                "trajectoryId": trajectory.get("trajectoryId", ""),
                "taskId": trajectory.get("taskId", ""),
                "label": judgement.get("label", ""),
                "confidence": confidence,
                "promoted": passed,
                "capabilityId": capability_id,
            }
        )
    return {
        "benchmarkId": benchmark_id,
        "count": len(results),
        "promoted": promoted,
        "pendingReview": pending_review,
        "results": results,
        "judge": judge_name or "rules",
    }
