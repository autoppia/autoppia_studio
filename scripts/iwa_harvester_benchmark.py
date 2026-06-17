#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
IWA_ROOT = Path(os.getenv("AUTOMATA_IWA_ROOT", "/home/usuario1/daryxx/autoppia/operator/autoppia_iwa"))

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(IWA_ROOT))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")
load_dotenv(IWA_ROOT / ".env")

from app.database import (  # noqa: E402
    agent_creation_jobs_collection,
    agent_webs_collection,
    agents_collection,
    benchmark_tasks_collection,
    benchmarks_collection,
    capabilities_collection,
    companies_collection,
    connectors_collection,
    ensure_indexes,
    harvester_runs_collection,
    tools_collection,
    trajectories_collection,
)
from app.harvesters.toolkit import ToolkitHarvester  # noqa: E402
from app.routes.agent_creation import _auto_promote_harvested_trajectories  # noqa: E402
from app.routes.onboarding import DEFAULT_OPERATOR_RUNTIME_ENDPOINT, DEFAULT_OPERATOR_RUNTIME_TYPE, DEFAULT_RUNTIME_PROXY_BASE, task_name_from_prompt  # noqa: E402
from app.services.agent_harvesters import HarvestTask, get_agent_harvester  # noqa: E402
from app.services.agent_runtime import agent_step_result  # noqa: E402


DEFAULT_EMAIL = "iwa-benchmark@autoppia.com"
DEFAULT_COMPANY = "IWA Demo Webs Benchmark"
DEFAULT_ENDPOINT = "http://84.247.180.192"
DEFAULT_STARTING_PORT = 8000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remap_url(url: str, frontend_url: str) -> str:
    src = urlsplit((url or "").strip())
    base = urlsplit(frontend_url.rstrip("/") + "/")
    if not src.scheme or not base.scheme:
        return url
    return urlunsplit((base.scheme, base.netloc, src.path, src.query, src.fragment))


def import_iwa() -> tuple[dict[str, str], Any]:
    from autoppia_iwa.src.demo_webs.project_package_registry import WEB_PROJECT_ID_TO_PACKAGE_DIR
    from autoppia_iwa.src.demo_webs.trajectory_registry import get_trajectory_map

    return WEB_PROJECT_ID_TO_PACKAGE_DIR, get_trajectory_map


def load_project(project_id: str, package: str) -> Any:
    module = importlib.import_module(f"autoppia_iwa.src.demo_webs.projects.{package}.main")
    for value in module.__dict__.values():
        if getattr(value, "id", None) == project_id:
            return value
    raise RuntimeError(f"Could not find WebProject object for {project_id}")


def build_inventory(endpoint: str, starting_port: int) -> list[dict[str, Any]]:
    registry, get_trajectory_map = import_iwa()
    rows: list[dict[str, Any]] = []
    for index, (project_id, package) in enumerate(registry.items()):
        project = load_project(project_id, package)
        frontend_url = f"{endpoint.rstrip('/')}:{starting_port + index}/"
        trajectories = get_trajectory_map(project_id) or {}
        rows.append(
            {
                "projectId": project_id,
                "package": package,
                "name": getattr(project, "name", project_id),
                "frontendUrl": frontend_url,
                "port": starting_port + index,
                "useCases": len(getattr(project, "use_cases", None) or []),
                "dataExtractionUseCases": len(getattr(project, "data_extraction_use_cases", None) or []),
                "goldenTrajectories": len(trajectories),
                "trajectoryNames": sorted(trajectories.keys()),
            }
        )
    return rows


async def check_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
        async def one(row: dict[str, Any]) -> dict[str, Any]:
            try:
                response = await client.get(row["frontendUrl"])
                return {**row, "httpStatus": response.status_code, "reachable": response.status_code < 500}
            except Exception as exc:
                return {**row, "httpStatus": 0, "reachable": False, "error": str(exc)}

        return await asyncio.gather(*(one(row) for row in rows))


