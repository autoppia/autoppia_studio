from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.services.agent_builder import build_company_agents
from app.services.queue import enqueue_job
from app.services.company_harvester import answer_company_harvest_questions, create_company_intake, company_harvest_status, start_company_harvest
from app.services.task_harvester import harvest_benchmark_tasks, harvest_task, judge_and_promote_benchmark_trajectories, task_harvest_has_implementation_gaps

router = APIRouter()


class CompanyIntakeCreateRequest(BaseModel):
    email: str
    companyId: str
    companyName: str = ""
    description: str = ""
    materials: list[dict[str, Any]] = Field(default_factory=list)
    userTasks: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["normal", "dev"] = "normal"
    startHarvest: bool = False
    autoSolveTasks: bool = False
    autoPromoteSkills: bool = False
    buildAgents: bool = False
    runtimeKinds: list[str] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    runtimeProfiles: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CompanyHarvestStartRequest(BaseModel):
    mode: Literal["normal", "dev"] | None = None
    autoSolveTasks: bool = False
    autoPromoteSkills: bool = False
    buildAgents: bool = False
    runtimeKinds: list[str] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    runtimeProfiles: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CompanyHarvestAnswerRequest(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)
    continueHarvest: bool = False
    autoSolveTasks: bool = False
    autoPromoteSkills: bool = False
    buildAgents: bool = False
    runtimeKinds: list[str] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    runtimeProfiles: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TaskHarvestRequest(BaseModel):
    email: str = ""
    benchmarkId: str = ""
    taskId: str = ""
    taskIds: list[str] = Field(default_factory=list)
    harvesterName: str = ""
    judgeName: str = "rules"
    limit: int = 25
    inline: bool = False
    promoteSkills: bool = False
    buildAgents: bool = False
    companyId: str = ""
    companyName: str = ""
    runtimeKinds: list[str] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    runtimeProfiles: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentBuildRequest(BaseModel):
    email: str
    companyId: str
    companyName: str = ""
    benchmarkId: str = ""
    runtimeKinds: list[str] = Field(default_factory=lambda: ["model_agent", "codex", "claude_code"])
    runtimeProfiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    inline: bool = False


