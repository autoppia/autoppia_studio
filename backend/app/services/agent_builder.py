from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.database import agents_collection, capabilities_collection, entities_collection, knowledge_documents_collection, tools_collection
from app.runtimes.registry import VALID_RUNTIME_KINDS, default_runtime_profile_payload, normalize_runtime_kind, runtime_descriptor_payload
from app.services.agent_config_contract import build_runtime_spec
from app.services.custom_connector_executors import has_custom_connector_executor
from app.services.resource_governance import resource_payload


DEFAULT_RUNTIME_PROXY_BASE = os.getenv("AUTOMATA_RUNTIME_PROXY_BASE", "http://127.0.0.1:8080").rstrip("/")
RUNTIME_KINDS = ("model_agent", "codex", "claude_code")
VALID_MODEL_PROVIDERS = {"openai", "anthropic", "local", "other"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_profile(kind: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = default_runtime_profile_payload(kind)
    overrides = overrides if isinstance(overrides, dict) else {}
    provider = overrides.get("provider")
    if isinstance(provider, str):
        clean_provider = provider.strip().lower()
        if clean_provider in VALID_MODEL_PROVIDERS:
            profile["provider"] = clean_provider
    for key in ("model", "systemPrompt", "endpoint"):
        value = overrides.get(key)
        if isinstance(value, str) and value.strip():
            profile[key] = value.strip()
    if isinstance(overrides.get("metadata"), dict):
        profile["metadata"] = {**(profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}), **overrides["metadata"]}
    profile["kind"] = kind
    return profile


def _agent_name(company_name: str, kind: str) -> str:
    label = {"model_agent": "Operations Agent", "codex": "Codex Agent", "claude_code": "Claude Code Agent"}.get(kind, "Agent")
    return f"{company_name} {label}".strip()


def _delivery_surfaces(agent_id: str, *, runtime_endpoint: str, kind: str) -> dict[str, Any]:
    api_endpoint = f"/runtime/agents/{agent_id}/step"
    return {
        "chat": {
            "available": True,
            "agentId": agent_id,
            "conversationScope": "company",
        },
        "api": {
            "available": True,
            "agentId": agent_id,
            "endpoint": api_endpoint,
            "runtimeEndpoint": runtime_endpoint,
            "method": "POST",
            "requestSchema": "agent_step/v1",
            "responseSchema": "agent_step_result/v1",
        },
        "widget": {
            "available": True,
            "agentId": agent_id,
            "embedScript": "/embed/v1/widget.js",
            "config": {"agentId": agent_id, "runtimeKind": kind},
        },
    }


def _skill_task(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(skill.get("name") or skill.get("toolName") or "Skill"),
        "prompt": str(skill.get("whenToUse") or skill.get("description") or skill.get("instructions") or ""),
        "successCriteria": str(skill.get("successCriteria") or "Approved skill completes successfully."),
        "status": "verified",
        "trajectoryId": str((skill.get("trajectoryIds") or [""])[0] if isinstance(skill.get("trajectoryIds"), list) and skill.get("trajectoryIds") else ""),
    }


def _skill_callable(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "skill",
        "name": str(skill.get("toolName") or skill.get("name") or skill.get("skillId") or "skill"),
        "description": str(skill.get("description") or skill.get("whenToUse") or ""),
        "capabilityId": str(skill.get("capabilityId") or skill.get("skillId") or ""),
        "trajectoryIds": [str(item) for item in skill.get("trajectoryIds") or [] if item],
        "runtime": str(skill.get("runtime") or "trajectory_replay_with_recovery"),
        "runtimeRequirements": [str(item) for item in skill.get("runtimeRequirements") or [] if item],
        "sideEffects": str(skill.get("sideEffects") or "reads"),
        "riskLevel": str(skill.get("riskLevel") or "low"),
        "inputSchema": skill.get("inputSchema") if isinstance(skill.get("inputSchema"), dict) else {"type": "object", "properties": {"instruction": {"type": "string"}}},
        "approvalPolicy": skill.get("approvalPolicy") if isinstance(skill.get("approvalPolicy"), dict) else {},
        "permissions": skill.get("permissions") if isinstance(skill.get("permissions"), dict) else {},
    }


def _tool_callable(tool: dict[str, Any]) -> dict[str, Any]:
    tool_contract = tool.get("toolContract") if isinstance(tool.get("toolContract"), dict) else {}
    execution_ready = _tool_runtime_ready(tool)
    return {
        "kind": "tool",
        "name": str(tool.get("name") or tool.get("toolName") or tool.get("toolId") or "tool"),
        "description": str(tool.get("description") or ""),
        "connectorId": str(tool.get("connectorId") or ""),
        "executionType": str(tool.get("executionType") or ""),
        "executionReady": execution_ready,
        "implementationRequired": not execution_ready,
        "runtimeRequirements": [str(item) for item in tool.get("runtimeRequirements") or [] if item],
        "sideEffects": str(tool.get("sideEffects") or "reads"),
        "policyBoundary": str(tool.get("policyBoundary") or tool_contract.get("policyBoundary") or "read"),
        "riskLevel": str(tool.get("riskLevel") or "low"),
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {"type": "object", "properties": {}},
        "outputSchema": tool.get("outputSchema") if isinstance(tool.get("outputSchema"), dict) else {"type": "object", "additionalProperties": True},
        "approvalPolicy": tool.get("approvalPolicy") if isinstance(tool.get("approvalPolicy"), dict) else {},
        "permissions": tool.get("permissions") if isinstance(tool.get("permissions"), dict) else {},
        "scopes": [str(item) for item in tool.get("scopes") or [] if item],
        "toolContract": tool_contract,
        "inputEntities": [str(item) for item in tool.get("inputEntities") or [] if item],
        "outputEntity": str(tool.get("outputEntity") or ""),
    }


def _is_custom_connector_tool(tool: dict[str, Any]) -> bool:
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    return bool(metadata.get("customConnector") or tool.get("executorBlueprint"))


def _tool_runtime_ready(tool: dict[str, Any]) -> bool:
    if _is_custom_connector_tool(tool):
        return has_custom_connector_executor(tool)
    return True


async def _skills_for_company(company_id: str, *, benchmark_id: str = "") -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "companyId": company_id,
        "capabilityKind": "skill",
        "status": {"$in": ["ready", "approved", "active", "published", "promoted"]},
    }
    if benchmark_id:
        query["$or"] = [{"benchmarkId": benchmark_id}, {"lineage.benchmarkIds": benchmark_id}]
    cursor = capabilities_collection.find(query, {"_id": 0}).sort("updatedAt", -1)
    return await cursor.to_list(length=500)