def select_rows(rows: list[dict[str, Any]], projects: list[str], limit_projects: int) -> list[dict[str, Any]]:
    if projects:
        wanted = set(projects)
        rows = [row for row in rows if row["projectId"] in wanted]
    if limit_projects > 0:
        rows = rows[:limit_projects]
    return rows


async def upsert_company(email: str, name: str) -> dict[str, Any]:
    existing = await companies_collection.find_one({"email": email, "name": name}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "companyId": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "industry": "web automation benchmark",
        "description": "Automata benchmark company for IWA demo web projects.",
        "createdAt": now(),
        "updatedAt": now(),
    }
    await companies_collection.insert_one(dict(doc))
    return doc


async def upsert_web_connector(email: str, company_id: str, row: dict[str, Any]) -> dict[str, Any]:
    name = f"IWA {row['projectId']}"
    existing = await connectors_collection.find_one({"email": email, "companyId": company_id, "name": name}, {"_id": 0})
    doc = {
        "email": email,
        "companyId": company_id,
        "name": name,
        "type": "web",
        "category": "demo_web",
        "description": f"IWA demo web connector for {row['projectId']}.",
        "status": "connected" if row.get("reachable") else "not_connected",
        "config": {
            "baseUrl": row["frontendUrl"],
            "startUrl": row["frontendUrl"],
            "projectId": row["projectId"],
            "package": row["package"],
            "port": row["port"],
            "sandbox": True,
            "allowWritesDuringHarvest": True,
        },
        "provider": "custom",
        "generationStatus": "ready" if row.get("reachable") else "needs_start_url",
        "updatedAt": now(),
    }
    if existing:
        await connectors_collection.update_one({"connectorId": existing["connectorId"]}, {"$set": doc})
        return {**existing, **doc}
    doc["connectorId"] = str(uuid.uuid4())
    doc["createdAt"] = now()
    await connectors_collection.insert_one(dict(doc))
    return doc


def trajectory_task(project_id: str, frontend_url: str, name: str, trajectory: Any, index: int) -> dict[str, str]:
    prompt = str(getattr(trajectory, "prompt", "") or "").strip()
    actions = getattr(trajectory, "actions", None) or []
    start_url = ""
    for action in actions:
        start_url = str(getattr(action, "url", "") or "")
        if start_url:
            break
    start_url = remap_url(start_url, frontend_url) if start_url else frontend_url
    return {
        "name": task_name_from_prompt(prompt, index),
        "prompt": prompt,
        "successCriteria": f"IWA project={project_id}, use_case={name}. Complete the task on {start_url}.",
        "status": "draft",
        "taskId": "",
        "iwaProjectId": project_id,
        "iwaUseCase": name,
        "iwaStartUrl": start_url,
    }


