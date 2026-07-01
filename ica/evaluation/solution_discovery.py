from __future__ import annotations

from typing import Any

from ica.evaluation.task_discovery import _selected_project_tasks
from ica.schemas import (
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaSolutionDiscoveryEvaluation,
    IcaTaskSolutionSpec,
)


def _solution_expected_tasks(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[Any]:
    return _selected_project_tasks(project, mode)


def _tool_names(snapshot: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(tool.get("name") or "") for tool in snapshot.get("tools", []) if tool.get("name")}


def _connector_types(snapshot: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(connector.get("type") or "") for connector in snapshot.get("connectors", []) if connector.get("type")}


def _connectors_by_type(snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for connector in snapshot.get("connectors", []):
        connector_type = str(connector.get("type") or "")
        if connector_type:
            grouped.setdefault(connector_type, []).append(connector)
    return grouped


def _tools_by_name(snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {str(tool.get("name") or ""): tool for tool in snapshot.get("tools", []) if tool.get("name")}


def _valid_origin(item: dict[str, Any], *, kind: str) -> tuple[bool, str]:
    origin = str(item.get("origin") or "unknown")
    if origin in {"existing", "existing_connector_tool"}:
        return True, ""
    if origin in {"derived_from_openapi", "derived_from_code"}:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        return (True, "") if evidence else (False, f"{kind}:{item.get('name') or item.get('connectorId') or item.get('toolId')}:missing_evidence")
    if origin == "proposed_custom":
        code_key = "customConnectorCode" if kind == "connector" else "customToolCode"
        custom_code = item.get(code_key)
        if isinstance(custom_code, dict) and custom_code:
            return True, ""
        return False, f"{kind}:{item.get('name') or item.get('connectorId') or item.get('toolId')}:missing_custom_code"
    return False, f"{kind}:{item.get('name') or item.get('connectorId') or item.get('toolId')}:unknown_origin"


def _expected_solution_for(project: IcaDemoProject, task_id: str) -> IcaTaskSolutionSpec | None:
    for solution in project.expectedSolutions:
        if solution.taskId == task_id:
            return solution
    return None


def _default_solution_for_task(project: IcaDemoProject, task: Any, snapshot: dict[str, list[dict[str, Any]]]) -> IcaTaskSolutionSpec:
    surfaces = set(task.expectedSurfaces)
    connectors = []
    if "api" in surfaces:
        connectors.append("api")
    if "web" in surfaces:
        connectors.append("web")
    if "documents" in surfaces:
        connectors.append("knowledge")
    if "code" in surfaces:
        connectors.append("code")
    available_tools = sorted(_tool_names(snapshot))
    tools = []
    if "documents" in surfaces and "knowledge.company_docs.search" in available_tools:
        tools.append("knowledge.company_docs.search")
    if "web" in surfaces:
        tools.extend(name for name in available_tools if ".web." in name or name.endswith(".explore_workflows"))
    if "api" in surfaces:
        tools.extend(name for name in available_tools if ".api." in name)
    if "code" in surfaces:
        tools.extend(name for name in available_tools if ".code." in name)
    tools = sorted(dict.fromkeys(tools))
    trajectory_id = f"{project.projectId}:{task.taskId}:expected_trajectory"
    return IcaTaskSolutionSpec(
        taskId=task.taskId,
        connectors=connectors,
        tools=tools,
        trajectories=[
            {
                "trajectoryId": trajectory_id,
                "description": f"Use {', '.join(connectors) or 'available'} surfaces to solve {task.name}.",
                "toolCalls": [{"toolName": name, "arguments": {}} for name in tools[:4]],
                "source": "generated",
            }
        ],
        skills=[
            {
                "skillId": f"{project.projectId}:{task.taskId}:skill",
                "name": f"{task.name} skill",
                "description": task.successCriteria,
                "trajectoryIds": [trajectory_id],
                "instructions": task.prompt,
                "source": "hybrid",
            }
        ],
        agentProvider={
            "runtimeKind": "model_agent",
            "provider": "openai",
            "model": "",
            "systemPrompt": f"You are the {project.name} task agent. Solve: {task.prompt}",
        },
    )


def propose_task_solutions(
    *,
    project: IcaDemoProject,
    snapshot: dict[str, list[dict[str, Any]]],
    mode: IcaBenchmarkModeKind | None = None,
) -> list[IcaTaskSolutionSpec]:
    expected_ids = {task.taskId for task in _solution_expected_tasks(project, mode)}
    if project.expectedSolutions:
        return [solution for solution in project.expectedSolutions if not expected_ids or solution.taskId in expected_ids]
    solutions: list[IcaTaskSolutionSpec] = []
    for task in _solution_expected_tasks(project, mode):
        solutions.append(_default_solution_for_task(project, task, snapshot))
    return [solution for solution in solutions if not expected_ids or solution.taskId in expected_ids]


def _normalize_solution_task_id(project: IcaDemoProject, raw_task_id: str) -> str:
    raw = str(raw_task_id or "")
    if project.metadata.get("category") == "only_web" and any(task.taskId == "primary_web_workflow" for task in project.tasks):
        return "primary_web_workflow"
    for task in project.tasks:
        if raw == task.taskId or raw.endswith(f":{task.taskId}") or task.taskId in raw:
            return task.taskId
    return raw


def _solutions_from_company_harvester_output(project: IcaDemoProject, output: dict[str, Any]) -> list[IcaTaskSolutionSpec]:
    raw_solutions = output.get("taskSolutions") if isinstance(output, dict) else []
    if not isinstance(raw_solutions, list):
        return []
    solutions: list[IcaTaskSolutionSpec] = []
    for raw in raw_solutions:
        if not isinstance(raw, dict):
            continue
        connectors = [
            str(connector.get("type") or connector.get("surface") or connector.get("name") or "")
            for connector in raw.get("connectors") or []
            if isinstance(connector, dict)
        ]
        connectors = ["knowledge" if item == "documents" else item for item in connectors if item]
        tools = [
            str(tool.get("name") or tool.get("toolId") or "")
            for tool in raw.get("tools") or []
            if isinstance(tool, dict) and (tool.get("name") or tool.get("toolId"))
        ]
        solution = IcaTaskSolutionSpec(
            taskId=_normalize_solution_task_id(project, str(raw.get("taskId") or "")),
            connectors=sorted(dict.fromkeys(connectors)),
            tools=sorted(dict.fromkeys(tools)),
            trajectories=raw.get("trajectories") if isinstance(raw.get("trajectories"), list) else [],
            skills=raw.get("skills") if isinstance(raw.get("skills"), list) else [],
            agentProvider=raw.get("agentProvider") if isinstance(raw.get("agentProvider"), dict) else {},
            metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
        )
        solutions.append(solution)
    return solutions


def evaluate_solution_discovery(
    *,
    project: IcaDemoProject,
    solutions: list[IcaTaskSolutionSpec],
    snapshot: dict[str, list[dict[str, Any]]],
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaSolutionDiscoveryEvaluation:
    expected_tasks = _solution_expected_tasks(project, mode)
    expected_task_ids = [task.taskId for task in expected_tasks]
    by_task = {solution.taskId: solution for solution in solutions}
    extra_solution_task_ids = sorted(set(by_task) - set(expected_task_ids))
    available_connectors = _connector_types(snapshot)
    connectors_by_type = _connectors_by_type(snapshot)
    tools_by_name = _tools_by_name(snapshot)
    missing: list[str] = []
    incomplete: list[str] = []
    invalid_origins: list[str] = []
    hallucinated_tools: list[str] = []
    hallucinated_connectors: list[str] = []
    incomplete_reasons: dict[str, list[str]] = {}

    for task in expected_tasks:
        solution = by_task.get(task.taskId)
        if not solution:
            missing.append(task.taskId)
            continue
        expected_solution = _expected_solution_for(project, task.taskId)
        required_connectors = {
            "api" if surface == "api" else "web" if surface == "web" else "knowledge" if surface == "documents" else "code"
            for surface in task.expectedSurfaces
            if surface in {"api", "web", "documents", "code"}
        }
        if expected_solution:
            required_connectors |= set(expected_solution.connectors)
        has_connector_plan = required_connectors <= set(solution.connectors)
        has_available_connectors = required_connectors <= available_connectors
        task_reasons: list[str] = []
        if not has_connector_plan:
            task_reasons.append("missing_connector_plan")
        if not has_available_connectors:
            task_reasons.append("missing_available_connector")
        for connector_type in required_connectors:
            candidate_connectors = connectors_by_type.get(connector_type) or []
            if not candidate_connectors:
                hallucinated_connectors.append(f"{task.taskId}:{connector_type}")
                continue
            if not any(_valid_origin(connector, kind="connector")[0] for connector in candidate_connectors):
                reason = _valid_origin(candidate_connectors[0], kind="connector")[1]
                invalid_origins.append(reason)
                task_reasons.append(reason)
        required_tools = set(expected_solution.tools if expected_solution else [])
        has_tools = bool(solution.tools) and (not required_tools or bool(required_tools & set(solution.tools)))
        if not has_tools:
            task_reasons.append("missing_tools")
        for tool_name in solution.tools:
            tool_doc = tools_by_name.get(tool_name)
            if not tool_doc:
                hallucinated_tools.append(tool_name)
                task_reasons.append(f"tool:{tool_name}:not_in_snapshot")
                continue
            valid, reason = _valid_origin(tool_doc, kind="tool")
            if not valid:
                invalid_origins.append(reason)
                task_reasons.append(reason)
        has_trajectory = bool(solution.trajectories)
        has_skill = bool(solution.skills)
        has_agent = bool(solution.agentProvider.runtimeKind)
        if not has_trajectory:
            task_reasons.append("missing_trajectory")
        if not has_skill:
            task_reasons.append("missing_skill")
        if not has_agent:
            task_reasons.append("missing_agent_provider")
        if not (has_connector_plan and has_available_connectors and has_tools and has_trajectory and has_skill and has_agent and not task_reasons):
            incomplete.append(task.taskId)
            incomplete_reasons[task.taskId] = sorted(set(task_reasons))

    passed_count = len(expected_task_ids) - len(missing) - len(incomplete)
    score = round(passed_count / len(expected_task_ids), 4) if expected_task_ids else 1.0
    return IcaSolutionDiscoveryEvaluation(
        projectId=project.projectId,
        mode=mode,
        passed=not missing and not incomplete,
        score=score,
        expectedTaskCount=len(expected_task_ids),
        solutionCount=len([solution for solution in solutions if solution.taskId in set(expected_task_ids)]),
        extraSolutionTaskIds=extra_solution_task_ids,
        missingTaskIds=missing,
        incompleteTaskIds=incomplete,
        invalidOriginIds=sorted(set(invalid_origins)),
        hallucinatedToolNames=sorted(set(hallucinated_tools)),
        hallucinatedConnectorIds=sorted(set(hallucinated_connectors)),
        incompleteReasons=incomplete_reasons,
        solutions=solutions,
    )
