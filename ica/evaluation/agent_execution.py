from __future__ import annotations

from typing import Any

from app.models.agent_config import AgentCallable, AgentConfig, AgentTask
from app.runtimes.base import AgentRuntimeProfile
from ica.evaluation.task_discovery import _selected_project_tasks
from ica.execution.demo_company_executors import get_demo_company_executor
from ica.schemas import (
    IcaAgentExecutionEvaluation,
    IcaAgentExecutionTaskResult,
    IcaBenchmarkModeKind,
    IcaDemoProject,
    IcaTaskSolutionSpec,
)


def _trajectory_tool_names(solution: IcaTaskSolutionSpec) -> list[str]:
    names: list[str] = []
    for trajectory in solution.trajectories:
        for call in trajectory.toolCalls:
            if isinstance(call, dict):
                name = str(call.get("toolName") or call.get("name") or call.get("tool") or "")
                if name:
                    names.append(name)
    return list(dict.fromkeys(names))


def _agent_config_summary(agent: AgentConfig) -> dict[str, Any]:
    return {
        "agentId": agent.agentId,
        "name": agent.name,
        "runtimeKind": agent.runtimeKind,
        "provider": agent.runtimeProfile.provider,
        "model": agent.runtimeProfile.model,
        "taskCount": len(agent.tasks),
        "toolCount": len(agent.tools),
        "skillCount": len(agent.skills),
        "toolNames": [tool.name for tool in agent.tools],
        "skillNames": [skill.name for skill in agent.skills],
        "capabilityDiscovery": agent.capabilityDiscovery,
    }


def validate_built_agent_config(*, agent: AgentConfig, solution: IcaTaskSolutionSpec) -> list[str]:
    errors: list[str] = []
    if not agent.agentId:
        errors.append("missing_agent_id")
    if not agent.tasks:
        errors.append("missing_task_prompt")
    if not agent.runtimeKind:
        errors.append("missing_runtime_kind")
    if agent.runtimeKind != solution.agentProvider.runtimeKind:
        errors.append("runtime_kind_mismatch")
    if not (agent.tools or agent.skills):
        errors.append("missing_tools_or_skills")

    agent_tool_names = {tool.name for tool in agent.tools}
    missing_tools = sorted(set(solution.tools) - agent_tool_names)
    if missing_tools:
        errors.extend(f"missing_agent_tool:{name}" for name in missing_tools)

    solution_skill_names = {skill.name for skill in solution.skills}
    agent_skill_names = {skill.name for skill in agent.skills}
    missing_skills = sorted(solution_skill_names - agent_skill_names)
    if missing_skills:
        errors.extend(f"missing_agent_skill:{name}" for name in missing_skills)

    trajectory_tool_names = _trajectory_tool_names(solution)
    if not trajectory_tool_names:
        errors.append("missing_trajectory_tool_calls")
    if solution.tools:
        orphan_calls = sorted(set(trajectory_tool_names) - set(solution.tools))
        if orphan_calls:
            errors.extend(f"trajectory_tool_not_declared:{name}" for name in orphan_calls)
    return errors


def build_agent_config_from_solution(
    *,
    project: IcaDemoProject,
    task: dict[str, Any],
    solution: IcaTaskSolutionSpec,
    email: str = "",
    company_id: str = "",
) -> AgentConfig:
    provider = solution.agentProvider
    tool_callables = [
        AgentCallable(
            name=tool_name,
            description=f"Tool required for {task.get('name') or solution.taskId}.",
            kind="tool",
            source="ica_solution",
            connectorId=next((connector for connector in solution.connectors if connector in tool_name), ""),
            executionReady=True,
        )
        for tool_name in solution.tools
    ]
    skill_callables = [
        AgentCallable(
            name=skill.name,
            description=skill.description or skill.instructions,
            kind="skill",
            source="ica_solution",
            capabilityId=skill.skillId,
            trajectoryIds=skill.trajectoryIds,
            executionReady=True,
        )
        for skill in solution.skills
    ]
    return AgentConfig(
        agentId=f"{project.projectId}:{solution.taskId}:{provider.runtimeKind}",
        name=f"{project.name} - {task.get('name') or solution.taskId}",
        email=email,
        companyId=company_id,
        runtimeKind=provider.runtimeKind,
        runtimeProfile=AgentRuntimeProfile(
            kind=provider.runtimeKind,
            provider=provider.provider,
            model=provider.model,
            systemPrompt=provider.systemPrompt,
        ),
        status="draft",
        tasks=[
            AgentTask(
                name=str(task.get("name") or solution.taskId),
                prompt=str(task.get("prompt") or ""),
                successCriteria=str(task.get("successCriteria") or ""),
            )
        ],
        tools=tool_callables,
        skills=skill_callables,
        capabilityDiscovery={
            "mode": "ica_task_solution",
            "icaProjectId": project.projectId,
            "icaTaskId": solution.taskId,
            "connectors": solution.connectors,
            "trajectoryIds": [trajectory.trajectoryId for trajectory in solution.trajectories],
        },
    )