async def _tools_for_company(company_id: str) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "companyId": company_id,
        "status": {"$in": ["candidate", "ready", "active", "published", "approved"]},
    }
    cursor = tools_collection.find(query, {"_id": 0}).sort("updatedAt", -1)
    return await cursor.to_list(length=500)


async def _resources_for_company(company_id: str) -> list[dict[str, Any]]:
    cursor = knowledge_documents_collection.find({"companyId": company_id}, {"_id": 0, "storagePath": 0}).sort("updatedAt", -1)
    docs = await cursor.to_list(length=500)
    resources = [resource_payload(doc) for doc in docs]
    resources.sort(key=lambda item: (not bool(item.get("indexed")), str(item.get("name") or "")))
    return resources


def _entity_graph_payload(docs: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {
            "id": str(doc.get("name") or ""),
            "entityId": str(doc.get("entityId") or ""),
            "name": str(doc.get("name") or ""),
            "description": str(doc.get("description") or ""),
            "fields": doc.get("fields") if isinstance(doc.get("fields"), list) else [],
            "sourceConnectorId": str(doc.get("sourceConnectorId") or ""),
            "source": str(doc.get("source") or "manual"),
            "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
        }
        for doc in docs
    ]
    edges: list[dict[str, Any]] = []
    for doc in docs:
        source = str(doc.get("name") or "")
        for rel in doc.get("relationships") or []:
            if not isinstance(rel, dict):
                continue
            target = str(rel.get("target") or "").strip()
            if source and target:
                edges.append(
                    {
                        "from": source,
                        "to": target,
                        "name": str(rel.get("name") or ""),
                        "kind": str(rel.get("kind") or "references"),
                        "via": str(rel.get("via") or ""),
                        "description": str(rel.get("description") or ""),
                    }
                )
    return {"nodes": nodes, "edges": edges}


async def _entities_for_company(company_id: str) -> dict[str, Any]:
    cursor = entities_collection.find({"companyId": company_id}, {"_id": 0}).sort("name", 1)
    docs = await cursor.to_list(length=500)
    return _entity_graph_payload(docs)


