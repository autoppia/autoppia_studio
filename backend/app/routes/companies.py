import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

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


def _session_runtime_kind(doc: dict[str, Any]) -> str:
    action_history = doc.get("actionHistory") if isinstance(doc.get("actionHistory"), list) else []
    has_browser = any(str(item.get("action") or "").startswith("browser.") for item in action_history if isinstance(item, dict))
    has_connector = any(
        not action.startswith(("browser.", "router.", "runtime.", "user."))
        and action not in {"skill.use", "Initialize", "Continue", ""}
        for action in (str(item.get("action") or "") for item in action_history if isinstance(item, dict))
    )
    if has_browser and has_connector:
        return "hybrid_runtime"
    if has_browser:
        return "browser_runtime"
    return "api_runtime"


def _connector_domains(connector: dict[str, Any]) -> list[str]:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    domains: set[str] = set()
    for key in ("baseUrl", "startUrl", "loginUrl", "docsUrl", "openApiUrl", "sourceUrl"):
        raw = str(config.get(key) or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname:
            domains.add(parsed.hostname.lower())
    return sorted(domains)


def _allowed_origin_hosts(company: dict[str, Any]) -> list[str]:
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    hosts: set[str] = set()
    for origin in settings.get("allowedOrigins") or []:
        raw = str(origin or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return sorted(hosts)


async def _count(query: dict[str, Any], collection: Any) -> int:
    return int(await collection.count_documents(query))


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


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

        runtime_kinds = [_session_runtime_kind(doc) for doc in sessions]
        connected_connectors = [doc for doc in connectors if str(doc.get("status") or "") == "connected"]
        needs_auth_connectors = [doc for doc in connectors if str(doc.get("status") or "") == "needs_auth"]
        custom_connectors = [doc for doc in connectors if str(doc.get("provider") or "") == "custom"]
        connector_domains = sorted({domain for doc in connectors for domain in _connector_domains(doc)})
        category_counts = _sorted_counts([str(doc.get("category") or "uncategorized") for doc in connectors])
        surface_counts = _sorted_counts([connector_surface(doc) for doc in connectors])
        policy_counts = _sorted_counts([str(doc.get("riskPolicy") or "unspecified") for doc in skills])

        counts = {
            "connectors": len(connectors),
            "connectedConnectors": len(connected_connectors),
            "connectorsNeedingAuth": len(needs_auth_connectors),
            "customConnectors": len(custom_connectors),
            "credentials": await _count({"companyId": company_id, "email": email}, credentials_collection),
            "resources": await _count({"companyId": company_id, "email": email}, knowledge_documents_collection),
            "vectorStores": await _count({"companyId": company_id, "email": email}, vector_databases_collection),
            "entities": await _count({"companyId": company_id, "email": email}, entities_collection),
            "agents": await _count({"companyId": company_id, "email": email}, agents_collection),
            "tools": await _count({"companyId": company_id, "email": email}, tools_collection),
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
            "benchmarks": await _count({"companyId": company_id, "email": email}, benchmarks_collection),
            "benchmarkTasks": await _count({"companyId": company_id, "email": email}, benchmark_tasks_collection),
            "evalRuns": await _count({"companyId": company_id, "email": email}, eval_runs_collection),
            "evals": await _count({"companyId": company_id, "email": email}, evals_collection),
            "trajectories": await _count({"companyId": company_id, "email": email}, trajectories_collection),
            "approvedTrajectories": await _count({"companyId": company_id, "email": email, "status": "approved"}, trajectories_collection),
            "skills": len(skills),
            "readySkills": sum(1 for doc in skills if str(doc.get("status") or "") in {"ready", "approved"}),
            "sessions": len(sessions),
            "artifacts": await _count({"companyId": company_id, "email": email}, artifacts_collection),
            "pendingApprovals": await _count({"companyId": company_id, "email": email, "status": "pending"}, approvals_collection),
            "approvedApprovals": await _count({"companyId": company_id, "email": email, "status": "approved"}, approvals_collection),
            "workItems": await _count({"companyId": company_id, "email": email}, work_items_collection),
            "runningWorkItems": await _count({"companyId": company_id, "email": email, "status": "RUNNING"}, work_items_collection),
            "reviewWorkItems": await _count({"companyId": company_id, "email": email, "status": "REVIEW"}, work_items_collection),
        }
        readiness_checks = {
            "profile": bool(str(company.get("name") or "").strip()),
            "systems": counts["connectors"] > 0,
            "credentials": counts["credentials"] > 0,
            "context": counts["resources"] > 0 or counts["entities"] > 0,
            "typedTools": counts["typedTools"] > 0,
            "benchmarks": counts["benchmarkTasks"] > 0,
            "skills": counts["readySkills"] > 0,
            "runtime": counts["sessions"] > 0,
            "approvals": counts["pendingApprovals"] > 0 or counts["approvedApprovals"] > 0,
            "domainAllowlist": bool((company.get("embedSettings") or {}).get("allowedOrigins") or connector_domains),
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
        if not readiness_checks["skills"]:
            readiness_gaps.append({"key": "skills", "label": "Promote at least one hardened, ready skill.", "target": "capabilities"})
        if not readiness_checks["runtime"]:
            readiness_gaps.append({"key": "runtime", "label": "Run at least one governed runtime session.", "target": "runtime"})
        if not readiness_checks["domainAllowlist"]:
            readiness_gaps.append({"key": "domains", "label": "Define domain allowlists for browser/embed governance.", "target": "governance"})
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
            },
            "runtime": {
                "sessions": counts["sessions"],
                "runtimeKinds": _sorted_counts(runtime_kinds),
                "artifacts": counts["artifacts"],
                "pendingApprovals": counts["pendingApprovals"],
                "approvedApprovals": counts["approvedApprovals"],
                "workItems": counts["workItems"],
                "runningWorkItems": counts["runningWorkItems"],
                "reviewWorkItems": counts["reviewWorkItems"],
            },
            "governance": {
                "credentials": counts["credentials"],
                "allowedOrigins": list((company.get("embedSettings") or {}).get("allowedOrigins") or []),
                "allowedOriginHosts": _allowed_origin_hosts(company),
                "hostJwtConfigured": bool(((company.get("embedSettings") or {}).get("hostJwtConfigured")) or ((company.get("embedSettings") or {}).get("hostJwtSecret"))),
                "discoveredDomains": connector_domains,
                "skillPolicies": policy_counts,
            },
            "integration": {
                "systems": counts["connectors"],
                "secrets": counts["credentials"],
                "environments": surface_counts,
                "domainAllowlist": sorted(set(connector_domains + _allowed_origin_hosts(company))),
                "approvalBoundary": {
                    "pending": counts["pendingApprovals"],
                    "approved": counts["approvedApprovals"],
                    "skillPolicies": policy_counts,
                },
                "acl": {
                    "ownerEmail": email,
                    "hostJwtConfigured": bool(((company.get("embedSettings") or {}).get("hostJwtConfigured")) or ((company.get("embedSettings") or {}).get("hostJwtSecret"))),
                    "allowedOrigins": list((company.get("embedSettings") or {}).get("allowedOrigins") or []),
                },
                "compliance": {
                    "browserRestrictedByDomain": bool(connector_domains or (company.get("embedSettings") or {}).get("allowedOrigins")),
                    "humanApprovalConfigured": bool(policy_counts or counts["pendingApprovals"] or counts["approvedApprovals"]),
                    "auditEvidence": {
                        "sessions": counts["sessions"],
                        "artifacts": counts["artifacts"],
                        "evalRuns": counts["evalRuns"],
                    },
                },
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