async def upsert_agent(
    *,
    email: str,
    company_id: str,
    rows: list[dict[str, Any]],
    tasks_per_project: int,
    harvester: str,
    judge: str,
) -> dict[str, Any]:
    agent_name = "IWA Demo Webs Benchmark Agent"
    existing = await agents_collection.find_one({"email": email, "companyId": company_id, "name": agent_name}, {"_id": 0})
    agent_id = str((existing or {}).get("agentId") or uuid.uuid4())
    runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else ""

    _, get_trajectory_map = import_iwa()
    tasks: list[dict[str, Any]] = []
    for row in rows:
        trajectory_map = get_trajectory_map(row["projectId"]) or {}
        for index, (name, trajectory) in enumerate(sorted(trajectory_map.items()), start=1):
            if tasks_per_project > 0 and index > tasks_per_project:
                break
            task = trajectory_task(row["projectId"], row["frontendUrl"], name, trajectory, index)
            if task["prompt"]:
                tasks.append(task)

    doc = {
        "agentId": agent_id,
        "email": email,
        "companyId": company_id,
        "name": agent_name,
        "websiteUrl": rows[0]["frontendUrl"] if rows else "",
        "runtimeEndpoint": runtime_endpoint,
        "baseRuntimeEndpoint": DEFAULT_OPERATOR_RUNTIME_ENDPOINT,
        "runtimeType": DEFAULT_OPERATOR_RUNTIME_TYPE if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "pending",
        "status": "ready" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "draft",
        "trainingStatus": "needs_trajectories",
        "harvesterImplementation": harvester,
        "judgeImplementation": judge,
        "runtimeCapabilities": {
            "browser": True,
            "apiCalls": False,
            "knowledge": False,
            "python": False,
            "humanApprovalForWrites": True,
        },
        "tasks": tasks,
        "successCriteria": "Use IWA demo web tasks to harvest reusable skills and replay them through /step.",
        "customInstructions": "You operate IWA demo web applications. Prefer approved skills when they match the task.",
        "updatedAt": now(),
    }
    if existing:
        await agents_collection.update_one({"agentId": agent_id}, {"$set": doc})
    else:
        doc["createdAt"] = now()
        await agents_collection.insert_one(dict(doc))

    web_id = f"iwa-{agent_id}"
    benchmark_id = f"iwa-demo-webs-{agent_id}"
    await agent_webs_collection.update_one(
        {"webId": web_id},
        {
            "$set": {
                "webId": web_id,
                "agentId": agent_id,
                "email": email,
                "name": "IWA Demo Webs",
                "baseUrl": rows[0]["frontendUrl"] if rows else "",
                "authRequired": False,
                "updatedAt": now(),
            },
            "$setOnInsert": {"createdAt": now()},
        },
        upsert=True,
    )

    await benchmarks_collection.update_one(
        {"benchmarkId": benchmark_id},
        {
            "$set": {
                "benchmarkId": benchmark_id,
                "agentId": agent_id,
                "companyId": company_id,
                "email": email,
                "name": "IWA Demo Webs Benchmark",
                "description": "Benchmark generated from IWA demo web golden use cases.",
                "source": "iwa_benchmark",
                "updatedAt": now(),
            },
            "$setOnInsert": {"createdAt": now()},
        },
        upsert=True,
    )
    await benchmark_tasks_collection.delete_many({"benchmarkId": benchmark_id})
    await trajectories_collection.delete_many(
        {
            "agentId": agent_id,
            "$or": [
                {"source": "iwa_benchmark"},
                {"metadata.iwaProjectId": {"$exists": True}},
                {"benchmarkId": benchmark_id},
            ],
        }
    )
    await capabilities_collection.delete_many({"agentId": agent_id, "capabilityKind": "skill"})
    task_ids: list[str] = []
    for task in tasks:
        task_id = str(uuid.uuid4())
        task["taskId"] = task_id
        task_ids.append(task_id)
        await benchmark_tasks_collection.insert_one(
            {
                "taskId": task_id,
                "benchmarkId": benchmark_id,
                "agentId": agent_id,
                "companyId": company_id,
                "email": email,
                "webId": web_id,
                "name": task["name"],
                "taskName": task["name"],
                "prompt": task["prompt"],
                "successCriteria": task["successCriteria"],
                "source": "iwa_benchmark",
                "status": "needs_harvest",
                "trajectoryId": "",
                "metadata": {
                    "iwaProjectId": task["iwaProjectId"],
                    "iwaUseCase": task["iwaUseCase"],
                    "iwaStartUrl": task["iwaStartUrl"],
                },
                "createdAt": now(),
                "updatedAt": now(),
            }
        )
    await agents_collection.update_one({"agentId": agent_id}, {"$set": {"tasks": tasks, "updatedAt": now()}})
    return await agents_collection.find_one({"agentId": agent_id}, {"_id": 0}) or doc


async def publish_connector_tools(company_id: str) -> int:
    harvester = ToolkitHarvester()
    count = 0
    async for connector in connectors_collection.find({"companyId": company_id}, {"_id": 0}):
        result = await harvester.harvest(connector)
        for tool in result.get("tools") or []:
            update = {key: value for key, value in tool.items() if key != "createdAt"}
            await tools_collection.update_one(
                {"toolId": tool["toolId"]},
                {"$set": update, "$setOnInsert": {"createdAt": tool.get("createdAt")}},
                upsert=True,
            )
            count += 1
    return count


