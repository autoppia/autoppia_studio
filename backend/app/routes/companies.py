import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import companies_collection
from app.database import (
    approvals_collection,
    capabilities_collection,
    credentials_collection,
    entities_collection,
    eval_runs_collection,
    evals_collection,
    benchmark_tasks_collection,
    benchmarks_collection,
    connectors_collection,
    knowledge_documents_collection,
    sessions_collection,
    tools_collection,
    vector_databases_collection,
    work_items_collection,
    artifacts_collection,
    agent_webs_collection,
    agents_collection,
    trajectories_collection,
)
from app.harvesters.base import connector_surface
from app.repositories import CompanyRepository
from app.request_scope import RequestScope, coerce_request_scope, get_request_scope
from app.services.artifact_outputs import summarize_artifact_outputs
from app.services.company_integration_contract import allowed_origin_hosts as _allowed_origin_hosts
from app.services.company_integration_contract import build_company_governance
from app.services.company_integration_contract import build_company_integration_contract
from app.services.company_integration_contract import connector_domains as _connector_domains
from app.services.connector_factory import summarize_connector_factory
from app.services.promotion_pipeline import summarize_promotion_pipeline
from app.services.resource_governance import derived_resource_gate as _derived_resource_gate
from app.services.resource_governance import resource_acl as _resource_acl
from app.services.resource_governance import resource_contract as _resource_contract
from app.services.resource_governance import resource_read_tools as _resource_read_tools
from app.services.resource_governance import resource_vector_id as _resource_vector_id
from app.services.resource_governance import summarize_resource_governance
from app.services.runtime_policy_summary import summarize_runtime_policy_map
from app.services.runtime_sessions import session_runtime_kind, summarize_session_contracts
from app.services.skill_eval_gates import summarize_skill_eval_gates
from app.services.skill_packages import summarize_skill_packages
from app.services.skill_readiness import skill_reusability_ready
from app.services.task_contracts import task_contract_from_record, task_contract_ready
from app.services.work_orchestration import summarize_work_orchestration_contracts

router = APIRouter()


class CompanyCreateRequest(BaseModel):
    email: str
    name: str
    description: str = ""
    industry: str = ""


class CompanyUpdateRequest(BaseModel):
    name: str
    description: str = ""
    industry: str = ""


class CompanyEmbedSettingsRequest(BaseModel):
    enabled: bool = False
    publicToken: str = ""
    hostJwtSecret: str = ""
    clearHostJwtSecret: bool = False
    allowedOrigins: list[str] = []


