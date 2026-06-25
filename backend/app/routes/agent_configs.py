import uuid
import os
from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    benchmark_tasks_collection,
    capabilities_collection,
    evals_collection,
    agent_webs_collection,
    agents_collection,
    trajectories_collection,
)
from app.routes.agent_creation import ensure_agent_creation_job
from app.repositories import AgentConfigRepository
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.services.agent_runtime import agent_step_result
from app.services.task_contracts import task_metadata_with_contract

router = APIRouter()


AUTOCINEMA_TASKS = [
    {"name": "Login", "prompt": "Log in to Autocinema with username user1 and password Passw0rd!", "status": "verified"},
    {"name": "Search film", "prompt": "Search for The Matrix in Autocinema", "status": "verified"},
    {"name": "Film detail", "prompt": "Open a film detail page in Autocinema", "status": "verified"},
]

AUTOCINEMA_URL = "http://84.247.180.192:8000"
AUTOCINEMA_RUNTIME = "http://127.0.0.1:5060/step"
DEFAULT_AGENT_RUNTIME_ENDPOINT = os.getenv("AUTOMATA_DEFAULT_RUNTIME_ENDPOINT", AUTOCINEMA_RUNTIME).strip()
DEFAULT_AGENT_RUNTIME_TYPE = os.getenv("AUTOMATA_DEFAULT_RUNTIME_TYPE", "generalist_with_company_capabilities").strip()
DEFAULT_RUNTIME_PROXY_BASE = os.getenv("AUTOMATA_RUNTIME_PROXY_BASE", "http://127.0.0.1:8080").rstrip("/")

AUTOCINEMA_CAPABILITIES = [
    {"name": "login", "taskName": "Login", "description": "Log in to Autocinema with the bundled demo credentials."},
    {"name": "search_film", "taskName": "Search film", "description": "Search for a film by title in Autocinema."},
    {"name": "open_film_detail", "taskName": "Film detail", "description": "Open a film detail page from Autocinema."},
]


class AgentTask(BaseModel):
    name: str
    prompt: str
    successCriteria: str = ""
    status: str = "draft"
    trajectoryId: str = ""


class AgentConfigCreateRequest(BaseModel):
    email: str
    companyId: str = ""
    name: str
    websiteUrl: str
    authUsername: str = ""
    authPassword: str = ""
    apiSpecUrl: str = ""
    apiAuthHeaderName: str = ""
    apiAuthHeaderValue: str = ""
    successCriteria: str = ""
    tasks: List[AgentTask] = Field(default_factory=list)
    browserEnabled: bool = True
    browserMode: str = "visible"
    maxCreditsPerRun: float = 5.0


class AgentRuntimeSettingsRequest(BaseModel):
    browserEnabled: bool = True
    browserMode: str = "visible"
    maxCreditsPerRun: float = 5.0


class AgentRunTaskRequest(BaseModel):
    email: str
    companyId: str = ""
    prompt: str
    target: str = "selected"
    agentId: str = ""
    browserEnabled: bool | None = None
    browserMode: str = "visible"
    maxCreditsPerRun: float = 5.0


class AgentBootstrapRequest(BaseModel):
    email: str


def _repo(scope: RequestScope) -> AgentConfigRepository:
    scope = coerce_request_scope(scope)
    return AgentConfigRepository(agents_collection, scope)