async def run_harvester(agent: dict[str, Any], *, concurrency: int = 1) -> dict[str, Any]:
    harvester = get_agent_harvester(agent.get("harvesterImplementation"))
    run_id = str(uuid.uuid4())
    await harvester_runs_collection.insert_one(
        {
            "harvesterRunId": run_id,
            "runKind": "iwa_benchmark",
            "agentId": agent["agentId"],
            "companyId": agent["companyId"],
            "email": agent["email"],
            "harvesterType": harvester.name,
            "status": "running",
            "logs": [f"{harvester.name} started by iwa_harvester_benchmark.py"],
            "errors": [],
            "createdAt": now(),
            "updatedAt": now(),
        }
    )
    if concurrency > 1:
        cursor = benchmark_tasks_collection.find(
            {"agentId": agent["agentId"], "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}},
            {"_id": 0},
        ).sort("createdAt", 1)
        tasks = await cursor.to_list(length=500)
        semaphore = asyncio.Semaphore(concurrency)
        completed = 0

        async def worker(task: dict[str, Any]) -> dict[str, Any]:
            nonlocal completed
            async with semaphore:
                item = await harvester.harvest_task(agent, HarvestTask(task))
                completed += 1
                label = item.get("status")
                task_name = task.get("taskName", "")
                project = (task.get("metadata") or {}).get("iwaProjectId", "")
                print(f"[{completed}/{len(tasks)}] {label} {project} - {task_name}", flush=True)
                return item

        results = await asyncio.gather(*(worker(task) for task in tasks))
        result = {"count": len(results), "results": results}
    else:
        result = await harvester.harvest(agent)
    promoted = await _auto_promote_harvested_trajectories(agent["agentId"], judge_name=agent.get("judgeImplementation"))
    await harvester_runs_collection.update_one(
        {"harvesterRunId": run_id},
        {
            "$set": {
                "status": "completed",
                "completedAt": now(),
                "updatedAt": now(),
                "generatedSkills": promoted,
                "result": result,
            }
        },
    )
    return {"harvesterRunId": run_id, "promoted": promoted, **result}


async def verify_step_uses_skills(agent: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    cursor = trajectories_collection.find({"agentId": agent["agentId"], "status": "approved"}, {"_id": 0}).sort("createdAt", 1)
    trajectories = await cursor.to_list(length=limit)
    checks: list[dict[str, Any]] = []
    for index, trajectory in enumerate(trajectories):
        state: dict[str, Any] = {}
        tool_calls: list[str] = []
        result: dict[str, Any] = {}
        used_skill = False
        for step_index in range(50):
            result = await agent_step_result(
                agent["agentId"],
                {
                    "prompt": trajectory.get("prompt", ""),
                    "url": ((trajectory.get("metadata") or {}).get("iwaStartUrl") or agent.get("websiteUrl") or "about:blank"),
                    "step_index": step_index,
                    "state_in": state,
                },
            )
            used_skill = used_skill or result.get("executionMode") == "skill_replay"
            tool_calls.extend([str(call.get("name") or "") for call in result.get("tool_calls", [])])
            state = result.get("state_out") if isinstance(result.get("state_out"), dict) else state
            if result.get("done"):
                break
        checks.append(
            {
                "trajectoryId": trajectory.get("trajectoryId"),
                "taskName": trajectory.get("taskName"),
                "executionMode": result.get("executionMode"),
                "usedSkill": used_skill,
                "toolCalls": tool_calls,
                "done": result.get("done"),
            }
        )
    return checks


async def write_report(payload: dict[str, Any]) -> Path:
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / f"iwa_harvester_benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Seed and benchmark Automata harvesting against IWA demo webs.")
    parser.add_argument("--endpoint", default=os.getenv("DEMO_WEBS_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--starting-port", type=int, default=int(os.getenv("DEMO_WEBS_STARTING_PORT", str(DEFAULT_STARTING_PORT))))
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--company", default=DEFAULT_COMPANY)
    parser.add_argument("--project", action="append", default=[], help="IWA project id to include. Can be repeated.")
    parser.add_argument("--limit-projects", type=int, default=0)
    parser.add_argument("--tasks-per-project", type=int, default=1)
    parser.add_argument("--harvester", default=os.getenv("AUTOMATA_AGENT_HARVESTER", "autoppia_harvester"))
    parser.add_argument("--judge", default=os.getenv("AUTOMATA_TRAJECTORY_JUDGE", "iwa"))
    parser.add_argument("--harvest-concurrency", type=int, default=1)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument("--harvest", action="store_true")
    parser.add_argument("--verify-step", action="store_true")
    parser.add_argument("--step-check-limit", type=int, default=20)
    args = parser.parse_args()

    os.environ["DEMO_WEBS_ENDPOINT"] = args.endpoint
    os.environ["DEMO_WEBS_STARTING_PORT"] = str(args.starting_port)

    await ensure_indexes()
    inventory = await check_urls(build_inventory(args.endpoint, args.starting_port))
    selected = select_rows(inventory, args.project, args.limit_projects)
    report: dict[str, Any] = {
        "endpoint": args.endpoint,
        "startingPort": args.starting_port,
        "inventory": inventory,
        "selectedProjects": [row["projectId"] for row in selected],
    }
    if args.inventory_only:
        path = await write_report(report)
        print(json.dumps({"report": str(path), "projects": len(inventory)}, indent=2))
        return 0

    company = await upsert_company(args.email, args.company)
    connectors = [await upsert_web_connector(args.email, company["companyId"], row) for row in selected]
    published_tools = await publish_connector_tools(company["companyId"])
    agent = await upsert_agent(
        email=args.email,
        company_id=company["companyId"],
        rows=selected,
        tasks_per_project=args.tasks_per_project,
        harvester=args.harvester,
        judge=args.judge,
    )
    await agent_creation_jobs_collection.update_one(
        {"agentId": agent["agentId"]},
        {
            "$set": {
                "jobId": f"iwa-{agent['agentId']}",
                "agentId": agent["agentId"],
                "companyId": company["companyId"],
                "email": args.email,
                "status": "ready_for_harvest",
                "currentStep": "run_harvester",
                "updatedAt": now(),
            },
            "$setOnInsert": {"createdAt": now(), "events": []},
        },
        upsert=True,
    )

    report.update(
        {
            "companyId": company["companyId"],
            "agentId": agent["agentId"],
            "connectors": [{"connectorId": item["connectorId"], "name": item["name"], "status": item["status"]} for item in connectors],
            "publishedTools": published_tools,
            "taskCount": len(agent.get("tasks") or []),
        }
    )
    if args.seed_only:
        path = await write_report(report)
        print(json.dumps({"report": str(path), "agentId": agent["agentId"], "taskCount": report["taskCount"]}, indent=2))
        return 0

    if args.harvest:
        report["harvest"] = await run_harvester(agent, concurrency=max(1, args.harvest_concurrency))
        agent = await agents_collection.find_one({"agentId": agent["agentId"]}, {"_id": 0}) or agent

    if args.verify_step:
        report["stepChecks"] = await verify_step_uses_skills(agent, args.step_check_limit)

    report["summary"] = {
        "trajectoriesTotal": await trajectories_collection.count_documents({"agentId": agent["agentId"]}),
        "benchmarkTasksTotal": await benchmark_tasks_collection.count_documents({"agentId": agent["agentId"]}),
        "approvedSkills": await capabilities_collection.count_documents({"agentId": agent["agentId"], "capabilityKind": "skill", "status": "approved"}),
        "tools": await tools_collection.count_documents({"companyId": company["companyId"]}),
    }
    path = await write_report(report)
    print(json.dumps({"report": str(path), **report["summary"], "agentId": agent["agentId"]}, indent=2))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