def _execution_tests_for(project: IcaDemoProject, mode: IcaBenchmarkModeKind | None = None) -> list[Any]:
    return [task for task in _selected_project_tasks(project, mode) if isinstance(task.metadata.get("executionTest"), dict)]


def evaluate_agent_execution(
    *,
    project: IcaDemoProject,
    solutions: list[IcaTaskSolutionSpec],
    email: str = "",
    company_id: str = "",
    mode: IcaBenchmarkModeKind | None = None,
) -> IcaAgentExecutionEvaluation:
    execution_tasks = _execution_tests_for(project, mode)
    if not execution_tasks:
        return IcaAgentExecutionEvaluation(projectId=project.projectId, mode=mode, applicable=False, skippedReason="no_execution_tests")

    executor = get_demo_company_executor(project.projectId)
    if executor is None:
        return IcaAgentExecutionEvaluation(
            projectId=project.projectId,
            mode=mode,
            applicable=False,
            skippedReason="no_demo_executor",
            expectedTaskCount=len(execution_tasks),
        )

    by_task = {solution.taskId: solution for solution in solutions}
    results: list[IcaAgentExecutionTaskResult] = []
    for task in execution_tasks:
        solution = by_task.get(task.taskId)
        if not solution:
            results.append(
                IcaAgentExecutionTaskResult(
                    taskId=task.taskId,
                    passed=False,
                    score=0.0,
                    buildPassed=False,
                    buildErrors=["missing_solution"],
                    error="missing_solution",
                )
            )
            continue
        agent = build_agent_config_from_solution(
            project=project,
            task=task.model_dump(mode="json"),
            solution=solution,
            email=email,
            company_id=company_id,
        )
        build_errors = validate_built_agent_config(agent=agent, solution=solution)
        if build_errors:
            results.append(
                IcaAgentExecutionTaskResult(
                    taskId=task.taskId,
                    passed=False,
                    score=0.0,
                    agentId=agent.agentId,
                    buildPassed=False,
                    buildErrors=build_errors,
                    agentConfigSummary=_agent_config_summary(agent),
                    executedTools=_trajectory_tool_names(solution),
                    assertions=[
                        {
                            "label": "agent config build",
                            "passed": False,
                            "expected": "valid executable AgentConfig",
                            "actual": build_errors,
                        }
                    ],
                    error="agent_build_failed",
                )
            )
            continue
        task_result = executor.run_task(task=task, solution=solution, agent=agent)
        task_result.buildPassed = True
        task_result.buildErrors = []
        task_result.agentConfigSummary = _agent_config_summary(agent)
        results.append(task_result)

    passed_ids = [result.taskId for result in results if result.passed]
    failed_ids = [result.taskId for result in results if not result.passed]
    score = round(sum(result.score for result in results) / len(results), 4) if results else 1.0
    return IcaAgentExecutionEvaluation(
        projectId=project.projectId,
        mode=mode,
        applicable=True,
        executionMode="trajectory_replay_harness",
        runtimeExecuted=False,
        passed=not failed_ids,
        score=score,
        expectedTaskCount=len(execution_tasks),
        executedTaskCount=len(results),
        passedTaskIds=passed_ids,
        failedTaskIds=failed_ids,
        results=results,
    )