@router.post("/company-intakes")
async def create_intake(body: CompanyIntakeCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    if not body.companyId.strip():
        raise HTTPException(status_code=400, detail="companyId is required")
    intake = await create_company_intake(
        email=email,
        company_id=body.companyId,
        company_name=body.companyName,
        description=body.description,
        materials=body.materials,
        user_tasks=body.userTasks,
        mode=body.mode,
    )
    response: dict[str, Any] = {"success": True, "intake": intake}
    if body.startHarvest:
        harvest_run = await start_company_harvest(str(intake["intakeId"]), mode=body.mode, email=email)
        response["harvestRun"] = harvest_run
        payload = {
            "runId": harvest_run["runId"],
            "intakeId": intake["intakeId"],
            "companyId": body.companyId,
            "companyName": body.companyName,
            "autoSolveTasks": body.autoSolveTasks,
            "autoPromoteSkills": body.autoPromoteSkills,
            "buildAgents": body.buildAgents,
            "runtimeKinds": body.runtimeKinds,
            "runtimeProfiles": body.runtimeProfiles,
        }
        response["job"] = await enqueue_job(
            "company_harvest",
            payload,
            dedupe_key=f"company_harvest:{harvest_run['runId']}",
            max_attempts=1,
        )
    return response


@router.post("/company-intakes/{intake_id}/harvest-runs")
async def start_harvest_run(intake_id: str, body: CompanyHarvestStartRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    try:
        harvest_run = await start_company_harvest(intake_id, mode=body.mode or "", email=scope.email)
        job = await enqueue_job(
            "company_harvest",
            {
                "runId": harvest_run["runId"],
                "intakeId": intake_id,
                "companyId": harvest_run.get("companyId", ""),
                "autoSolveTasks": body.autoSolveTasks,
                "autoPromoteSkills": body.autoPromoteSkills,
                "buildAgents": body.buildAgents,
                "runtimeKinds": body.runtimeKinds,
                "runtimeProfiles": body.runtimeProfiles,
            },
            dedupe_key=f"company_harvest:{harvest_run['runId']}",
            max_attempts=1,
        )
        return {"success": True, "harvestRun": harvest_run, "job": job}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/company-harvest-runs/{run_id}/answers")
async def answer_harvest_questions(run_id: str, body: CompanyHarvestAnswerRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    if not body.answers:
        raise HTTPException(status_code=400, detail="answers are required")
    try:
        harvest_run = await answer_company_harvest_questions(run_id, answers=body.answers, email=scope.email)
        response: dict[str, Any] = {"success": True, "harvestRun": harvest_run}
        if body.continueHarvest and harvest_run.get("status") != "needs_user_input":
            response["job"] = await enqueue_job(
                "company_harvest",
                {
                    "runId": harvest_run["runId"],
                    "intakeId": harvest_run["intakeId"],
                    "companyId": harvest_run.get("companyId", ""),
                    "autoSolveTasks": body.autoSolveTasks,
                    "autoPromoteSkills": body.autoPromoteSkills,
                    "buildAgents": body.buildAgents,
                    "runtimeKinds": body.runtimeKinds,
                    "runtimeProfiles": body.runtimeProfiles,
                },
                dedupe_key=f"company_harvest:{harvest_run['runId']}:resume:{harvest_run.get('updatedAt', '')}",
                max_attempts=1,
            )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/task-harvest-runs")
async def start_task_harvest(body: TaskHarvestRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    build_email = scope.require_email(body.email) if body.buildAgents else (scope.email or body.email)
    if body.inline:
        try:
            if body.taskId:
                harvest = await harvest_task(body.taskId, harvester_name=body.harvesterName)
                response = {"success": True, "result": harvest}
                if body.promoteSkills:
                    benchmark_id = str(harvest.get("benchmarkId") or body.benchmarkId or "")
                    if task_harvest_has_implementation_gaps(harvest):
                        response["blockedActions"] = [
                            {
                                "kind": "promote_or_build_agents",
                                "reason": "task_harvest_requires_connector_implementation",
                                "benchmarkId": benchmark_id,
                            }
                        ]
                        return response
                    promotion = await judge_and_promote_benchmark_trajectories(
                        benchmark_id,
                        task_ids=[body.taskId],
                        judge_name=body.judgeName,
                        limit=body.limit,
                    )
                    response["promotion"] = promotion
                    if body.buildAgents:
                        response["agentBuild"] = await build_company_agents(
                            email=build_email,
                            company_id=body.companyId or str(harvest.get("companyId") or ""),
                            company_name=body.companyName,
                            benchmark_id=benchmark_id,
                            runtime_kinds=body.runtimeKinds,
                            runtime_profiles=body.runtimeProfiles,
                        )
                return response
            if not body.benchmarkId:
                raise HTTPException(status_code=400, detail="benchmarkId or taskId is required")
            harvest = await harvest_benchmark_tasks(
                body.benchmarkId,
                harvester_name=body.harvesterName,
                task_ids=body.taskIds or None,
                limit=body.limit,
            )
            response = {
                "success": True,
                "result": harvest,
            }
            if body.promoteSkills:
                if task_harvest_has_implementation_gaps(harvest):
                    response["blockedActions"] = [
                        {
                            "kind": "promote_or_build_agents",
                            "reason": "task_harvest_requires_connector_implementation",
                            "benchmarkId": body.benchmarkId,
                        }
                    ]
                    return response
                promotion = await judge_and_promote_benchmark_trajectories(
                    body.benchmarkId,
                    task_ids=body.taskIds or None,
                    judge_name=body.judgeName,
                    limit=body.limit,
                )
                response["promotion"] = promotion
                if body.buildAgents:
                    response["agentBuild"] = await build_company_agents(
                        email=build_email,
                        company_id=body.companyId,
                        company_name=body.companyName,
                        benchmark_id=body.benchmarkId,
                        runtime_kinds=body.runtimeKinds,
                        runtime_profiles=body.runtimeProfiles,
                    )
            return response
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not body.taskId and not body.benchmarkId:
        raise HTTPException(status_code=400, detail="benchmarkId or taskId is required")
    job = await enqueue_job(
        "task_harvest",
        {
            "benchmarkId": body.benchmarkId,
            "taskId": body.taskId,
            "taskIds": body.taskIds,
            "harvesterName": body.harvesterName,
            "judgeName": body.judgeName,
            "limit": body.limit,
            "promoteSkills": body.promoteSkills,
            "buildAgents": body.buildAgents,
            "email": build_email,
            "companyId": body.companyId,
            "companyName": body.companyName,
            "runtimeKinds": body.runtimeKinds,
            "runtimeProfiles": body.runtimeProfiles,
        },
        dedupe_key=f"task_harvest:{body.taskId or body.benchmarkId}:{','.join(body.taskIds)}",
        max_attempts=1,
    )
    return {"success": True, "job": job}


@router.post("/company-agent-builds")
async def start_company_agent_build(body: AgentBuildRequest, scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    email = scope.require_email(body.email)
    if not body.companyId.strip():
        raise HTTPException(status_code=400, detail="companyId is required")
    if body.inline:
        return {
            "success": True,
            "result": await build_company_agents(
                email=email,
                company_id=body.companyId,
                company_name=body.companyName,
                benchmark_id=body.benchmarkId,
                runtime_kinds=body.runtimeKinds,
                runtime_profiles=body.runtimeProfiles,
            ),
        }
    job = await enqueue_job(
        "agent_build",
        {
            "email": email,
            "companyId": body.companyId,
            "companyName": body.companyName,
            "benchmarkId": body.benchmarkId,
            "runtimeKinds": body.runtimeKinds,
            "runtimeProfiles": body.runtimeProfiles,
        },
        dedupe_key=f"agent_build:{body.companyId}:{body.benchmarkId}:{','.join(body.runtimeKinds)}",
        max_attempts=1,
    )
    return {"success": True, "job": job}


@router.get("/company-harvest-runs/{run_id}/status")
async def get_harvest_status(run_id: str, mode: Literal["normal", "dev"] = "normal", scope: RequestScope = Depends(get_request_scope)):
    scope = coerce_request_scope(scope)
    try:
        return {"status": await company_harvest_status(run_id, mode=mode, email=scope.email)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