def _training_status(
    *,
    skills: list[dict[str, Any]],
    executable_tools: list[dict[str, Any]],
    missing_tool_executors: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> str:
    if skills:
        return "verified"
    if executable_tools:
        return "tools_ready"
    if any(bool(resource.get("indexed")) for resource in resources):
        return "knowledge_ready"
    if resources:
        return "knowledge_pending"
    if missing_tool_executors:
        return "connector_implementation_required"
    return "needs_skills"


async def build_company_agents(
    *,
    email: str,
    company_id: str,
    company_name: str = "",
    benchmark_id: str = "",
    runtime_kinds: list[str] | None = None,
    runtime_profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kinds = []
    for item in runtime_kinds or list(RUNTIME_KINDS):
        kind = normalize_runtime_kind(item)
        if kind in VALID_RUNTIME_KINDS and kind not in kinds:
            kinds.append(kind)
    if not kinds:
        kinds = ["model_agent"]
    skills = await _skills_for_company(company_id, benchmark_id=benchmark_id)
    tools = await _tools_for_company(company_id)
    resources = await _resources_for_company(company_id)
    entities = await _entities_for_company(company_id)
    now = now_iso()
    skill_callables = [_skill_callable(skill) for skill in skills]
    tool_callables = [_tool_callable(tool) for tool in tools]
    executable_tools = [tool for tool in tools if _tool_runtime_ready(tool)]
    missing_tool_executors = [tool for tool in tools if not _tool_runtime_ready(tool)]
    tasks = [_skill_task(skill) for skill in skills]
    has_runtime_inventory = bool(skill_callables or executable_tools or resources)
    training_status = _training_status(
        skills=skills,
        executable_tools=executable_tools,
        missing_tool_executors=missing_tool_executors,
        resources=resources,
    )
    runtime_profiles = runtime_profiles if isinstance(runtime_profiles, dict) else {}
    agent_ids: list[str] = []
    agents: list[dict[str, Any]] = []
    for kind in kinds:
        agent_id = f"{company_id}:agent:{kind}"
        runtime_profile = _runtime_profile(kind, runtime_profiles.get(kind))
        runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step"
        delivery_surfaces = _delivery_surfaces(agent_id, runtime_endpoint=runtime_endpoint, kind=kind)
        runtime_spec = build_runtime_spec(
            browser_enabled=True,
            browser_mode="headless",
            max_credits_per_run=5.0,
            existing_tools={"connectors": True, "skills": True, "knowledge": True},
            existing_spec={"approvalRequiredFor": ["write", "send"]},
        )
        doc = {
            "agentId": agent_id,
            "agentConfigId": agent_id,
            "email": email,
            "companyId": company_id,
            "name": _agent_name(company_name or "Company", kind),
            "websiteUrl": "",
            "runtimeEndpoint": runtime_endpoint,
            "baseRuntimeEndpoint": "",
            "runtimeType": "company_agent",
            "runtimeKind": kind,
            "runtimeProfile": runtime_profile,
            "runtimeDescriptor": runtime_descriptor_payload(kind),
            "status": "ready" if has_runtime_inventory else "draft",
            "trainingStatus": training_status,
            "runtimeReadiness": {
                "executableToolCount": len(executable_tools),
                "missingToolExecutorCount": len(missing_tool_executors),
                "missingToolNames": [str(tool.get("name") or tool.get("toolName") or tool.get("toolId") or "") for tool in missing_tool_executors],
            },
            "runtimeCapabilities": {"browser": True, "apiCalls": True, "knowledge": True, "python": kind == "codex", "humanApprovalForWrites": True},
            "runtimeSpec": runtime_spec,
            "capabilityDiscovery": {"mode": "company_harvest", "benchmarkId": benchmark_id},
            "tasks": tasks,
            "skills": skill_callables,
            "tools": tool_callables,
            "entities": entities,
            "resources": resources,
            "knowledge": resources,
            "deliverySurfaces": delivery_surfaces,
            "riskPolicy": {"writesRequireApproval": True},
            "source": "company_agent_builder",
            "generatedFrom": {
                "companyId": company_id,
                "benchmarkId": benchmark_id,
                "skillIds": [str(skill.get("capabilityId") or skill.get("skillId") or "") for skill in skills],
                "toolIds": [str(tool.get("toolId") or "") for tool in tools],
                "resourceIds": [str(resource.get("resourceId") or resource.get("documentId") or "") for resource in resources],
                "entityIds": [str(node.get("entityId") or "") for node in entities.get("nodes", []) if node.get("entityId")],
            },
            "updatedAt": now,
        }
        existing = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
        doc["createdAt"] = (existing or {}).get("createdAt") or now
        await agents_collection.update_one({"agentId": agent_id}, {"$set": doc}, upsert=True)
        agent_ids.append(agent_id)
        agents.append(doc)
    return {
        "companyId": company_id,
        "benchmarkId": benchmark_id,
        "skillCount": len(skills),
        "toolCount": len(tools),
        "executableToolCount": len(executable_tools),
        "missingToolExecutorCount": len(missing_tool_executors),
        "resourceCount": len(resources),
        "entityCount": len(entities.get("nodes", [])),
        "agentCount": len(agent_ids),
        "agentIds": agent_ids,
        "agents": agents,
    }
