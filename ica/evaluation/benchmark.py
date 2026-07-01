from __future__ import annotations

from typing import Any

from app.services import company_harvester
from ica.company_harvesters.runners import CompanyHarvesterIcaRunner, IcaCompanyHarvestRunner
from ica.demo_companies.materializer import materialize_project
from ica.evaluation.agent_execution import evaluate_agent_execution
from ica.evaluation.inventory import evaluate_company_harvest_snapshot
from ica.evaluation.solution_discovery import (
    _solutions_from_company_harvester_output,
    evaluate_solution_discovery,
)
from ica.evaluation.task_discovery import evaluate_task_discovery
from ica.schemas import IcaBenchmarkModeKind, IcaCompanyBenchmarkResult, IcaDemoProject, IcaExpectedHarvest


async def evaluate_project_company_harvest(
    project: IcaDemoProject,
    *,
    email: str,
    company_id: str,
    base_url: str = "",
    mode: IcaBenchmarkModeKind | None = None,
    process: bool = True,
    runner: IcaCompanyHarvestRunner | None = None,
) -> IcaCompanyBenchmarkResult:
    runner = runner or CompanyHarvesterIcaRunner()
    result = await runner.run(
        project,
        email=email,
        company_id=company_id,
        base_url=base_url,
        mode=mode,
        process=process,
        include_ground_truth_tasks=False,
    )
    expected = IcaExpectedHarvest.model_validate(result.get("expectedHarvest") or project.expectedHarvest.model_dump())
    inventory = evaluate_company_harvest_snapshot(
        project=project,
        snapshot=result.get("snapshot") or {},
        expected_harvest=expected,
        run=result.get("run") or {},
        mode=mode,
    )
    snapshot = result.get("snapshot") or {}
    task_discovery = evaluate_task_discovery(project=project, discovered_tasks=snapshot.get("tasks") or [], mode=mode)
    output_solutions = _solutions_from_company_harvester_output(project, result.get("companyHarvesterOutput") or {})
    solutions = output_solutions
    solution_discovery = evaluate_solution_discovery(project=project, solutions=solutions, snapshot=snapshot, mode=mode)
    agent_execution = evaluate_agent_execution(
        project=project,
        solutions=solutions,
        email=email,
        company_id=company_id,
        mode=mode,
    )
    if agent_execution.applicable:
        score = round((task_discovery.score * 0.25) + (solution_discovery.score * 0.25) + (inventory.score * 0.10) + (agent_execution.score * 0.40), 4)
        passed = task_discovery.passed and solution_discovery.passed and inventory.passed and agent_execution.passed
    else:
        score = round((task_discovery.score * 0.45) + (solution_discovery.score * 0.45) + (inventory.score * 0.10), 4)
        passed = task_discovery.passed and solution_discovery.passed and inventory.passed
    return IcaCompanyBenchmarkResult(
        projectId=project.projectId,
        mode=mode,
        passed=passed,
        score=score,
        phases={
            "taskDiscovery": task_discovery.model_dump(),
            "solutionDiscovery": solution_discovery.model_dump(),
            "agentExecution": agent_execution.model_dump(),
            "inventory": inventory.model_dump(),
        },
    )


async def seed_company_harvester_from_project(
    project: IcaDemoProject,
    *,
    email: str,
    company_id: str,
    base_url: str = "",
    mode: IcaBenchmarkModeKind | None = None,
    process: bool = True,
) -> dict[str, Any]:
    materialized = materialize_project(project, base_url=base_url, mode=mode)
    intake = await company_harvester.create_company_intake(
        email=email,
        company_id=company_id,
        company_name=project.name,
        description=project.description,
        materials=materialized.materials,
        user_tasks=materialized.userTasks,
        mode="dev",
    )
    run = await company_harvester.start_company_harvest(intake["intakeId"], email=email, mode="dev")
    if process:
        run = await company_harvester.process_company_harvest_run(run["runId"])
    return {"project": project.model_dump(), "intake": intake, "run": run, "expectedHarvest": project.expectedHarvest.model_dump()}