def _runtime_spec(
    *,
    browser_enabled: bool = True,
    browser_mode: str = "visible",
    max_credits_per_run: float = 5.0,
    existing_tools: dict[str, Any] | None = None,
    website_url: str = "",
    existing_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = browser_mode if browser_mode in {"visible", "headless"} else "visible"
    credits = max(0.0, float(max_credits_per_run or 0.0))
    existing_spec = existing_spec if isinstance(existing_spec, dict) else {}
    tools = {
        "browser": browser_enabled,
        "connectors": True,
        "skills": True,
        "knowledge": False,
        **(existing_tools or {}),
    }
    tools["browser"] = browser_enabled
    allowed_domains = _runtime_allowed_domains(website_url, existing_spec)
    approval_required_for = _dedupe_runtime_values(existing_spec.get("approvalRequiredFor") or ["write", "send"])
    return {
        "browserEnabled": browser_enabled,
        "browserMode": mode,
        "browserDefaultUse": "exception",
        "browserRestrictedByDomain": bool(allowed_domains),
        "allowedDomains": allowed_domains,
        "approvalRequiredFor": approval_required_for,
        "runtimeClasses": _runtime_classes(browser_enabled=browser_enabled, tools=tools),
        "maxCreditsPerRun": credits,
        "tools": tools,
    }


def _dedupe_runtime_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _runtime_host(value: str) -> str:
    try:
        return (urlparse(str(value or "")).hostname or "").lower()
    except Exception:
        return ""


def _runtime_allowed_domains(website_url: str, existing_spec: dict[str, Any]) -> list[str]:
    raw_domains = (
        existing_spec.get("allowedDomains")
        or existing_spec.get("browserAllowedDomains")
        or existing_spec.get("allowedOrigins")
        or []
    )
    domains = _dedupe_runtime_values(raw_domains if isinstance(raw_domains, list) else [])
    website_host = _runtime_host(website_url)
    if website_host and website_host not in domains:
        domains.append(website_host)
    return domains


def _runtime_classes(*, browser_enabled: bool, tools: dict[str, Any]) -> list[str]:
    classes = ["api_runtime"]
    if tools.get("connectors"):
        classes.append("connector_runtime")
    if tools.get("skills"):
        classes.append("skill_runtime")
    if browser_enabled:
        classes.append("browser_runtime")
        if tools.get("connectors") or tools.get("skills"):
            classes.append("hybrid_runtime")
    return classes


def _serialize_agent_config(doc: dict[str, Any]) -> dict[str, Any]:
    agent_id = doc.get("agentId", "")
    runtime_capabilities = doc.get("runtimeCapabilities", {"browser": True, "apiCalls": True, "knowledge": False, "python": False})
    runtime_spec = doc.get("runtimeSpec") or _runtime_spec(
        browser_enabled=bool(runtime_capabilities.get("browser", True)),
        browser_mode=str(doc.get("browserMode") or "visible"),
        max_credits_per_run=float(doc.get("maxCreditsPerRun") or 5.0),
        website_url=str(doc.get("websiteUrl") or ""),
        existing_spec=doc.get("runtimeSpec") if isinstance(doc.get("runtimeSpec"), dict) else {},
    )
    if isinstance(runtime_spec, dict):
        runtime_spec = _runtime_spec(
            browser_enabled=bool(runtime_spec.get("browserEnabled", runtime_capabilities.get("browser", True))),
            browser_mode=str(runtime_spec.get("browserMode") or doc.get("browserMode") or "visible"),
            max_credits_per_run=float(runtime_spec.get("maxCreditsPerRun") or doc.get("maxCreditsPerRun") or 5.0),
            existing_tools=runtime_spec.get("tools") if isinstance(runtime_spec.get("tools"), dict) else None,
            website_url=str(doc.get("websiteUrl") or ""),
            existing_spec=runtime_spec,
        )
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeEndpoint": doc.get("runtimeEndpoint", ""),
        "runtimeType": doc.get("runtimeType", "replay"),
        "status": doc.get("status", "draft"),
        "trainingStatus": doc.get("trainingStatus", "not_started"),
        "harvester": doc.get("harvester", "Automata Agent"),
        "companyId": doc.get("companyId", ""),
        "runtimeCapabilities": runtime_capabilities,
        "runtimeSpec": runtime_spec,
        "apiSpecUrl": doc.get("apiSpecUrl", ""),
        "apiAuthConfigured": bool(doc.get("apiAuth", {}).get("headerValueConfigured")),
        "tasks": doc.get("tasks", []),
        "trajectories": doc.get("trajectories", []),
        "successCriteria": doc.get("successCriteria", ""),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _agent_docs_for_run(body: AgentRunTaskRequest) -> list[dict[str, Any]]:
    if body.target == "selected":
        if not body.agentId:
            raise HTTPException(status_code=400, detail="agentId is required for selected target")
        query: dict[str, Any] = {"agentId": body.agentId, "email": body.email}
        if body.companyId:
            query["companyId"] = body.companyId
        doc = await agents_collection.find_one(query, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Agent not found")
        return [doc]

    query: dict[str, Any] = {"email": body.email}
    if body.companyId:
        query["companyId"] = body.companyId
    cursor = agents_collection.find(query, {"_id": 0}).sort("createdAt", -1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="No agents found")
    return docs[:12]


async def _ensure_agent_evals(
    *,
    email: str,
    agent_id: str,
    agent_name: str,
    website_url: str,
    tasks: list[dict[str, Any]],
) -> list[str]:
    eval_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    benchmark_id = f"agent-{agent_id}"
    for task in tasks:
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        eval_id = str(uuid.uuid4())
        result = await evals_collection.update_one(
            {
                "email": email,
                "agentId": agent_id,
                "prompt": prompt,
            },
            {
                "$set": {
                    "benchmarkId": benchmark_id,
                    "benchmarkName": f"{agent_name} Benchmark",
                    "initialUrl": website_url,
                },
                "$setOnInsert": {
                    "evalId": eval_id,
                    "email": email,
                    "prompt": prompt,
                    "agentId": agent_id,
                    "agentName": agent_name,
                    "agentTaskName": str(task.get("name") or ""),
                    "createdAt": now,
                }
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            eval_ids.append(eval_id)
        else:
            existing = await evals_collection.find_one(
                {"email": email, "agentId": agent_id, "prompt": prompt},
                {"_id": 0, "evalId": 1},
            )
            if existing and existing.get("evalId"):
                eval_ids.append(str(existing["evalId"]))
    return eval_ids


async def _ensure_agent_benchmark_tasks(
    *,
    email: str,
    company_id: str,
    agent_id: str,
    benchmark_id: str,
    website_url: str,
    web_id: str,
    tasks: list[dict[str, Any]],
    source: str = "agent_config",
) -> list[str]:
    task_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    for task in tasks:
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        task_id = str(task.get("taskId") or uuid.uuid4())
        task_name = str(task.get("name") or task.get("taskName") or "").strip()
        metadata = task_metadata_with_contract(
            task,
            website_url=website_url,
            allowed_systems=[website_url] if website_url else [],
        )
        result = await benchmark_tasks_collection.update_one(
            {
                "email": email,
                "agentId": agent_id,
                "benchmarkId": benchmark_id,
                "prompt": prompt,
            },
            {
                "$set": {
                    "companyId": company_id,
                    "webId": web_id,
                    "name": task_name,
                    "taskName": task_name,
                    "prompt": prompt,
                    "successCriteria": str(task.get("successCriteria") or ""),
                    "metadata": metadata,
                    "businessIntent": metadata["businessIntent"],
                    "initialState": metadata["initialState"],
                    "allowedSystems": metadata["allowedSystems"],
                    "expectedArtifacts": metadata["expectedArtifacts"],
                    "riskClass": metadata["riskClass"],
                    "status": "needs_harvest",
                    "trajectoryId": str(task.get("trajectoryId") or ""),
                    "source": source,
                    "updatedAt": now,
                },
                "$setOnInsert": {
                    "taskId": task_id,
                    "email": email,
                    "agentId": agent_id,
                    "benchmarkId": benchmark_id,
                    "createdAt": now,
                },
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            task_ids.append(task_id)
        else:
            existing = await benchmark_tasks_collection.find_one(
                {"email": email, "agentId": agent_id, "benchmarkId": benchmark_id, "prompt": prompt},
                {"_id": 0, "taskId": 1},
            )
            if existing and existing.get("taskId"):
                task_ids.append(str(existing["taskId"]))
    return task_ids


async def _ensure_autocinema_assets(*, email: str, agent_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    web_id = f"autocinema-{agent_id}"
    await agent_webs_collection.update_one(
        {"webId": web_id},
        {
            "$set": {
                "agentId": agent_id,
                "email": email,
                "name": "Autocinema",
                "baseUrl": AUTOCINEMA_URL,
                "authRequired": True,
                "updatedAt": now,
            },
            "$setOnInsert": {"webId": web_id, "createdAt": now},
        },
        upsert=True,
    )

    trajectory_ids_by_task: dict[str, str] = {}
    for task in AUTOCINEMA_TASKS:
        trajectory_id = f"autocinema-{agent_id}-{task['name'].lower().replace(' ', '-')}"
        trajectory_ids_by_task[task["name"]] = trajectory_id
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory_id},
            {
                "$set": {
                    "agentId": agent_id,
                    "email": email,
                    "webId": web_id,
                    "taskName": task["name"],
                    "prompt": task["prompt"],
                    "successCriteria": "User confirms replay success or IWA reward accepts the task.",
                    "source": "bundled_autocinema_package",
                    "status": "approved",
                    "actions": [],
                    "screenshots": [],
                    "updatedAt": now,
                },
                "$setOnInsert": {"trajectoryId": trajectory_id, "createdAt": now},
            },
            upsert=True,
        )

    for capability in AUTOCINEMA_CAPABILITIES:
        capability_id = f"autocinema-{agent_id}-{capability['name']}"
        await capabilities_collection.update_one(
            {"capabilityId": capability_id},
            {
                "$set": {
                    "agentId": agent_id,
                    "email": email,
                    "webId": web_id,
                    "name": capability["name"],
                    "description": capability["description"],
                    "type": "web",
                    "parameters": [],
                    "trajectoryIds": [trajectory_ids_by_task[capability["taskName"]]],
                    "runtime": "trajectory_replay_with_recovery",
                    "updatedAt": now,
                },
                "$setOnInsert": {"capabilityId": capability_id, "createdAt": now},
            },
            upsert=True,
        )

    return {"webId": web_id, "trajectoryIds": list(trajectory_ids_by_task.values())}


@router.get("/agents")
async def get_agents(email: str, companyId: str = "", scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        email = scope.require_email(email)
        query: dict[str, Any] = {"email": email}
        if companyId:
            query["companyId"] = companyId
        cursor = agents_collection.find(query).sort("createdAt", -1)
        agents = []
        async for doc in cursor:
            agents.append(_serialize_agent_config(doc))
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, scope: RequestScope = Depends(get_request_scope)):
    try:
        doc = await _repo(scope).by_id(agent_id)
        agent = _serialize_agent_config(doc)
        return {"agent": agent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents")
async def create_agent(body: AgentConfigCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        email = scope.require_email(body.email)
        now = datetime.now(timezone.utc)
        agent_id = str(uuid.uuid4())
        runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step" if DEFAULT_AGENT_RUNTIME_ENDPOINT else ""
        doc = {
            "agentId": agent_id,
            "email": email,
            "companyId": body.companyId,
            "name": body.name,
            "websiteUrl": body.websiteUrl,
            "runtimeEndpoint": runtime_endpoint,
            "baseRuntimeEndpoint": DEFAULT_AGENT_RUNTIME_ENDPOINT,
            "runtimeType": DEFAULT_AGENT_RUNTIME_TYPE if DEFAULT_AGENT_RUNTIME_ENDPOINT else "pending",
            "status": "ready" if DEFAULT_AGENT_RUNTIME_ENDPOINT else "draft",
            "trainingStatus": "needs_harvest",
            "harvester": "Automata Agent",
            "runtimeCapabilities": {
                "browser": body.browserEnabled,
                "apiCalls": True,
                "knowledge": False,
                "python": False,
                "humanApprovalForWrites": True,
            },
            "runtimeSpec": _runtime_spec(
                browser_enabled=body.browserEnabled,
                browser_mode=body.browserMode,
                max_credits_per_run=body.maxCreditsPerRun,
                website_url=body.websiteUrl,
            ),
            "tasks": [task.model_dump() for task in body.tasks],
            "trajectories": [],
            "successCriteria": body.successCriteria,
            "apiSpecUrl": body.apiSpecUrl.strip(),
            "apiAuth": {
                "headerName": body.apiAuthHeaderName.strip(),
                "headerValueConfigured": bool(body.apiAuthHeaderValue),
            },
            "auth": {
                "hasCredentials": bool(body.authUsername or body.authPassword),
                "username": body.authUsername,
                "passwordConfigured": bool(body.authPassword),
            },
            "createdAt": now,
            "updatedAt": now,
        }
        await agents_collection.insert_one(doc)
        await ensure_agent_creation_job(doc)
        web_id = f"default-{agent_id}"
        await agent_webs_collection.insert_one(
            {
                "webId": web_id,
                "agentId": agent_id,
                "email": email,
                "name": body.name,
                "baseUrl": body.websiteUrl,
                "authRequired": bool(body.authUsername or body.authPassword),
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
            }
        )
        eval_ids = await _ensure_agent_evals(
            email=email,
            agent_id=agent_id,
            agent_name=body.name,
            website_url=body.websiteUrl,
            tasks=[task.model_dump() for task in body.tasks],
        )
        task_ids = await _ensure_agent_benchmark_tasks(
            email=email,
            company_id=body.companyId,
            agent_id=agent_id,
            benchmark_id=f"agent-{agent_id}",
            website_url=body.websiteUrl,
            web_id=web_id,
            tasks=[task.model_dump() for task in body.tasks],
            source="user_prompt",
        )
        return {
            "success": True,
            "agentId": agent_id,
            "agentConfigId": agent_id,
            "evalIds": eval_ids,
            "taskIds": task_ids,
            "trajectoryIds": [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/agents/{agent_id}/runtime-settings")
async def update_agent_runtime_settings(agent_id: str, body: AgentRuntimeSettingsRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        repo = _repo(scope)
        existing = await repo.by_id(agent_id)
        runtime_spec = _runtime_spec(
            browser_enabled=body.browserEnabled,
            browser_mode=body.browserMode,
            max_credits_per_run=body.maxCreditsPerRun,
            existing_tools=(existing.get("runtimeSpec") or {}).get("tools") if isinstance(existing.get("runtimeSpec"), dict) else None,
            website_url=str(existing.get("websiteUrl") or ""),
            existing_spec=existing.get("runtimeSpec") if isinstance(existing.get("runtimeSpec"), dict) else {},
        )
        capabilities = {
            **(existing.get("runtimeCapabilities") if isinstance(existing.get("runtimeCapabilities"), dict) else {}),
            "browser": body.browserEnabled,
        }
        await repo.update_owned_one(
            {"agentId": agent_id},
            {
                "$set": {
                    "runtimeSpec": runtime_spec,
                    "runtimeCapabilities": capabilities,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )
        refreshed = await agents_collection.find_one({"agentId": agent_id})
        return {"success": True, "agent": _serialize_agent_config(refreshed or existing)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/run-task")
async def run_agent_task(body: AgentRunTaskRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        body.email = scope.require_email(body.email)
        prompt = body.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")

        docs = await _agent_docs_for_run(body)
        runtime_overrides: dict[str, Any] = {
            "browserMode": body.browserMode if body.browserMode in {"visible", "headless"} else "visible",
            "maxCreditsPerRun": max(0.0, float(body.maxCreditsPerRun or 0.0)),
        }
        if body.browserEnabled is not None:
            runtime_overrides["browserEnabled"] = body.browserEnabled

        results = []
        for doc in docs:
            agent_id = str(doc.get("agentId") or "")
            try:
                result = await agent_step_result(
                    agent_id,
                    {
                        "prompt": prompt,
                        "task": prompt,
                        "url": str(doc.get("websiteUrl") or ""),
                        "step_index": 0,
                        "state_in": {},
                        "context": {"runtimeOverrides": runtime_overrides},
                    },
                )
                results.append(
                    {
                        "agentId": agent_id,
                        "agentName": doc.get("name", ""),
                        "status": "ok",
                        "result": result,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "agentId": agent_id,
                        "agentName": doc.get("name", ""),
                        "status": "failed",
                        "error": str(getattr(exc, "detail", exc)),
                    }
                )

        return {
            "success": True,
            "target": body.target,
            "count": len(results),
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/bootstrap/autocinema")
async def bootstrap_autocinema_agent(body: AgentBootstrapRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        body.email = scope.require_email(body.email)
        existing = await agents_collection.find_one(
            {"email": body.email, "name": "Autocinema"}
        )
        if existing:
            updates = {
                "websiteUrl": AUTOCINEMA_URL,
                "runtimeEndpoint": AUTOCINEMA_RUNTIME,
                "runtimeType": "standard_replay_recovery",
                "status": "ready",
                "trainingStatus": "verified",
                "harvester": "Automata Agent",
                "runtimeCapabilities": {
                    "browser": True,
                    "apiCalls": True,
                    "knowledge": False,
                    "python": False,
                    "humanApprovalForWrites": True,
                },
                "apiSpecUrl": "",
                "apiAuth": {"headerName": "", "headerValueConfigured": False},
                "tasks": AUTOCINEMA_TASKS,
                "trajectories": [
                    {"name": task["name"], "status": "verified", "source": "bundled_autocinema_package"}
                    for task in AUTOCINEMA_TASKS
                ],
                "successCriteria": "IWA benchmark success for the matched Autocinema task.",
                "updatedAt": datetime.now(timezone.utc),
            }
            await agents_collection.update_one(
                {"agentId": existing.get("agentId")},
                {"$set": updates},
            )
            refreshed = await agents_collection.find_one({"agentId": existing.get("agentId")})
            eval_ids = await _ensure_agent_evals(
                email=body.email,
                agent_id=str(existing.get("agentId") or ""),
                agent_name="Autocinema",
                website_url=AUTOCINEMA_URL,
                tasks=AUTOCINEMA_TASKS,
            )
            assets = await _ensure_autocinema_assets(
                email=body.email,
                agent_id=str(existing.get("agentId") or ""),
            )
            return {
                "success": True,
                "agentId": existing.get("agentId"),
                "agentConfigId": existing.get("agentId"),
                "agent": _serialize_agent_config(refreshed or existing),
                "evalIds": eval_ids,
                "assets": assets,
            }

        now = datetime.now(timezone.utc)
        agent_id = str(uuid.uuid4())
        doc = {
            "agentId": agent_id,
            "email": body.email,
            "name": "Autocinema",
            "websiteUrl": AUTOCINEMA_URL,
            "runtimeEndpoint": AUTOCINEMA_RUNTIME,
            "runtimeType": "standard_replay_recovery",
            "status": "ready",
            "trainingStatus": "verified",
            "harvester": "Automata Agent",
            "companyId": "",
            "runtimeCapabilities": {
                "browser": True,
                "apiCalls": True,
                "knowledge": False,
                "python": False,
                "humanApprovalForWrites": True,
            },
            "apiSpecUrl": "",
            "apiAuth": {"headerName": "", "headerValueConfigured": False},
            "tasks": AUTOCINEMA_TASKS,
            "trajectories": [
                {"name": task["name"], "status": "verified", "source": "bundled_autocinema_package"}
                for task in AUTOCINEMA_TASKS
            ],
            "successCriteria": "IWA benchmark success for the matched Autocinema task.",
            "createdAt": now,
            "updatedAt": now,
        }
        await agents_collection.insert_one(doc)
        eval_ids = await _ensure_agent_evals(
            email=body.email,
            agent_id=agent_id,
            agent_name="Autocinema",
            website_url=AUTOCINEMA_URL,
            tasks=AUTOCINEMA_TASKS,
        )
        assets = await _ensure_autocinema_assets(email=body.email, agent_id=agent_id)
        return {
            "success": True,
            "agentId": agent_id,
            "agentConfigId": agent_id,
            "agent": _serialize_agent_config(doc),
            "evalIds": eval_ids,
            "assets": assets,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