class DemoResetRequest(BaseModel):
    email: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    embed_settings = doc.get("embedSettings") if isinstance(doc.get("embedSettings"), dict) else {}
    return {
        "companyId": doc.get("companyId", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "description": doc.get("description", ""),
        "industry": doc.get("industry", ""),
        "embedSettings": {
            "enabled": bool(embed_settings.get("enabled")),
            "publicToken": str(embed_settings.get("publicToken") or ""),
            "allowedOrigins": embed_settings.get("allowedOrigins") if isinstance(embed_settings.get("allowedOrigins"), list) else [],
            "hostJwtConfigured": bool(embed_settings.get("hostJwtSecret")),
            "updatedAt": embed_settings.get("updatedAt", ""),
        } if embed_settings else {},
        "status": doc.get("status", "active"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _count(query: dict[str, Any], collection: Any) -> int:
    return int(await collection.count_documents(query))


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _normalized_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item or "").strip()]


def _task_metadata(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("metadata") if isinstance(task.get("metadata"), dict) else {}


def _top_named_items(items: list[dict[str, Any]], *, name_key: str, count_key: str = "count", limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"name": str(item.get(name_key) or "unknown"), count_key: int(item.get(count_key) or 0)}
        for item in items[:limit]
    ]


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _work_latest_credits(doc: dict[str, Any]) -> float:
    report = doc.get("report") if isinstance(doc.get("report"), dict) else {}
    return _safe_float(report.get("creditsSpent"))


def _work_retry_count(doc: dict[str, Any]) -> int:
    history = doc.get("runHistory") if isinstance(doc.get("runHistory"), list) else []
    return max(0, len(history) - 1)


async def _ensure_default_company(email: str) -> dict[str, Any]:
    existing = await companies_collection.find_one({"email": email})
    if existing:
        return existing
    now = _now()
    doc = {
        "companyId": str(uuid.uuid4()),
        "email": email,
        "name": "Default Company",
        "description": "Default workspace for agents, connectors, skills, benchmarks, and runs.",
        "industry": "",
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }
    await companies_collection.insert_one(doc)
    return doc


def _repo(scope: RequestScope) -> CompanyRepository:
    scope = coerce_request_scope(scope)
    return CompanyRepository(companies_collection, scope)


@router.get("/companies")
async def list_companies(email: str, scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        email = scope.require_email(email)
        await _ensure_default_company(email)
        cursor = companies_collection.find({"email": email}, {"_id": 0}).sort("createdAt", 1)
        return {"companies": [_serialize(doc) async for doc in cursor]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies")
async def create_company(body: CompanyCreateRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        scope = coerce_request_scope(scope)
        email = scope.require_email(body.email)
        now = _now()
        doc = {
            "companyId": str(uuid.uuid4()),
            "email": email,
            "name": body.name.strip() or "Untitled Company",
            "description": body.description.strip(),
            "industry": body.industry.strip(),
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        await companies_collection.insert_one(doc)
        return {"success": True, "company": _serialize(doc)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/companies/{company_id}")
async def update_company(company_id: str, body: CompanyUpdateRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        repo = _repo(scope)
        await repo.by_id(company_id)
        now = _now()
        update = {
            "name": body.name.strip() or "Untitled Company",
            "description": body.description.strip(),
            "industry": body.industry.strip(),
            "updatedAt": now,
        }
        doc = await repo.update_owned_one({"companyId": company_id}, {"$set": update}, not_found="Company not found")
        return {"success": True, "company": _serialize(doc or {"companyId": company_id, **update})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/companies/{company_id}/embed-settings")
async def update_company_embed_settings(company_id: str, body: CompanyEmbedSettingsRequest, scope: RequestScope = Depends(get_request_scope)):
    try:
        repo = _repo(scope)
        existing = await repo.by_id(company_id)
        token = body.publicToken.strip() or str(uuid.uuid4())
        existing_settings = existing.get("embedSettings") if isinstance(existing.get("embedSettings"), dict) else {}
        if body.clearHostJwtSecret:
            host_jwt_secret = ""
        elif body.hostJwtSecret.strip():
            host_jwt_secret = body.hostJwtSecret.strip()
        else:
            host_jwt_secret = str(existing_settings.get("hostJwtSecret") or "")
        settings = {
            "enabled": bool(body.enabled),
            "publicToken": token,
            "hostJwtSecret": host_jwt_secret,
            "allowedOrigins": [origin.strip().rstrip("/") for origin in body.allowedOrigins if origin.strip()],
            "updatedAt": _now(),
        }
        doc = await repo.update_owned_one(
            {"companyId": company_id},
            {"$set": {"embedSettings": settings, "updatedAt": _now()}},
            not_found="Company not found",
        )
        serialized = _serialize(doc or {"companyId": company_id, "embedSettings": settings})
        return {"success": True, "company": serialized, "embedSettings": serialized.get("embedSettings", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, scope: RequestScope = Depends(get_request_scope)):
    try:
        company = await _repo(scope).by_id(company_id)
        agent_docs = await agents_collection.find(
            {"companyId": company_id},
            {"_id": 0, "agentId": 1},
        ).to_list(length=500)
        agent_ids = [doc.get("agentId") for doc in agent_docs if doc.get("agentId")]
        if agent_ids:
            await agent_webs_collection.delete_many({"agentId": {"$in": agent_ids}})
            await trajectories_collection.delete_many({"agentId": {"$in": agent_ids}})
            await capabilities_collection.delete_many({"agentId": {"$in": agent_ids}})
            await evals_collection.delete_many({"agentId": {"$in": agent_ids}})
            await eval_runs_collection.delete_many({"agentId": {"$in": agent_ids}})
            await agents_collection.delete_many({"agentId": {"$in": agent_ids}})
        await connectors_collection.delete_many({"companyId": company_id})
        await companies_collection.delete_one({"companyId": company_id})
        await _ensure_default_company(str(company.get("email") or ""))
        return {"success": True, "deletedAgents": len(agent_ids)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/setup-contract")
async def get_company_setup_contract(company_id: str, scope: RequestScope = Depends(get_request_scope)):
    try:
        repo = _repo(scope)
        company = await repo.by_id(company_id)
        company_id = str(company.get("companyId") or "")
        email = str(company.get("email") or "")

        connectors = await connectors_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
        sessions = await sessions_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=500)
        skills = await capabilities_collection.find({"companyId": company_id, "capabilityKind": "skill"}, {"_id": 0}).to_list(length=500)
        tools = await tools_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=500)
        benchmarks = await benchmarks_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=500)
        benchmark_tasks = await benchmark_tasks_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=1000)
        trajectories = await trajectories_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=1000)
        eval_runs = await eval_runs_collection.find({"companyId": company_id, "email": email}, {"_id": 0, "actions": 0, "screenshots": 0}).to_list(length=1000)
        work_items = await work_items_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=1000)
        approvals = await approvals_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=1000)
        artifacts = await artifacts_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=1000)
        knowledge_docs = await knowledge_documents_collection.find({"companyId": company_id, "email": email}, {"_id": 0, "storagePath": 0}).to_list(length=1000)
        vector_stores = await vector_databases_collection.find({"companyId": company_id, "email": email}, {"_id": 0}).to_list(length=500)

        runtime_kinds = [session_runtime_kind(doc) for doc in sessions]
        connected_connectors = [doc for doc in connectors if str(doc.get("status") or "") == "connected"]
        needs_auth_connectors = [doc for doc in connectors if str(doc.get("status") or "") == "needs_auth"]
        custom_connectors = [doc for doc in connectors if str(doc.get("provider") or "") == "custom"]
        connector_domains = sorted({domain for doc in connectors for domain in _connector_domains(doc)})
        category_counts = _sorted_counts([str(doc.get("category") or "uncategorized") for doc in connectors])
        surface_counts = _sorted_counts([connector_surface(doc) for doc in connectors])
        connector_factory = summarize_connector_factory(connectors)
        policy_counts = _sorted_counts([str(doc.get("riskPolicy") or "unspecified") for doc in skills])
        task_contracts_ready = sum(1 for task in benchmark_tasks if task_contract_ready(task))
        task_contracts = [task_contract_from_record(task) for task in benchmark_tasks]
        promotion_pipeline = summarize_promotion_pipeline(tasks=benchmark_tasks, trajectories=trajectories, skills=skills)
        task_artifacts = sorted({artifact for contract in task_contracts for artifact in _normalized_list(contract.get("expectedArtifacts"))})
        task_inputs = sorted({input_name for contract in task_contracts for input_name in _normalized_list(contract.get("expectedInputs"))})
        task_allowed_systems = sorted({system for contract in task_contracts for system in _normalized_list(contract.get("allowedSystems"))})
        task_business_intents = [
            str(contract.get("businessIntent") or task.get("name") or task.get("agentTaskName") or "").strip()
            for task, contract in zip(benchmark_tasks, task_contracts)
        ]
        task_risks = [str(contract.get("riskClass") or "unspecified") for contract in task_contracts]
        benchmark_verticals = _sorted_counts([str(doc.get("vertical") or "general") for doc in benchmarks])
        skill_artifacts = sorted({artifact for skill in skills for artifact in _normalized_list(skill.get("expectedArtifacts"))})
        hardened_skills = sum(1 for skill in skills if skill_reusability_ready(skill))
        skill_packages = summarize_skill_packages(skills, package_limit=8)
        eval_gate = summarize_skill_eval_gates(skills, eval_runs)
        side_effects = _sorted_counts([str(tool.get("sideEffects") or tool.get("sideEffect") or "unknown") for tool in tools])
        tool_entities = sorted(
            {
                entity
                for tool in tools
                for entity in [*_normalized_list(tool.get("inputEntities")), str(tool.get("outputEntity") or "").strip()]
                if entity
            }
        )
        resource_read_tools = sorted({tool for doc in knowledge_docs for tool in _resource_read_tools(doc)})
        resource_gates = [_derived_resource_gate(doc) for doc in knowledge_docs]
        resource_summary = summarize_resource_governance(knowledge_docs)
        runtime_ready_resources = sum(1 for gate in resource_gates if bool(gate.get("readyForRuntime")))
        resource_vector_ids = {_resource_vector_id(doc) for doc in knowledge_docs if _resource_vector_id(doc)}
        vector_store_ids = {str(doc.get("vectorDatabaseId") or "").strip() for doc in vector_stores if str(doc.get("vectorDatabaseId") or "").strip()}
        docs_with_contract = sum(1 for doc in knowledge_docs if _resource_contract(doc))
        docs_with_vector_store = sum(1 for doc in knowledge_docs if _resource_vector_id(doc))
        resource_acls = [_resource_acl(doc) for doc in knowledge_docs]
        docs_with_acl = sum(1 for acl in resource_acls if acl.get("explicit"))
        company_visible_docs = sum(1 for acl in resource_acls if acl.get("visibility") == "company")
        restricted_docs = sum(1 for acl in resource_acls if acl.get("visibility") not in {"", "company", "unspecified"})
        acl_visibility_counts = _sorted_counts([str(acl.get("visibility") or "unspecified") for acl in resource_acls])
        resource_gaps = [
            gap
            for gap in [
                {"key": "resource_contracts", "label": "Knowledge documents exist but no resource contracts are exposed.", "target": "knowledge"} if knowledge_docs and docs_with_contract == 0 else None,
                {"key": "resource_acl", "label": "Knowledge resources need explicit ACL governance before broad runtime use.", "target": "knowledge"} if knowledge_docs and docs_with_acl < len(knowledge_docs) else None,
                {"key": "resource_read_tools", "label": "Knowledge resources need read-only tools before they can support skills.", "target": "knowledge"} if knowledge_docs and not resource_read_tools else None,
                {"key": "resource_runtime_gate", "label": "Knowledge resources must pass runtime grounding gates before skills rely on them.", "target": "knowledge"} if knowledge_docs and runtime_ready_resources < len(knowledge_docs) else None,
                {"key": "vector_index", "label": "Knowledge resources are not linked to vector stores.", "target": "knowledge"} if knowledge_docs and docs_with_vector_store == 0 else None,
                {"key": "vector_store", "label": "Create a vector store for indexed business context.", "target": "knowledge"} if knowledge_docs and not vector_stores else None,
            ]
            if gap
        ]
        now_dt = datetime.now(timezone.utc)
        work_item_ids = {str(doc.get("workItemId") or "") for doc in work_items if str(doc.get("workItemId") or "")}
        approval_work_item_ids = {
            str((approval.get("metadata") if isinstance(approval.get("metadata"), dict) else {}).get("workItemId") or "")
            for approval in approvals
            if str(approval.get("status") or "") == "pending"
        }
        approval_work_item_ids = {item for item in approval_work_item_ids if item in work_item_ids}
        scheduled_items = [doc for doc in work_items if str(doc.get("triggerType") or "manual") == "scheduled"]
        due_scheduled_items = [
            doc
            for doc in scheduled_items
            if (parsed := _parse_iso_datetime(doc.get("nextRunAt"))) is not None and parsed <= now_dt
        ]
        upcoming_scheduled_items = [
            doc
            for doc in scheduled_items
            if (parsed := _parse_iso_datetime(doc.get("nextRunAt"))) is not None and parsed > now_dt
        ]
        budgeted_items = [doc for doc in work_items if _safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun"))) > 0]
        exhausted_budget_items = [
            doc
            for doc in budgeted_items
            if _work_latest_credits(doc) >= _safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun")))
        ]
        retried_items = [doc for doc in work_items if _work_retry_count(doc) > 0]
        max_retry_count = max([_work_retry_count(doc) for doc in work_items] or [0])
        review_blocked_items = [
            doc
            for doc in work_items
            if str(doc.get("status") or "") == "REVIEW"
            or str((doc.get("pendingApproval") if isinstance(doc.get("pendingApproval"), dict) else {}).get("approvalId") or "")
            or str(doc.get("workItemId") or "") in approval_work_item_ids
        ]
        session_contracts = summarize_session_contracts(sessions)
        artifact_outputs = summarize_artifact_outputs(artifacts)
        work_contracts = summarize_work_orchestration_contracts(work_items)
        browser_allowlisted = bool(connector_domains or (company.get("embedSettings") or {}).get("allowedOrigins"))
        runtime_policy_map = summarize_runtime_policy_map(
            skills=skills,
            tools=tools,
            runtime_kinds=runtime_kinds,
            browser_allowlisted=browser_allowlisted,
            pending_approvals=sum(1 for doc in approvals if str(doc.get("status") or "") == "pending"),
            approved_approvals=sum(1 for doc in approvals if str(doc.get("status") or "") == "approved"),
        )

        counts = {
            "connectors": len(connectors),
            "connectedConnectors": len(connected_connectors),
            "connectorsNeedingAuth": len(needs_auth_connectors),
            "customConnectors": len(custom_connectors),
            "credentials": await _count({"companyId": company_id, "email": email}, credentials_collection),
            "resources": len(knowledge_docs),
            "vectorStores": len(vector_stores),
            "entities": await _count({"companyId": company_id, "email": email}, entities_collection),
            "agents": await _count({"companyId": company_id, "email": email}, agents_collection),
            "tools": len(tools),
            "typedTools": await _count(
                {
                    "companyId": company_id,
                    "email": email,
                    "$or": [
                        {"inputEntities.0": {"$exists": True}},
                        {"outputEntity": {"$nin": ["", None]}},
                    ],
                },
                tools_collection,
            ),
            "benchmarks": len(benchmarks),
            "benchmarkTasks": len(benchmark_tasks),
            "evalRuns": len(eval_runs),
            "evals": await _count({"companyId": company_id, "email": email}, evals_collection),
            "trajectories": len(trajectories),
            "approvedTrajectories": sum(1 for doc in trajectories if str(doc.get("status") or "").lower() in {"approved", "accepted"}),
            "skills": len(skills),
            "readySkills": sum(1 for doc in skills if str(doc.get("status") or "") in {"ready", "approved"}),
            "sessions": len(sessions),
            "artifacts": len(artifacts),
            "pendingApprovals": sum(1 for doc in approvals if str(doc.get("status") or "") == "pending"),
            "approvedApprovals": sum(1 for doc in approvals if str(doc.get("status") or "") == "approved"),
            "workItems": len(work_items),
            "runningWorkItems": sum(1 for doc in work_items if str(doc.get("status") or "") == "RUNNING"),
            "reviewWorkItems": sum(1 for doc in work_items if str(doc.get("status") or "") == "REVIEW"),
        }
        readiness_checks = {
            "profile": bool(str(company.get("name") or "").strip()),
            "systems": counts["connectors"] > 0,
            "credentials": counts["credentials"] > 0,
            "context": counts["resources"] > 0 or counts["entities"] > 0,
            "typedTools": counts["typedTools"] > 0,
            "benchmarks": counts["benchmarkTasks"] > 0,
            "capabilityCoverage": task_contracts_ready > 0 and hardened_skills > 0,
            "skills": counts["readySkills"] > 0,
            "runtime": counts["sessions"] > 0,
            "approvals": counts["pendingApprovals"] > 0 or counts["approvedApprovals"] > 0,
            "domainAllowlist": bool((company.get("embedSettings") or {}).get("allowedOrigins") or connector_domains),
            "resourceAcl": not knowledge_docs or docs_with_acl == len(knowledge_docs),
            "resourceRuntime": not knowledge_docs or runtime_ready_resources == len(knowledge_docs),
            "skillPackages": not skills or skill_packages["publishable"] > 0,
        }
        readiness_gaps = []
        if not readiness_checks["systems"]:
            readiness_gaps.append({"key": "systems", "label": "Connect at least one enterprise system.", "target": "connectors"})
        if counts["connectorsNeedingAuth"] > 0:
            readiness_gaps.append({"key": "auth", "label": f"{counts['connectorsNeedingAuth']} connectors still need authentication.", "target": "credentials"})
        if not readiness_checks["context"]:
            readiness_gaps.append({"key": "context", "label": "Add knowledge resources or mapped business entities.", "target": "knowledge"})
        if not readiness_checks["typedTools"]:
            readiness_gaps.append({"key": "typed_tools", "label": "Publish typed tools with entity mapping and side-effect metadata.", "target": "capabilities"})
        if not readiness_checks["benchmarks"]:
            readiness_gaps.append({"key": "benchmarks", "label": "Create benchmark tasks with success criteria and expected artifacts.", "target": "evals"})
        if counts["benchmarkTasks"] > 0 and task_contracts_ready == 0:
            readiness_gaps.append({"key": "task_contracts", "label": "Add business intent, allowed systems, risk class and expected artifacts to benchmark tasks.", "target": "evals"})
        if not readiness_checks["skills"]:
            readiness_gaps.append({"key": "skills", "label": "Promote at least one hardened, ready skill.", "target": "capabilities"})
        if counts["skills"] > 0 and hardened_skills == 0:
            readiness_gaps.append({"key": "skill_hardening", "label": "Harden skills with activation guidance, instructions, preconditions or expected artifacts.", "target": "capabilities"})
        if counts["skills"] > 0 and skill_packages["publishable"] == 0:
            readiness_gaps.append({"key": "skill_packages", "label": "Complete at least one publishable skill package with IO contract and regression evidence.", "target": "capabilities"})
        if not readiness_checks["runtime"]:
            readiness_gaps.append({"key": "runtime", "label": "Run at least one governed runtime session.", "target": "runtime"})
        if not readiness_checks["domainAllowlist"]:
            readiness_gaps.append({"key": "domains", "label": "Define domain allowlists for browser/embed governance.", "target": "governance"})
        if not readiness_checks["resourceAcl"]:
            readiness_gaps.append({"key": "resource_acl", "label": "Define ACL visibility for every knowledge resource.", "target": "knowledge"})
        if not readiness_checks["resourceRuntime"]:
            readiness_gaps.append({"key": "resource_runtime", "label": "Clear resource runtime blockers before relying on knowledge grounding.", "target": "knowledge"})
        readiness_passed = sum(1 for value in readiness_checks.values() if value)
        readiness_score = round(readiness_passed / len(readiness_checks), 3) if readiness_checks else 0.0

        contract = {
            "integrationContractVersion": "2026-06-25",
            "profile": {
                "companyId": company_id,
                "name": str(company.get("name") or ""),
                "industry": str(company.get("industry") or ""),
                "description": str(company.get("description") or ""),
                "status": str(company.get("status") or "active"),
            },
            "systems": {
                "summary": {
                    "totalConnectors": counts["connectors"],
                    "connectedConnectors": counts["connectedConnectors"],
                    "connectorsNeedingAuth": counts["connectorsNeedingAuth"],
                    "customConnectors": counts["customConnectors"],
                },
                "categoryCoverage": category_counts,
                "surfaceCoverage": surface_counts,
                "connectors": [
                    {
                        "connectorId": str(doc.get("connectorId") or ""),
                        "name": str(doc.get("name") or ""),
                        "type": str(doc.get("type") or ""),
                        "category": str(doc.get("category") or ""),
                        "status": str(doc.get("status") or ""),
                        "provider": str(doc.get("provider") or "official"),
                        "surface": connector_surface(doc),
                        "authRequired": bool(doc.get("authRequired")),
                        "runtimeRequirements": [str(item) for item in doc.get("runtimeRequirements") or [] if item],
                        "domains": _connector_domains(doc),
                    }
                    for doc in connectors
                ],
            },
            "context": {
                "resources": counts["resources"],
                "vectorStores": counts["vectorStores"],
                "entities": counts["entities"],
                "typedTools": counts["typedTools"],
            },
            "systemFactory": {
                "connectorMap": connector_factory,
            },
            "resourceMap": {
                "documents": {
                    "total": resource_summary["total"],
                    "indexed": resource_summary["indexed"],
                    "withResourceContract": resource_summary["withResourceContract"],
                    "withVectorStore": resource_summary["withVectorStore"],
                    "acl": {
                        "withAcl": resource_summary["acl"]["withAcl"],
                        "companyVisible": resource_summary["acl"]["companyVisible"],
                        "restricted": resource_summary["acl"]["restricted"],
                        "visibility": resource_summary["acl"]["visibility"],
                        "roles": resource_summary["acl"]["roles"],
                        "users": resource_summary["acl"]["users"],
                    },
                    "status": resource_summary["status"],
                    "readTools": resource_summary["readTools"],
                    "sample": resource_summary["sample"],
                    "runtimeGate": resource_summary["runtimeGate"],
                },
                "vectorStores": {
                    "total": counts["vectorStores"],
                    "linked": len(resource_vector_ids & vector_store_ids) if vector_store_ids else len(resource_vector_ids),
                    "collections": [
                        str(doc.get("collectionName") or doc.get("name") or doc.get("vectorDatabaseId") or "unknown")
                        for doc in vector_stores[:8]
                    ],
                },
                "gaps": resource_gaps,
            },
            "factory": {
                "agents": counts["agents"],
                "tools": counts["tools"],
                "benchmarks": counts["benchmarks"],
                "benchmarkTasks": counts["benchmarkTasks"],
                "evals": counts["evals"],
                "evalRuns": counts["evalRuns"],
                "trajectories": counts["trajectories"],
                "approvedTrajectories": counts["approvedTrajectories"],
                "skills": counts["skills"],
                "readySkills": counts["readySkills"],
                "publishableSkillPackages": skill_packages["publishable"],
            },
            "runtime": {
                "sessions": counts["sessions"],
                "runtimeKinds": _sorted_counts(runtime_kinds),
                "sessionContracts": session_contracts,
                "artifacts": counts["artifacts"],
                "artifactOutputs": artifact_outputs,
                "pendingApprovals": counts["pendingApprovals"],
                "approvedApprovals": counts["approvedApprovals"],
                "workItems": counts["workItems"],
                "runningWorkItems": counts["runningWorkItems"],
                "reviewWorkItems": counts["reviewWorkItems"],
            },
            "runtimePolicyMap": runtime_policy_map,
            "workOrchestration": {
                "queues": {
                    "total": counts["workItems"],
                    "byStatus": _sorted_counts([str(doc.get("status") or "TODO") for doc in work_items]),
                    "running": counts["runningWorkItems"],
                    "review": counts["reviewWorkItems"],
                    "blockedByApproval": len(review_blocked_items),
                },
                "triggers": {
                    "manual": sum(1 for doc in work_items if str(doc.get("triggerType") or "manual") != "scheduled"),
                    "scheduled": len(scheduled_items),
                    "due": len(due_scheduled_items),
                    "upcoming": len(upcoming_scheduled_items),
                    "frequencies": _sorted_counts([str(doc.get("scheduleFrequency") or "none") for doc in scheduled_items]),
                },
                "budgets": {
                    "budgetedItems": len(budgeted_items),
                    "exhaustedItems": len(exhausted_budget_items),
                    "totalMaxBudgetCredits": round(sum(_safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun"))) for doc in budgeted_items), 4),
                    "latestCreditsSpent": round(sum(_work_latest_credits(doc) for doc in work_items), 4),
                },
                "retries": {
                    "itemsRetried": len(retried_items),
                    "maxRetryCount": max_retry_count,
                    "totalRetryCount": sum(_work_retry_count(doc) for doc in work_items),
                },
                "approvalBoundary": {
                    "pendingApprovals": counts["pendingApprovals"],
                    "workItemsBlocked": len(review_blocked_items),
                    "linkedApprovalWorkItems": len(approval_work_item_ids),
                },
                "sla": {
                    "reviewBlocked": len(review_blocked_items),
                    "scheduledDue": len(due_scheduled_items),
                    "budgetExhausted": len(exhausted_budget_items),
                    "needsAttention": len(review_blocked_items) + len(due_scheduled_items) + len(exhausted_budget_items),
                },
                "contracts": work_contracts,
            },
            "governance": build_company_governance(
                company=company,
                counts=counts,
                connector_domains=connector_domains,
                policy_counts=policy_counts,
                acl_visibility_counts=acl_visibility_counts,
                knowledge_doc_count=len(knowledge_docs),
                docs_with_acl=docs_with_acl,
                company_visible_docs=company_visible_docs,
                restricted_docs=restricted_docs,
            ),
            "integration": build_company_integration_contract(
                company=company,
                owner_email=email,
                counts=counts,
                surface_counts=surface_counts,
                connector_domains=connector_domains,
                policy_counts=policy_counts,
                acl_visibility_counts=acl_visibility_counts,
                knowledge_doc_count=len(knowledge_docs),
                docs_with_acl=docs_with_acl,
            ),
            "capabilityMap": {
                "taskContracts": {
                    "total": counts["benchmarkTasks"],
                    "ready": task_contracts_ready,
                    "coverageRatio": round(task_contracts_ready / counts["benchmarkTasks"], 3) if counts["benchmarkTasks"] else 0.0,
                    "businessIntents": _top_named_items(_sorted_counts([intent for intent in task_business_intents if intent]), name_key="name"),
                    "allowedSystems": task_allowed_systems,
                    "expectedInputs": task_inputs,
                    "expectedArtifacts": task_artifacts,
                    "riskClasses": _sorted_counts(task_risks),
                },
                "benchmarks": {
                    "total": counts["benchmarks"],
                    "verticals": benchmark_verticals,
                    "tasks": counts["benchmarkTasks"],
                    "evalRuns": counts["evalRuns"],
                },
                "evalGate": eval_gate,
                "promotionPipeline": promotion_pipeline,
                "tools": {
                    "total": counts["tools"],
                    "typed": counts["typedTools"],
                    "typedRatio": round(counts["typedTools"] / counts["tools"], 3) if counts["tools"] else 0.0,
                    "sideEffects": side_effects,
                    "mappedEntities": tool_entities[:20],
                },
                "skills": {
                    "total": counts["skills"],
                    "ready": counts["readySkills"],
                    "hardened": hardened_skills,
                    "hardenedRatio": round(hardened_skills / counts["skills"], 3) if counts["skills"] else 0.0,
                    "expectedArtifacts": skill_artifacts,
                    "policies": policy_counts,
                    "packages": skill_packages,
                },
                "gaps": [
                    gap
                    for gap in [
                        {"key": "task_contracts", "label": "No benchmark task has a complete business contract.", "target": "evals"} if counts["benchmarkTasks"] and task_contracts_ready == 0 else None,
                        {"key": "skill_hardening", "label": "Skills exist but none expose enough reusable package metadata.", "target": "capabilities"} if counts["skills"] and hardened_skills == 0 else None,
                        {"key": "skill_packages", "label": "Skills exist but none are publishable packages with IO and regression gates.", "target": "capabilities"} if counts["skills"] and skill_packages["publishable"] == 0 else None,
                        {"key": "tool_entities", "label": "Typed tool/entity mapping is missing or thin.", "target": "capabilities"} if counts["tools"] and counts["typedTools"] == 0 else None,
                        {"key": "expected_artifacts", "label": "No expected business artifacts are declared for task coverage.", "target": "evals"} if counts["benchmarkTasks"] and not task_artifacts else None,
                    ]
                    if gap
                ],
            },
            "readiness": {
                "score": readiness_score,
                "passed": readiness_passed,
                "total": len(readiness_checks),
                "checks": readiness_checks,
                "gaps": readiness_gaps,
            },
        }

        return {
            "company": _serialize(company),
            "contract": contract,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/demo/celeris/reset")
async def reset_celeris_demo(body: DemoResetRequest):
    try:
        agent_docs = await agents_collection.find(
            {"email": body.email, "name": {"$regex": "celer[ií]s|celeris", "$options": "i"}},
            {"_id": 0, "agentId": 1},
        ).to_list(length=100)
        agent_ids = [doc.get("agentId") for doc in agent_docs if doc.get("agentId")]
        if agent_ids:
            await agent_webs_collection.delete_many({"agentId": {"$in": agent_ids}})
            await trajectories_collection.delete_many({"agentId": {"$in": agent_ids}})
            await capabilities_collection.delete_many({"agentId": {"$in": agent_ids}})
            await evals_collection.delete_many({"agentId": {"$in": agent_ids}})
            await eval_runs_collection.delete_many({"agentId": {"$in": agent_ids}})
            await agents_collection.delete_many({"agentId": {"$in": agent_ids}})
        await companies_collection.delete_many(
            {"email": body.email, "name": {"$regex": "celer[ií]s|celeris", "$options": "i"}}
        )
        await connectors_collection.delete_many({"email": body.email, "name": {"$regex": "gmail|holded|telegram|bopa|document", "$options": "i"}})
        return {"success": True, "deletedAgents": len(agent_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
