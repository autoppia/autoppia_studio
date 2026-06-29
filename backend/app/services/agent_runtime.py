from __future__ import annotations

import os
import re
import logging
from typing import Any
from urllib.parse import quote_plus

import httpx
from fastapi import HTTPException

from app.connectors import ConnectorExecutionError, execute_connector_tool
from app.database import (
    agents_collection,
    benchmark_tasks_collection,
    capabilities_collection,
    connectors_collection,
    entities_collection,
    knowledge_documents_collection,
    tools_collection,
    trajectories_collection,
)
from app.models.agent_config import AgentCallable, AgentConfig
from app.runtimes.base import AgentRuntimeContext
from app.runtimes.external_step import step_url
from app.runtimes.registry import get_runtime_adapter, normalize_runtime_kind, runtime_catalog_payload, runtime_descriptor_payload
from app.services.approvals import create_pending_approval, stable_approval_key
from app.services.agent_config_contract import control_plane_separation_gate
from app.services.custom_connector_executors import custom_connector_executor_name, execute_custom_connector_tool, has_custom_connector_executor
from app.services.metering import record_usage
from app.services.observability import record_runtime_event
from app.services.resource_governance import resource_payload
from app.services.runtime_policy import ordered_policy_boundaries
from app.services.runtime_policy import browser_enabled as _runtime_policy_browser_enabled
from app.services.runtime_policy import browser_runtime_policy, enterprise_runtime_policy
from app.services.skill_packages import summarize_skill_packages


DEFAULT_BASE_RUNTIME_ENDPOINT = os.getenv("AUTOMATA_DEFAULT_RUNTIME_ENDPOINT", "http://127.0.0.1:5060/step").strip()
logger = logging.getLogger(__name__)


def _runtime_kind(value: Any) -> str:
    return normalize_runtime_kind(value)


def _runtime_adapter_context(agent_config: dict[str, Any], capability_context: dict[str, Any]) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        agentConfig=agent_config,
        tools=capability_context.get("tools") if isinstance(capability_context.get("tools"), list) else [],
        skills=capability_context.get("skills") if isinstance(capability_context.get("skills"), list) else [],
        resources=capability_context.get("resources") if isinstance(capability_context.get("resources"), list) else [],
        entities=capability_context.get("entities") if isinstance(capability_context.get("entities"), dict) else {},
        metadata={
            "defaultEndpoint": DEFAULT_BASE_RUNTIME_ENDPOINT,
            "httpClientFactory": httpx.AsyncClient,
            "timeoutSeconds": 45.0,
        },
    )


async def _record_usage_event(**kwargs: Any) -> None:
    try:
        await record_usage(**kwargs)
    except Exception:
        logger.exception("Failed to record usage event")


async def load_agent_config(agent_id: str) -> dict[str, Any]:
    agent = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def serialize_agent(doc: dict[str, Any]) -> dict[str, Any]:
    agent_id = doc.get("agentId", "")
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "name": doc.get("name", ""),
        "websiteUrl": doc.get("websiteUrl", ""),
        "runtimeEndpoint": doc.get("runtimeEndpoint", ""),
        "baseRuntimeEndpoint": doc.get("baseRuntimeEndpoint", ""),
        "runtimeType": doc.get("runtimeType", ""),
        "runtimeKind": _runtime_kind(doc.get("runtimeKind")),
        "runtimeProfile": doc.get("runtimeProfile") or {"kind": _runtime_kind(doc.get("runtimeKind"))},
        "runtimeDescriptor": runtime_descriptor_payload(doc.get("runtimeKind")),
        "status": doc.get("status", ""),
        "trainingStatus": doc.get("trainingStatus", ""),
        "runtimeCapabilities": doc.get("runtimeCapabilities") or {},
        "runtimeSpec": doc.get("runtimeSpec") or {},
        "capabilityDiscovery": doc.get("capabilityDiscovery") or {"mode": "task_scoped"},
        "tasks": doc.get("tasks") or [],
        "successCriteria": doc.get("successCriteria", ""),
        "apiSpecUrl": doc.get("apiSpecUrl", ""),
        "apiAuthConfigured": bool(doc.get("apiAuth", {}).get("headerValueConfigured")),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _tool_callable(doc: dict[str, Any]) -> dict[str, Any]:
    return AgentCallable(
        kind="tool",
        name=str(doc.get("name") or ""),
        description=str(doc.get("description") or ""),
        inputSchema=doc.get("inputSchema") or {"type": "object", "properties": {}},
        outputSchema=doc.get("outputSchema") or {"type": "object", "additionalProperties": True},
        sideEffects=str(doc.get("sideEffects") or "reads"),
        policyBoundary=str(doc.get("policyBoundary") or (doc.get("toolContract") or {}).get("policyBoundary") or "read"),
        riskLevel=str(doc.get("riskLevel") or "low"),
        source=str(doc.get("source") or ""),
        connectorId=str(doc.get("connectorId") or ""),
        executionType=str(doc.get("executionType") or ""),
        executionReady=bool(doc.get("executionReady", True)),
        implementationRequired=bool(doc.get("implementationRequired", False)),
        runtimeRequirements=[str(item) for item in doc.get("runtimeRequirements") or [] if item],
        permissions=doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {},
        approvalPolicy=doc.get("approvalPolicy") if isinstance(doc.get("approvalPolicy"), dict) else {},
        scopes=[str(item) for item in doc.get("scopes") or [] if item],
        toolContract=doc.get("toolContract") if isinstance(doc.get("toolContract"), dict) else {},
        inputEntities=[str(item) for item in doc.get("inputEntities") or [] if item],
        outputEntity=str(doc.get("outputEntity") or ""),
        outputCard=doc.get("outputCard") if isinstance(doc.get("outputCard"), dict) else {},
    ).model_dump()


def _skill_callable(doc: dict[str, Any]) -> dict[str, Any]:
    name = str(doc.get("toolName") or doc.get("name") or doc.get("skillId") or "skill").strip()
    if "." not in name:
        name = f"skill.{re.sub(r'[^a-zA-Z0-9_]+', '_', name).strip('_').lower()}"
    skill_package = doc.get("skillPackage") if isinstance(doc.get("skillPackage"), dict) else {}
    skill_policies = skill_package.get("policies") if isinstance(skill_package.get("policies"), dict) else {}
    runtime_policy = skill_policies.get("runtimePolicy") if isinstance(skill_policies.get("runtimePolicy"), dict) else {}
    return AgentCallable(
        kind="skill",
        name=name,
        description=str(doc.get("description") or doc.get("whenToUse") or ""),
        inputSchema=doc.get("inputSchema") or {"type": "object", "properties": {"instruction": {"type": "string"}}},
        outputSchema=doc.get("outputSchema") or {"type": "object", "additionalProperties": True},
        sideEffects=str(doc.get("sideEffects") or "reads"),
        policyBoundary=str(doc.get("policyBoundary") or runtime_policy.get("primaryBoundary") or "read"),
        riskLevel=str(doc.get("riskLevel") or "medium"),
        source=str(doc.get("source") or "skill_registry"),
        capabilityId=str(doc.get("capabilityId") or doc.get("skillId") or ""),
        trajectoryIds=[str(item) for item in doc.get("trajectoryIds") or []],
        runtime=str(doc.get("runtime") or ""),
        runtimeRequirements=[str(item) for item in doc.get("runtimeRequirements") or [] if item],
        permissions=doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {},
        approvalPolicy=doc.get("approvalPolicy") if isinstance(doc.get("approvalPolicy"), dict) else {},
        scopes=[str(item) for item in doc.get("scopes") or [] if item],
        toolContract=doc.get("toolContract") if isinstance(doc.get("toolContract"), dict) else {},
        inputEntities=[str(item) for item in doc.get("inputEntities") or [] if item],
        outputEntity=str(doc.get("outputEntity") or ""),
        outputCard=doc.get("outputCard") if isinstance(doc.get("outputCard"), dict) else {},
    ).model_dump()


def _agent_config_payload(agent_config: dict[str, Any], context: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    runtime_capabilities = agent_config.get("runtimeCapabilities") or {}
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    if not runtime_spec:
        browser_enabled = bool(runtime_capabilities.get("browser", True))
        runtime_spec = {
            "browserEnabled": browser_enabled,
            "browserMode": str(agent_config.get("browserMode") or "visible"),
            "maxCreditsPerRun": float(agent_config.get("maxCreditsPerRun") or 5.0),
            "tools": {
                "browser": browser_enabled,
                "connectors": True,
                "skills": True,
                "knowledge": bool(runtime_capabilities.get("knowledge", False)),
            },
        }
    payload = AgentConfig(
        agentId=str(agent_config.get("agentId") or ""),
        name=str(agent_config.get("name") or ""),
        email=str(agent_config.get("email") or ""),
        companyId=str(agent_config.get("companyId") or ""),
        websiteUrl=str(agent_config.get("websiteUrl") or ""),
        runtimeEndpoint=str(agent_config.get("runtimeEndpoint") or ""),
        baseRuntimeEndpoint=str(agent_config.get("baseRuntimeEndpoint") or ""),
        runtimeType=str(agent_config.get("runtimeType") or "generalist_with_company_capabilities"),
        runtimeKind=_runtime_kind(agent_config.get("runtimeKind")),
        runtimeProfile=agent_config.get("runtimeProfile") if isinstance(agent_config.get("runtimeProfile"), dict) else {"kind": _runtime_kind(agent_config.get("runtimeKind"))},
        status=str(agent_config.get("status") or "draft"),
        trainingStatus=str(agent_config.get("trainingStatus") or "not_started"),
        runtimeCapabilities=runtime_capabilities,
        runtimeSpec=runtime_spec,
        capabilityDiscovery=agent_config.get("capabilityDiscovery") if isinstance(agent_config.get("capabilityDiscovery"), dict) else {"mode": "task_scoped"},
        tasks=agent_config.get("tasks") or [],
        tools=[_tool_callable(tool) for tool in context.get("tools") or []],
        skills=[_skill_callable(skill) for skill in context.get("skills") or []],
        entities=context.get("entities") if isinstance(context.get("entities"), dict) else {},
        resources=context.get("resources") if isinstance(context.get("resources"), list) else [],
        knowledge=context.get("resources") if isinstance(context.get("resources"), list) else [],
        deliverySurfaces=agent_config.get("deliverySurfaces") if isinstance(agent_config.get("deliverySurfaces"), dict) else {},
        memory=memory,
        riskPolicy={"writesRequireApproval": bool((agent_config.get("runtimeCapabilities") or {}).get("humanApprovalForWrites", True))},
        createdAt=agent_config.get("createdAt"),
        updatedAt=agent_config.get("updatedAt"),
    )
    data = payload.model_dump()
    data["runtimeDescriptor"] = runtime_descriptor_payload(data.get("runtimeKind"))
    return data


def _apply_runtime_overrides(agent_config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    overrides = context.get("runtimeOverrides") if isinstance(context.get("runtimeOverrides"), dict) else {}
    if not overrides:
        return agent_config

    updated = dict(agent_config)
    runtime_spec = dict(updated.get("runtimeSpec") if isinstance(updated.get("runtimeSpec"), dict) else {})
    runtime_capabilities = dict(updated.get("runtimeCapabilities") if isinstance(updated.get("runtimeCapabilities"), dict) else {})
    tools = dict(runtime_spec.get("tools") if isinstance(runtime_spec.get("tools"), dict) else {})

    if "browserEnabled" in overrides:
        browser_enabled = bool(overrides.get("browserEnabled"))
        runtime_spec["browserEnabled"] = browser_enabled
        tools["browser"] = browser_enabled
        runtime_capabilities["browser"] = browser_enabled
    if str(overrides.get("browserMode") or "") in {"visible", "headless"}:
        runtime_spec["browserMode"] = str(overrides["browserMode"])
    if "maxCreditsPerRun" in overrides or "maxCredits" in overrides:
        raw_credits = overrides.get("maxCreditsPerRun", overrides.get("maxCredits"))
        try:
            runtime_spec["maxCreditsPerRun"] = max(0.0, float(raw_credits))
        except (TypeError, ValueError):
            pass

    runtime_spec["tools"] = tools
    updated["runtimeSpec"] = runtime_spec
    updated["runtimeCapabilities"] = runtime_capabilities
    return updated


async def _capability_context(agent_config: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {"agentId": agent_config.get("agentId", "")}
    company_id = str(agent_config.get("companyId") or "")
    if company_id:
        query = {"$or": [query, {"companyId": company_id}]}

    skills = await capabilities_collection.find(
        {**query, "capabilityKind": "skill"} if "$or" not in query else {"$and": [query, {"capabilityKind": "skill"}]},
        {"_id": 0},
    ).to_list(length=200)
    tools = []
    if company_id:
        tools = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    skill_tools = [_skill_callable(skill) for skill in skills]
    tool_callables = [_tool_callable(tool) for tool in tools]
    callables = tool_callables + skill_tools
    entity_graph = await _entity_context(company_id, callables) if company_id else {}
    resources = await _resource_context(company_id) if company_id else []
    return {"skills": skills, "tools": tools, "entities": entity_graph, "resources": resources, "callables": callables}


async def _resource_context(company_id: str) -> list[dict[str, Any]]:
    docs = await knowledge_documents_collection.find(
        {"companyId": company_id},
        {"_id": 0, "storagePath": 0},
    ).to_list(length=200)
    resources = [resource_payload(doc) for doc in docs]
    resources.sort(key=lambda item: (not bool(item.get("indexed")), str(item.get("name") or "")))
    return resources


def _callable_entity_names(callables: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in callables:
        output_entity = str(item.get("outputEntity") or "").strip()
        if output_entity:
            names.add(output_entity)
        for entity in item.get("inputEntities") or []:
            clean = str(entity or "").strip()
            if clean:
                names.add(clean)
    return names


def _entity_graph_payload(docs: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {
            "id": doc.get("name", ""),
            "entityId": doc.get("entityId", ""),
            "name": doc.get("name", ""),
            "description": doc.get("description", ""),
            "fields": doc.get("fields") if isinstance(doc.get("fields"), list) else [],
            "sourceConnectorId": doc.get("sourceConnectorId", ""),
            "source": doc.get("source", "manual"),
        }
        for doc in docs
    ]
    edges = []
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
                        "name": rel.get("name", ""),
                        "kind": rel.get("kind", "references"),
                        "via": rel.get("via", ""),
                        "description": rel.get("description", ""),
                    }
                )
    return {"nodes": nodes, "edges": edges}


async def _entity_context(company_id: str, callables: list[dict[str, Any]]) -> dict[str, Any]:
    names = _callable_entity_names(callables)
    if not names:
        return {"nodes": [], "edges": []}

    docs = await entities_collection.find({"companyId": company_id, "name": {"$in": sorted(names)}}, {"_id": 0}).to_list(length=200)
    related_names = set(names)
    for doc in docs:
        for rel in doc.get("relationships") or []:
            if isinstance(rel, dict) and str(rel.get("target") or "").strip():
                related_names.add(str(rel.get("target")).strip())

    if related_names != names:
        docs = await entities_collection.find({"companyId": company_id, "name": {"$in": sorted(related_names)}}, {"_id": 0}).to_list(length=300)
    docs.sort(key=lambda item: str(item.get("name") or ""))
    return _entity_graph_payload(docs)


async def runtime_contract_payload(agent_config: dict[str, Any]) -> dict[str, Any]:
    context = await _capability_context(agent_config)
    tool_callables = annotate_runtime_availability(agent_config, [_tool_callable(tool) for tool in context["tools"]])
    skill_callables = annotate_runtime_availability(agent_config, [_skill_callable(skill) for skill in context["skills"]])
    skill_packages = summarize_skill_packages(context["skills"])
    resources = context.get("resources") if isinstance(context.get("resources"), list) else []
    browser_tools = [
        "browser.navigate",
        "browser.snapshot",
        "browser.click",
        "browser.input",
        "browser.select_option",
        "browser.select_dropdown",
        "browser.send_keys",
        "browser.wait",
        "browser.done",
    ]
    base_tools = [
        {"name": name, "kind": "browser", "runtimeAvailability": runtime_requirement_status(agent_config, ["browser"])}
        for name in browser_tools
    ]
    human_approval = {
        "name": "api.human_approval",
        "kind": "control",
        "runtimeAvailability": runtime_requirement_status(agent_config, ["human_approval"]),
    }
    all_tools = [*base_tools, human_approval, *tool_callables, *skill_callables]
    governed_tools = [tool for tool in tool_callables if isinstance(tool.get("toolContract"), dict) and tool["toolContract"]]
    approval_tools = [
        tool.get("name", "")
        for tool in tool_callables
        if isinstance(tool.get("approvalPolicy"), dict) and tool["approvalPolicy"].get("required")
    ]
    risk_counts: dict[str, int] = {}
    for tool in tool_callables:
        risk = str(tool.get("riskLevel") or "unknown").lower()
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    return {
        "runtimeKind": _runtime_kind(agent_config.get("runtimeKind")),
        "runtimeProfile": agent_config.get("runtimeProfile") if isinstance(agent_config.get("runtimeProfile"), dict) else {"kind": _runtime_kind(agent_config.get("runtimeKind"))},
        "runtimeDescriptor": runtime_descriptor_payload(agent_config.get("runtimeKind")),
        "runtimeAdapters": runtime_catalog_payload(),
        "runtimeCapabilities": agent_config.get("runtimeCapabilities") or {},
        "runtimeSpec": agent_config.get("runtimeSpec") or {},
        "controlPlaneSeparationGate": control_plane_separation_gate(
            agent_config,
            tools=tool_callables,
            skills=skill_callables,
            resources=resources,
        ),
        "browserPolicy": browser_runtime_policy(agent_config),
        "enterpriseRuntime": enterprise_runtime_policy(
            agent_config,
            tools=tool_callables,
            skills=skill_callables,
            resources=resources,
        ),
        "entities": context.get("entities") if isinstance(context.get("entities"), dict) else {},
        "resources": resources,
        "resourceGrounding": {
            "total": len(resources),
            "indexed": sum(1 for item in resources if item.get("indexed")),
            "citable": sum(1 for item in resources if item.get("citable")),
            "readTools": sorted({tool for item in resources for tool in (item.get("readTools") or [])}),
        },
        "toolGovernance": {
            "total": len(tool_callables),
            "governed": len(governed_tools),
            "approvalRequiredTools": approval_tools,
            "riskCounts": risk_counts,
            "policyBoundaries": sorted({str(tool.get("policyBoundary") or "read") for tool in tool_callables}),
        },
        "tools": tool_callables,
        "skills": skill_callables,
        "skillPackages": skill_packages,
        "toolCalls": [item["name"] for item in all_tools if item.get("runtimeAvailability", {}).get("available", True)],
        "unavailableToolCalls": [
            {"name": item["name"], "runtimeAvailability": item.get("runtimeAvailability", {})}
            for item in all_tools
            if not item.get("runtimeAvailability", {}).get("available", True)
        ],
    }


def _runtime_feature_enabled(agent_config: dict[str, Any], feature: str) -> bool:
    feature = feature.strip().lower()
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    runtime_tools = runtime_spec.get("tools") if isinstance(runtime_spec.get("tools"), dict) else {}
    runtime_classes = {str(item).strip().lower() for item in runtime_spec.get("runtimeClasses") or [] if str(item).strip()}
    capabilities = agent_config.get("runtimeCapabilities") if isinstance(agent_config.get("runtimeCapabilities"), dict) else {}

    if feature == "browser":
        return _browser_enabled(agent_config) and (not runtime_classes or "browser_runtime" in runtime_classes)
    if feature in {"browser_runtime", "computer_use", "web_runtime", "display"}:
        return _browser_enabled(agent_config) and (not runtime_classes or "browser_runtime" in runtime_classes)
    if feature in {"connector_runtime", "connectors", "connector_tools", "tool_runtime"}:
        return bool(runtime_tools.get("connectors", True)) and (not runtime_classes or "connector_runtime" in runtime_classes)
    if feature in {"skill_runtime", "skills", "skill_tool", "trajectory_replay"}:
        return bool(runtime_tools.get("skills", True)) and (not runtime_classes or "skill_runtime" in runtime_classes)
    if feature in {"hybrid_runtime"}:
        return (
            _runtime_feature_enabled(agent_config, "browser_runtime")
            and (_runtime_feature_enabled(agent_config, "connector_runtime") or _runtime_feature_enabled(agent_config, "skill_runtime"))
            and (not runtime_classes or "hybrid_runtime" in runtime_classes)
        )
    if feature in {"network", "http", "api", "api_calls", "api_credentials", "api_credentials_optional", "openapi_optional", "api_docs_or_openapi"}:
        if runtime_classes and "api_runtime" not in runtime_classes:
            return False
        if "network" in capabilities:
            return bool(capabilities.get("network"))
        if "apiCalls" in capabilities:
            return bool(capabilities.get("apiCalls"))
        if "connectors" in runtime_tools:
            return bool(runtime_tools.get("connectors"))
        return True
    if feature in {"knowledge", "vectorstore", "embedding_model", "knowledge_source"}:
        return bool(capabilities.get("knowledge") or runtime_tools.get("knowledge"))
    if feature in {"python", "code"}:
        return bool(capabilities.get("python"))
    if feature in {"human_approval", "human_approval_for_writes"}:
        if isinstance(runtime_spec.get("approvalRequiredFor"), list):
            return bool(ordered_policy_boundaries(runtime_spec.get("approvalRequiredFor") or []))
        return bool(capabilities.get("humanApprovalForWrites", True))
    if feature.endswith("_credentials") or "credentials" in feature or feature.startswith("oauth:") or feature in {"bot_token", "smtp_credentials"}:
        return bool(runtime_tools.get("connectors", True))
    return bool(capabilities.get(feature, True))


def runtime_requirement_status(agent_config: dict[str, Any], requirements: list[Any] | None) -> dict[str, Any]:
    required = [str(item).strip() for item in requirements or [] if str(item).strip()]
    unavailable = [item for item in required if not _runtime_feature_enabled(agent_config, item)]
    runtime_spec = agent_config.get("runtimeSpec") if isinstance(agent_config.get("runtimeSpec"), dict) else {}
    return {
        "required": required,
        "available": not unavailable,
        "unavailable": unavailable,
        "runtimeClasses": runtime_spec.get("runtimeClasses") if isinstance(runtime_spec.get("runtimeClasses"), list) else [],
    }


def annotate_runtime_availability(agent_config: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = []
    for item in items:
        status = runtime_requirement_status(agent_config, item.get("runtimeRequirements") or [])
        annotated.append({**item, "runtimeAvailability": status, "available": status["available"]})
    return annotated


def _require_runtime_available(agent_config: dict[str, Any], name: str, requirements: list[Any] | None) -> dict[str, Any] | None:
    status = runtime_requirement_status(agent_config, requirements)
    if status["available"]:
        return None
    return {
        "tool": name,
        "success": False,
        "error": f"Runtime requirements unavailable: {', '.join(status['unavailable'])}",
        "runtimeAvailability": status,
    }


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]{4,}", value.lower()) if token}


ROUTER_STOPWORDS = {
    "para", "sobre", "with", "from", "that", "this", "este", "esta", "estos", "estas",
    "email", "mail", "correo", "task", "agent", "using", "hacer", "busca", "buscar",
    "reciente", "ultimo", "último", "resume", "resumen", "respuesta", "cliente",
}


def _router_tokens(value: str) -> set[str]:
    return {token for token in _tokens(value) if token not in ROUTER_STOPWORDS}


def _skill_route_text(skill: dict[str, Any]) -> str:
    task_text = " ".join(
        str(item.get(key) or "")
        for item in skill.get("tasks") or []
        if isinstance(item, dict)
        for key in ("name", "prompt", "successCriteria")
    )
    return " ".join(
        str(skill.get(key) or "")
        for key in ("name", "description", "whenToUse", "runtime", "source", "successCriteria", "taskName", "prompt")
    ) + " " + task_text


def _skill_route_items(skill: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, task in enumerate(skill.get("tasks") or []):
        if not isinstance(task, dict):
            continue
        text = str(task.get("prompt") or "").strip()
        if not text:
            text = " ".join(str(task.get(key) or "") for key in ("name", "successCriteria"))
        if text.strip():
            items.append({
                "source": "task",
                "name": str(task.get("name") or task.get("taskId") or f"Task {index + 1}"),
                "text": text,
            })
    top_level_task = str(skill.get("prompt") or "").strip()
    if not top_level_task:
        top_level_task = " ".join(str(skill.get(key) or "") for key in ("taskName", "successCriteria"))
    if top_level_task.strip():
        items.append({"source": "task", "name": str(skill.get("taskName") or skill.get("name") or "Linked task"), "text": top_level_task})
    skill_text = _skill_route_text(skill)
    if skill_text.strip():
        items.append({"source": "skill", "name": str(skill.get("name") or "Skill"), "text": skill_text})
    return items


def _skill_route_status(skill: dict[str, Any]) -> bool:
    status = str(skill.get("status") or "").lower()
    if status and status not in {"approved", "ready", "active", "published", "promoted"}:
        return False
    return bool(skill.get("trajectoryIds") or skill.get("trajectoryId"))


def _skill_route_candidate(prompt: str, skill: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = _router_tokens(prompt)
    route_items = _skill_route_items(skill)
    best_item: dict[str, Any] = {"source": "", "name": "", "text": "", "tokens": set(), "overlap": set(), "score": 0.0, "promptCoverage": 0.0, "skillCoverage": 0.0}
    for item in route_items:
        item_tokens = _router_tokens(item["text"])
        overlap = prompt_tokens & item_tokens if prompt_tokens else set()
        prompt_coverage = len(overlap) / max(1, len(prompt_tokens))
        item_coverage = len(overlap) / max(1, len(item_tokens))
        score = min(prompt_coverage, item_coverage) if item_tokens else 0.0
        candidate_item = {
            **item,
            "tokens": item_tokens,
            "overlap": overlap,
            "score": score,
            "promptCoverage": prompt_coverage,
            "skillCoverage": item_coverage,
        }
        if (score, len(overlap), item.get("source") == "task") > (
            float(best_item["score"]),
            len(best_item["overlap"]),
            best_item.get("source") == "task",
        ):
            best_item = candidate_item
    overlap = best_item["overlap"]
    prompt_coverage = len(overlap) / max(1, len(prompt_tokens))
    skill_coverage = float(best_item["skillCoverage"])
    score = float(best_item["score"])
    return {
        "skillId": str(skill.get("capabilityId") or skill.get("skillId") or ""),
        "name": str(skill.get("name") or ""),
        "status": str(skill.get("status") or ""),
        "matchedRouteSource": str(best_item.get("source") or ""),
        "matchedRouteName": str(best_item.get("name") or ""),
        "hasTaskRoute": any(item.get("source") == "task" for item in route_items),
        "overlap": sorted(overlap),
        "overlapCount": len(overlap),
        "promptCoverage": round(prompt_coverage, 3),
        "skillCoverage": round(skill_coverage, 3),
        "score": round(score, 3),
        "hasApprovedTrajectoryRef": _skill_route_status(skill),
        "skill": skill,
    }


async def _skill_has_executable_trajectory(skill: dict[str, Any]) -> tuple[bool, str]:
    trajectory = await _load_skill_trajectory(skill)
    if not trajectory:
        return False, "Skill has no linked trajectory."
    status = str(trajectory.get("status") or "").lower()
    actions = trajectory.get("trajectory") or trajectory.get("actions") or trajectory.get("steps") or []
    if status != "approved":
        return False, f"Linked trajectory status is {status or 'unknown'}, not approved."
    if not isinstance(actions, list) or not actions:
        return False, "Linked trajectory has no executable steps."
    return True, f"Approved trajectory {trajectory.get('trajectoryId') or ''} with {len(actions)} step(s)."


async def _route_skill_match(prompt: str, skills: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [_skill_route_candidate(prompt, skill) for skill in skills]
    candidates.sort(key=lambda item: (item["score"], item["overlapCount"]), reverse=True)
    public_candidates = [
        {key: value for key, value in item.items() if key != "skill"}
        for item in candidates[:5]
    ]
    thresholds = {
        "minimumOverlapTokens": 4,
        "minimumShortExactOverlapTokens": 3,
        "minimumPromptCoverage": 0.45,
        "minimumTaskCoverage": 0.65,
        "minimumShortExactTaskCoverage": 0.9,
        "minimumLeadOverSecondCandidate": 0.15,
        "requiresConcreteTaskRoute": True,
        "requiresApprovedExecutableTrajectory": True,
    }
    if not candidates:
        return {
            "decision": "no_safe_match",
            "reason": "No approved skills are available for this AgentConfig/company.",
            "confidence": 0.0,
            "thresholds": thresholds,
            "candidates": [],
        }

    best = candidates[0]
    second_score = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
    if not best["hasApprovedTrajectoryRef"]:
        return {
            "decision": "no_safe_match",
            "reason": "Best skill candidate does not reference an approved trajectory.",
            "confidence": best["score"],
            "thresholds": thresholds,
            "candidates": public_candidates,
        }
    if not best.get("hasTaskRoute") or best.get("matchedRouteSource") != "task":
        return {
            "decision": "no_safe_match",
            "reason": "Best skill candidate did not match a concrete source task, so trajectory replay is not safe.",
            "confidence": best["score"],
            "thresholds": thresholds,
            "candidates": public_candidates,
        }

    lead_is_clear = float(best["score"]) - second_score >= 0.15 or second_score == 0.0
    standard_safe = (
        best["overlapCount"] >= 4
        and float(best["promptCoverage"]) >= 0.45
        and float(best["skillCoverage"]) >= 0.65
        and lead_is_clear
    )
    short_exact_task_safe = (
        best["overlapCount"] >= 3
        and float(best["promptCoverage"]) >= 0.999
        and float(best["skillCoverage"]) >= 0.9
        and float(best["score"]) >= 0.9
        and lead_is_clear
    )
    safe = standard_safe or short_exact_task_safe
    if not safe:
        return {
            "decision": "no_safe_match",
            "reason": "No skill matched strongly enough for autonomous trajectory replay.",
            "confidence": best["score"],
            "thresholds": thresholds,
            "candidates": public_candidates,
        }
    executable, executable_reason = await _skill_has_executable_trajectory(best["skill"])
    if not executable:
        return {
            "decision": "no_safe_match",
            "reason": executable_reason,
            "confidence": best["score"],
            "thresholds": thresholds,
            "candidates": public_candidates,
        }
    return {
        "decision": "matched_skill",
        "reason": executable_reason,
        "confidence": best["score"],
        "thresholds": thresholds,
        "matchedSkillId": best["skillId"],
        "matchedSkillName": best["name"],
        "matchedTaskName": best.get("matchedRouteName") or "",
        "candidates": public_candidates,
        "skill": best["skill"],
    }


def _match_skill(prompt: str, skills: list[dict[str, Any]]) -> dict[str, Any] | None:
    prompt_tokens = _router_tokens(prompt)
    if not prompt_tokens:
        return None
    best: tuple[float, int, dict[str, Any] | None] = (0.0, 0, None)
    for skill in skills:
        candidate = _skill_route_candidate(prompt, skill)
        if (float(candidate["score"]), int(candidate["overlapCount"])) > (best[0], best[1]):
            best = (float(candidate["score"]), int(candidate["overlapCount"]), skill)
    return best[2] if best[0] >= 0.65 and best[1] >= 4 else None


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    name = str(action.get("action") or action.get("name") or "")
    args = action.get("args") if isinstance(action.get("args"), dict) else action.get("arguments")
    if not isinstance(args, dict):
        args = {}
    if name in {"navigate", "click", "input", "type", "select_dropdown", "send_keys", "wait", "done", "extract"}:
        name = f"browser.{name}"
    return {"name": name, "arguments": args, "reasoning": str(action.get("reasoning") or "")}


def _last_failed_tool_result(state: dict[str, Any], expected_name: str = "") -> dict[str, Any] | None:
    results = state.get("automata_last_tool_results")
    if not isinstance(results, list):
        return None
    for result in reversed(results):
        if not isinstance(result, dict) or result.get("success") is not False:
            continue
        name = str(result.get("tool") or result.get("name") or "")
        if expected_name and name and name != expected_name:
            continue
        return result
    return None


def _requires_human_approval(action_name: str) -> bool:
    lowered = action_name.lower()
    return any(token in lowered for token in ("send_email", "send_message", "smtp_send", "delete", "create_invoice", "payment", "transfer", ".create", ".update"))


def _approval_mode(callable_meta: dict[str, Any] | None) -> str:
    permissions = callable_meta.get("permissions") if isinstance(callable_meta, dict) and isinstance(callable_meta.get("permissions"), dict) else {}
    explicit = str(permissions.get("approval") or permissions.get("requiresHumanApproval") or "").strip().lower()
    if explicit in {"always", "auto", "never"}:
        return explicit
    if permissions.get("requiresApproval") is True:
        return "always"
    if permissions.get("requiresApproval") is False:
        return "never"
    return "auto"


def _callable_requires_approval(callable_meta: dict[str, Any] | None, agent_config: dict[str, Any], action_name: str) -> bool:
    meta = callable_meta if isinstance(callable_meta, dict) else {}
    if str(meta.get("riskLevel") or "").lower() == "high":
        return True
    mode = _approval_mode(meta)
    if mode == "always":
        return True
    if mode == "never":
        return False

    risk_policy = agent_config.get("riskPolicy") if isinstance(agent_config.get("riskPolicy"), dict) else {}
    runtime_capabilities = agent_config.get("runtimeCapabilities") if isinstance(agent_config.get("runtimeCapabilities"), dict) else {}
    writes_require_approval = bool(
        risk_policy.get("writesRequireApproval", runtime_capabilities.get("humanApprovalForWrites", True))
    )
    side_effects = str(meta.get("sideEffects") or "").lower()
    writes = any(token in side_effects for token in ("write", "send", "delete", "payment", "transfer"))
    return writes_require_approval and (writes or _requires_human_approval(action_name))


def _content_from_tool_results(tool_results: list[dict[str, Any]]) -> str:
    if not tool_results:
        return ""
    latest = tool_results[-1]
    if not latest.get("success"):
        return str(latest.get("error") or "")
    output = latest.get("output") if isinstance(latest.get("output"), dict) else {}
    tool_name = str(latest.get("tool") or "")
    if tool_name == "imap.search_emails":
        messages = output.get("messages") if isinstance(output.get("messages"), list) else []
        if not messages:
            query = output.get("query") or output.get("searchQuery") or "the requested query"
            return f"No emails found for {query!r} in {output.get('folder') or 'INBOX'}."
        lines = [f"Found {len(messages)} email(s):"]
        for message in messages[:5]:
            lines.append(
                f"- {message.get('subject') or '(no subject)'} from {message.get('from') or 'unknown'} "
                f"on {message.get('date') or 'unknown date'} [messageId: {message.get('messageId')}]"
            )
        return "\n".join(lines)
    if tool_name == "imap.read_email":
        return (
            f"Email from {output.get('from') or 'unknown'} about {output.get('subject') or '(no subject)'}:\n\n"
            f"{output.get('body') or 'No body content found.'}"
        )
    if tool_name == "smtp.draft_email":
        return (
            f"Draft ready.\n\nTo: {output.get('to') or ''}\n"
            f"Subject: {output.get('subject') or ''}\n\n{output.get('body') or ''}"
        )
    if tool_name in {"smtp.send_email", "gmail.send_email"}:
        return f"Email sent to {output.get('to') or 'recipient'} with subject {output.get('subject') or '(no subject)'}."
    if tool_name in {"web.fetch", "web.fetch_text"} and output.get("text"):
        url = f"Source: {output.get('url')}\n\n" if output.get("url") else ""
        return f"{url}{str(output.get('text') or '').strip()[:2000]}"
    if tool_name == "web.extract_links":
        links = output.get("links") if isinstance(output.get("links"), list) else []
        if not links:
            return f"No links found at {output.get('url') or 'the requested URL'}."
        lines = [f"Found {len(links)} link(s) at {output.get('url') or 'the requested URL'}:"]
        for link in links[:10]:
            lines.append(f"- {link.get('text') or '(no label)'}: {link.get('url')}")
        return "\n".join(lines)
    if output.get("pdfUrl"):
        label = str(output.get("numBOPA") or output.get("title") or latest.get("tool") or "result")
        published = f" published at {output.get('publishedAt')}" if output.get("publishedAt") else ""
        return f"{label}{published}: {output['pdfUrl']}"
    if output.get("url"):
        return str(output["url"])
    if output:
        compact = {key: value for key, value in output.items() if key not in {"text", "html"}}
        return str(compact)
    return "Connector tools executed."


def _email_agent_response(prompt: str, state: dict[str, Any]) -> dict[str, Any]:
    lowered = prompt.lower()
    email_match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", prompt)
    recipient = email_match.group(0) if email_match else ""
    subject_match = re.search(r"(?:asunto|subject)\s*[:：]?\s*(.+?)(?:\s+y\s+cuerpo\b|\s+con\s+cuerpo\b|\s+body\b|[.\n]|$)", prompt, flags=re.IGNORECASE)
    subject = subject_match.group(1).strip() if subject_match else "Seguimiento"
    if subject.lower() in {"y cuerpo", "con cuerpo", "cuerpo", "body"}:
        subject = "Seguimiento"

    if any(token in lowered for token in ("buscar", "busca", "search", "encuentra", "último", "ultimo", "reciente")):
        query = _email_search_query(prompt)
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": "imap.search_emails", "arguments": {"query": query, "folder": "INBOX", "limit": 5}}],
            "content": None,
            "reasoning": "Email-specialized runtime: search mailbox first so the response can be grounded in actual email context.",
            "done": False,
            "state_out": state,
        }

    read_match = re.search(r"(?:messageId|uid|mensaje)\s*[:#]?\s*([A-Za-z0-9_.:-]+)", prompt, flags=re.IGNORECASE)
    if any(token in lowered for token in ("lee", "leer", "léelo", "leelo", "read")) and read_match:
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": "imap.read_email", "arguments": {"messageId": read_match.group(1), "folder": "INBOX"}}],
            "content": None,
            "reasoning": "Email-specialized runtime: read the requested message before summarizing or replying.",
            "done": False,
            "state_out": state,
        }

    body = _email_body(prompt)
    draft_arguments = {"to": recipient or "pending-recipient@example.com", "subject": subject, "body": body}
    wants_send = any(token in lowered for token in ("envía", "envia", "send", "enviar")) and not any(token in lowered for token in ("no lo env", "no enviar", "no send", "sin enviar"))
    if wants_send and recipient:
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": "smtp.send_email", "arguments": draft_arguments}],
            "content": None,
            "reasoning": "Email-specialized runtime: the user requested sending, so use smtp.send_email and let the approval gate stop execution until confirmed.",
            "done": False,
            "state_out": state,
        }

    return {
        "protocol_version": "1.0",
        "tool_calls": [{"name": "smtp.draft_email", "arguments": draft_arguments}],
        "content": None,
        "reasoning": "Email-specialized runtime: prepare a draft rather than sending.",
        "done": False,
        "state_out": state,
    }


def _email_search_query(prompt: str) -> str:
    topic_match = re.search(
        r"(?:sobre|de|about|for)\s+(.+?)(?:,|\.|\s+y\s+|\s+and\s+|\s+resume\b|\s+summari[sz]e\b|$)",
        prompt,
        flags=re.IGNORECASE,
    )
    candidate = topic_match.group(1) if topic_match else prompt
    candidate = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", candidate)
    words = [
        re.sub(r"^[^\wáéíóúüñÁÉÍÓÚÜÑ]+|[^\wáéíóúüñÁÉÍÓÚÜÑ]+$", "", token)
        for token in re.split(r"\s+", candidate)
    ]
    stopwords = {
        "busca", "buscar", "email", "mail", "correo", "correos", "mensaje", "mensajes",
        "mas", "más", "reciente", "ultimo", "último", "the", "latest", "recent",
        "search", "find", "sobre", "about", "de", "del", "la", "el", "los", "las",
    }
    keywords = [word for word in words if word and word.lower() not in stopwords]
    return " ".join(keywords[:6])[:80]


def _email_body(prompt: str) -> str:
    body_match = re.search(r"(?:cuerpo|body)\s*[:：]?\s*(.+)$", prompt, flags=re.IGNORECASE | re.DOTALL)
    if body_match:
        body = body_match.group(1).strip()
        if body and body.lower() not in {"cuerpo", "body"} and re.search(r"[\wáéíóúüñÁÉÍÓÚÜÑ]", body):
            return body
    lowered = prompt.lower()
    if "agradec" in lowered and ("revisaremos" in lowered or "revisar" in lowered):
        return "Gracias por su consulta. Revisaremos el caso hoy y le responderemos con una actualizacion en cuanto tengamos mas informacion."
    if "agradec" in lowered:
        return "Gracias por su consulta. Hemos recibido su mensaje y lo revisaremos lo antes posible."
    return prompt.strip()


def _expected_tool_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if expected.startswith("knowledge."):
        suffix = expected.removeprefix("knowledge")
        return actual.startswith("knowledge.") and actual.endswith(suffix)
    return False


async def _resolve_company_tool_name(company_id: str, expected_tool: str) -> str:
    if not expected_tool:
        return ""
    tools = await tools_collection.find({"companyId": company_id}, {"_id": 0, "name": 1}).to_list(length=500)
    names = [str(tool.get("name") or "") for tool in tools]
    for name in names:
        if _expected_tool_matches(name, expected_tool):
            return name
    return expected_tool


def _configured_url(connector: dict[str, Any], payload: dict[str, Any]) -> str:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    for key in ("startUrl", "baseUrl", "url", "websiteUrl", "loginUrl"):
        value = str(config.get(key) or connector.get(key) or "").strip()
        if value:
            return value
    return str(payload.get("url") or "").strip()


def _query_after(prompt: str, markers: tuple[str, ...]) -> str:
    lowered = prompt.lower()
    for marker in markers:
        index = lowered.find(marker)
        if index >= 0:
            return prompt[index + len(marker):].strip(" :,.")[:120]
    return prompt[:120]


def _connector_tool_arguments(tool_name: str, prompt: str, connector: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name in {"bopa.latest_bulletin", "bopa.latest_bulletin_pdf", "bopa.list_bulletins"}:
        return {}
    if tool_name.endswith(".search") and tool_name.startswith("knowledge."):
        return {"query": prompt, "topK": 5}
    if tool_name == "erp.search_claims":
        return {"query": _query_after(prompt, ("siniestro", "claim", "cliente", "customer")) or prompt, "limit": 5}
    if tool_name.endswith(".list_documents") and tool_name.startswith("knowledge."):
        return {"limit": 20}
    if tool_name == "holded.list_invoices":
        return {"limit": 10}
    if tool_name in {"holded.search_invoices", "holded.search_clients"}:
        query = _query_after(prompt, ("cliente", "client", "facturas de", "facturas para", "buscar", "busca"))
        return {"query": query or prompt, "limit": 10}
    if tool_name == "holded.list_clients":
        return {"limit": 25}
    if tool_name == "holded.get_invoice":
        match = re.search(r"(?:invoiceId|factura)\s*[:#]?\s*([A-Za-z0-9_.:-]+)", prompt, flags=re.IGNORECASE)
        return {"invoiceId": match.group(1) if match else ""}
    if tool_name == "telegram.get_chat":
        return {}
    if tool_name == "telegram.send_message":
        message = prompt.split(":", 1)[1].strip() if ":" in prompt else prompt
        return {"message": message}
    if tool_name == "imap.search_emails":
        return {"query": _email_search_query(prompt), "folder": "INBOX", "limit": 5}
    if tool_name == "imap.read_email":
        read_match = re.search(r"(?:messageId|uid|mensaje)\s*[:#]?\s*([A-Za-z0-9_.:-]+)", prompt, flags=re.IGNORECASE)
        message_id = read_match.group(1) if read_match else ""
        return {"messageId": message_id, "folder": "INBOX"}
    if tool_name in {"smtp.draft_email", "smtp.send_email", "gmail.send_email"}:
        email_match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", prompt)
        subject_match = re.search(r"(?:asunto|subject)\s*[:：]?\s*(.+?)(?:\s+y\s+cuerpo\b|\s+con\s+cuerpo\b|\s+body\b|[.\n]|$)", prompt, flags=re.IGNORECASE)
        subject = subject_match.group(1).strip() if subject_match else "Seguimiento"
        if subject.lower() in {"y cuerpo", "con cuerpo", "cuerpo", "body"}:
            subject = "Seguimiento"
        return {
            "to": email_match.group(0) if email_match else "",
            "subject": subject,
            "body": _email_body(prompt),
        }
    if tool_name in {"web.fetch", "web.fetch_text", "web.extract_links", "browser.navigate"}:
        args: dict[str, Any] = {"url": _configured_url(connector, payload)}
        if tool_name == "web.fetch_text":
            args["maxChars"] = 6000
        if tool_name == "web.extract_links":
            args["limit"] = 20
        return args
    if tool_name.endswith(".search"):
        return {"query": prompt, "limit": 10}
    if tool_name.endswith(".get"):
        return {}
    if tool_name.endswith(".send_message"):
        return {"message": prompt}
    return {}


def _custom_connector_needs_implementation(tool_doc: dict[str, Any] | None) -> bool:
    if not isinstance(tool_doc, dict) or not tool_doc:
        return False
    metadata = tool_doc.get("metadata") if isinstance(tool_doc.get("metadata"), dict) else {}
    connector_type = str(tool_doc.get("connectorType") or metadata.get("connectorType") or "").lower()
    implementation_status = str(tool_doc.get("implementationStatus") or metadata.get("implementationStatus") or "").lower()
    has_executor = bool(tool_doc.get("executor") or tool_doc.get("runtimeExecutor") or metadata.get("executor"))
    is_custom = connector_type == "custom" or bool(metadata.get("customConnector"))
    if has_custom_connector_executor(tool_doc):
        return False
    if is_custom and has_executor:
        return True
    if implementation_status in {"ready", "implemented", "active"} or has_executor:
        return False
    return is_custom


def _custom_connector_implementation_result(name: str, arguments: dict[str, Any], tool_doc: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    task_id = str(payload_context.get("taskId") or "")
    connector_id = str(tool_doc.get("connectorId") or "")
    executor_name = custom_connector_executor_name(tool_doc)
    return {
        "tool": name,
        "success": False,
        "status": "implementation_required",
        "error": "Custom connector tool is specified but no runtime executor is implemented yet.",
        "output": {
            "implementationRequired": True,
            "toolName": name,
            "toolId": str(tool_doc.get("toolId") or ""),
            "connectorId": connector_id,
            "runtimeExecutor": executor_name,
            "arguments": arguments,
            "nextAction": "Implement or attach a connector executor, then rerun the benchmark task.",
        },
        "artifacts": [
            {
                "artifactId": f"{task_id or connector_id or name}:connector_gap_report",
                "name": "connector_gap_report",
                "title": "Connector Gap Report",
                "artifactType": "connector_gap_report",
                "kind": "connector_gap_report",
                "content": f"Tool {name} is modeled for connector {connector_id or 'unknown'}, but no runtime executor is attached.",
                "sourceTool": name,
                "metadata": {
                    "toolId": str(tool_doc.get("toolId") or ""),
                    "connectorId": connector_id,
                    "taskId": task_id,
                    "implementationRequired": True,
                    "runtimeExecutor": executor_name,
                },
            }
        ],
    }


def _fallback_expected_tool_from_prompt(prompt: str, tools: list[str]) -> str:
    lowered = prompt.lower()
    def available(name: str) -> bool:
        return any(_expected_tool_matches(actual, name) for actual in tools)

    if "bopa" in lowered:
        if "pdf" in lowered and available("bopa.latest_bulletin_pdf"):
            return "bopa.latest_bulletin_pdf"
        if available("bopa.latest_bulletin"):
            return "bopa.latest_bulletin"
    if "telegram" in lowered:
        if any(token in lowered for token in ("envia", "envía", "send")) and available("telegram.send_message"):
            return "telegram.send_message"
        if available("telegram.get_chat"):
            return "telegram.get_chat"
    if "holded" in lowered or "factura" in lowered or "cliente" in lowered:
        if "factura" in lowered and any(token in lowered for token in ("lista", "ultimas", "últimas")) and available("holded.list_invoices"):
            return "holded.list_invoices"
        if "factura" in lowered and available("holded.search_invoices"):
            return "holded.search_invoices"
        if "cliente" in lowered and available("holded.search_clients"):
            return "holded.search_clients"
    if any(token in lowered for token in ("document", "documento", "knowledge", "intern")):
        if any(token in lowered for token in ("lista", "listar", "disponibles")) and available("knowledge.list_documents"):
            return "knowledge.list_documents"
        if available("knowledge.search"):
            return "knowledge.search"
    if any(token in lowered for token in ("web", "pagina", "página", "links", "link", "abre", "abrir")):
        if any(token in lowered for token in ("abre", "abrir", "browser")) and available("browser.navigate"):
            return "browser.navigate"
        if "link" in lowered and available("web.extract_links"):
            return "web.extract_links"
        if available("web.fetch_text"):
            return "web.fetch_text"
    return tools[0] if tools else ""


async def _local_connector_agent_response(agent_config: dict[str, Any], prompt: str, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    company_id = str(agent_config.get("companyId") or "")
    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    task_id = str(payload_context.get("taskId") or "")
    task = await benchmark_tasks_collection.find_one({"taskId": task_id}, {"_id": 0}) if task_id else None
    metadata = task.get("metadata") if isinstance(task, dict) and isinstance(task.get("metadata"), dict) else {}
    expected_tools = [str(item) for item in metadata.get("expectedTools") or [] if item]
    connector_id = str(metadata.get("connectorId") or "")

    tool_docs = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    tool_names = [str(tool.get("name") or "") for tool in tool_docs if tool.get("name")]
    selected_expected_tools = expected_tools or [_fallback_expected_tool_from_prompt(prompt, tool_names)]
    selected_expected_tools = [tool for tool in selected_expected_tools if tool]
    resolved_tool_names = [await _resolve_company_tool_name(company_id, expected_tool) for expected_tool in selected_expected_tools]
    resolved_tool_names = [tool for tool in resolved_tool_names if tool]
    tool_name = resolved_tool_names[0] if resolved_tool_names else ""

    connector = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0}) if connector_id else None
    if not connector and tool_name:
        tool_doc = next((tool for tool in tool_docs if str(tool.get("name") or "") == tool_name), {})
        connector_ref = str(tool_doc.get("connectorId") or "")
        connector = await connectors_collection.find_one({"connectorId": connector_ref}, {"_id": 0}) if connector_ref else None
    connector = connector or {}

    if not tool_name:
        return {
            "protocol_version": "1.0",
            "tool_calls": [],
            "tool_results": [{"tool": "local_connector_agent", "success": False, "error": "No connector tool matched this task."}],
            "content": "No connector tool matched this task.",
            "reasoning": "Local connector runtime could not find a safe tool for the request.",
            "done": True,
            "state_out": state,
        }

    tool_calls = [
        {"name": name, "arguments": _connector_tool_arguments(name, prompt, connector, payload)}
        for name in resolved_tool_names
    ]
    expected_artifacts = [str(item) for item in metadata.get("expectedArtifacts") or [] if item]
    artifacts = [
        {
            "artifactId": f"{task_id or 'connector-task'}:{artifact}",
            "name": artifact,
            "title": artifact.replace("_", " ").title(),
            "artifactType": artifact,
            "kind": artifact,
            "content": f"Generated {artifact} for benchmark task {task_id or 'ad-hoc connector task'}.",
            "sourceTool": "local_connector_agent",
            "metadata": {"benchmarkId": metadata.get("benchmarkId", ""), "taskId": task_id},
        }
        for artifact in expected_artifacts
        if artifact not in {"approval_request"}
    ]
    state_out = dict(state or {})
    if bool(metadata.get("requiresApproval")) or "api.human_approval" in resolved_tool_names:
        state_out["pendingConnectorApproval"] = state_out.get("pendingConnectorApproval") or f"{task_id or 'connector-task'}:approval"
    return {
        "protocol_version": "1.0",
        "tool_calls": tool_calls,
        "artifacts": artifacts,
        "content": None,
        "reasoning": f"Local connector runtime selected {', '.join(resolved_tool_names)} for this connector task.",
        "done": False,
        "state_out": state_out,
    }


def _is_browser_tool(tool_name: str) -> bool:
    return tool_name.startswith("browser.") or tool_name in {"navigate", "click", "input", "type", "select_dropdown", "send_keys", "wait", "done", "extract"} or tool_name == "api.human_approval"


def _has_browser_tool_calls(data: dict[str, Any]) -> bool:
    calls = data.get("tool_calls")
    if not isinstance(calls, list):
        return False
    return any(
        isinstance(call, dict) and _is_browser_tool(_normalize_tool_call(call)["name"])
        for call in calls
    )


def _browser_enabled(agent_config: dict[str, Any]) -> bool:
    return _runtime_policy_browser_enabled(agent_config)


def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    fn = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else None
    if fn:
        return {"name": str(fn.get("name") or ""), "arguments": fn.get("arguments") if isinstance(fn.get("arguments"), dict) else {}}
    return {
        "name": str(tool_call.get("name") or ""),
        "arguments": tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {},
    }


def _search_query_from_prompt(prompt: str) -> str:
    quoted = re.search(r"['\"]([^'\"]{2,120})['\"]", prompt)
    if quoted:
        return quoted.group(1).strip()

    lowered = prompt.strip()
    match = re.search(r"\b(?:busca|buscar|search|find)\b(?:\s+(?:amazon|for|un|una|el|la|los|las|a|the))*\s+(.+)", lowered, flags=re.IGNORECASE)
    if match:
        lowered = match.group(1)

    lowered = re.split(r"[.;\n]", lowered, maxsplit=1)[0]
    stop_words = {
        "amazon",
        "busca",
        "buscar",
        "search",
        "find",
        "for",
        "the",
        "a",
        "an",
        "un",
        "una",
        "el",
        "la",
        "los",
        "las",
        "producto",
        "product",
        "detail",
        "page",
        "open",
        "abre",
    }
    terms = [token for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]+", lowered) if token.lower() not in stop_words]
    return " ".join(terms).strip()


def _site_search_url(agent_config: dict[str, Any], prompt: str) -> str:
    website_url = str(agent_config.get("websiteUrl") or "").strip()
    query = _search_query_from_prompt(prompt)
    if query and "amazon." in website_url.lower():
        return f"https://www.amazon.com/s?k={quote_plus(query)}"
    if query:
        return f"https://duckduckgo.com/?q={quote_plus(query)}"
    return website_url or "about:blank"


def _site_fallback_response(agent_config: dict[str, Any], prompt: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "tool_calls": [{"name": "browser.navigate", "arguments": {"url": _site_search_url(agent_config, prompt)}}],
        "content": None,
        "reasoning": "Detected mismatched external runtime instructions; using the configured agent site instead.",
        "done": False,
        "state_out": state,
    }


def _normalize_runtime_tool_calls(agent_config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    raw_calls = data.get("tool_calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        return data

    normalized_calls: list[Any] = []
    changed = False
    website_url = str(agent_config.get("websiteUrl") or "").lower()
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            normalized_calls.append(raw_call)
            continue
        call = _normalize_tool_call(raw_call)
        if call["name"] != "browser.search":
            normalized_calls.append(raw_call)
            continue

        query = str(call["arguments"].get("query") or "").strip()
        if not query:
            normalized_calls.append(raw_call)
            continue

        if "amazon." in website_url:
            url = f"https://www.amazon.com/s?k={quote_plus(query)}"
        else:
            url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        normalized_calls.append({"name": "browser.navigate", "arguments": {"url": url}})
        changed = True

    return {**data, "tool_calls": normalized_calls} if changed else data


def _enforce_runtime_surface_permissions(agent_config: dict[str, Any], data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if _browser_enabled(agent_config):
        return data
    raw_calls = data.get("tool_calls")
    browser_call_names = {"navigate", "click", "input", "type", "select_dropdown", "send_keys", "wait", "done", "extract"}
    has_browser_call = False
    if isinstance(raw_calls, list):
        for call in raw_calls:
            if not isinstance(call, dict):
                continue
            name = _normalize_tool_call(call)["name"]
            if name.startswith("browser.") or name in browser_call_names:
                has_browser_call = True
                break
    if not has_browser_call:
        return data
    return {
        **data,
        "tool_calls": [],
        "content": "Browser access is disabled for this agent runtime.",
        "reasoning": "The runtime requested a browser action, but this AgentConfig does not expose the browser toolkit.",
        "done": True,
        "state_out": state,
    }


def _step_index(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("step_index") or 0)
    except (TypeError, ValueError):
        return 0


def _external_runtime_looks_mismatched(agent_config: dict[str, Any], data: dict[str, Any]) -> bool:
    text = " ".join(
        str(data.get(key) or "")
        for key in ("reasoning", "content", "message")
    ).lower()
    default_instruction_markers = (
        "custom operator instructions",
        "you are operating the autocinema website",
    )
    return any(marker in text for marker in default_instruction_markers)


async def _execute_connector_tool_calls(agent_config: dict[str, Any], data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    company_id = str(agent_config.get("companyId") or "")
    if not company_id:
        return data
    raw_calls = data.get("tool_calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        return data

    state = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    approved = set(state.get("approvedConnectorToolCalls") or [])
    passthrough_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = list(data.get("tool_results") or [])
    executed_tool_calls: list[dict[str, Any]] = list(data.get("executed_tool_calls") or [])
    executed_any = False
    tool_docs = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    tools_by_name = {str(tool.get("name") or ""): tool for tool in tool_docs}

    for idx, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            passthrough_calls.append(raw_call)
            continue
        call = _normalize_tool_call(raw_call)
        name = call["name"]
        arguments = call["arguments"]
        if not name or _is_browser_tool(name):
            passthrough_calls.append(raw_call)
            continue

        if name.startswith("skill."):
            skills = await capabilities_collection.find(
                {"agentId": agent_config.get("agentId", ""), "capabilityKind": "skill"},
                {"_id": 0},
            ).to_list(length=200)
            skill = next((item for item in skills if _skill_callable(item).get("name") == name), None)
            if not skill:
                tool_results.append({"tool": name, "success": False, "error": "Skill not found"})
                executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": "Skill not found"})
                executed_any = True
                continue
            unavailable = _require_runtime_available(agent_config, name, skill.get("runtimeRequirements") or [])
            if unavailable:
                tool_results.append(unavailable)
                executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": unavailable.get("error")})
                executed_any = True
                continue
            skill_response = await _web_skill_response(
                agent_config,
                skill,
                str(arguments.get("instruction") or payload.get("prompt") or ""),
                payload,
            )
            passthrough_calls.extend(skill_response.get("tool_calls") or [])
            tool_results.append({"tool": name, "success": True, "output": {"content": skill_response.get("content"), "capabilityMatch": skill_response.get("capability_match")}})
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": True, "output": {"capabilityMatch": skill_response.get("capability_match")}})
            executed_any = True
            continue

        tool_doc = tools_by_name.get(name)
        unavailable = _require_runtime_available(agent_config, name, (tool_doc or {}).get("runtimeRequirements") or [])
        if unavailable:
            tool_results.append(unavailable)
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": unavailable.get("error")})
            executed_any = True
            continue

        approval_key = stable_approval_key(name, idx, arguments)
        if _callable_requires_approval(tool_doc, agent_config, name) and approval_key not in approved:
            payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            run_id = str(payload.get("run_id") or payload.get("runId") or payload_context.get("runId") or "")
            work_item_id = str(payload_context.get("workItemId") or "")
            session_id = str(payload.get("sessionId") or payload.get("session_id") or payload_context.get("sessionId") or "")
            approval = await create_pending_approval(
                email=str(agent_config.get("email") or ""),
                company_id=company_id,
                agent_id=str(agent_config.get("agentId") or ""),
                run_id=run_id,
                approval_key=approval_key,
                title=f"Approve {name}",
                message="This connector tool can write or send data. Confirm before Automata executes it.",
                proposed_action={"name": name, "arguments": arguments},
                entity_ref={"entity": str((tool_doc or {}).get("outputEntity") or "")},
                metadata={
                    "toolId": str((tool_doc or {}).get("toolId") or ""),
                    "connectorId": str((tool_doc or {}).get("connectorId") or ""),
                    "workItemId": work_item_id,
                    "sessionId": session_id,
                    "runId": run_id,
                    "sourceKind": "work" if work_item_id else "session" if session_id else "runtime",
                },
            )
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="approval_required",
                payload={"arguments": arguments},
                result={
                    "tool": name,
                    "success": False,
                    "status": "approval_required",
                    "approvalId": approval.get("approvalId", ""),
                    "approvalKey": approval_key,
                },
            )
            return {
                **data,
                "tool_calls": [
                    {
                        "name": "api.human_approval",
                        "arguments": {
                            "title": f"Approve {name}",
                            "message": "This connector tool can write or send data. Confirm before Automata executes it.",
                            "proposedAction": {"name": name, "arguments": arguments},
                            "approvalKey": approval_key,
                            "approvalId": approval.get("approvalId", ""),
                        },
                    }
                ],
                "tool_results": tool_results,
                "executed_tool_calls": [
                    *executed_tool_calls,
                    {
                        "name": name,
                        "arguments": arguments,
                        "success": False,
                        "status": "approval_required",
                        "approvalId": approval.get("approvalId", ""),
                        "approvalKey": approval_key,
                    },
                ],
                "done": False,
                "state_out": {
                    **(data.get("state_out") if isinstance(data.get("state_out"), dict) else {}),
                    "pendingConnectorApproval": approval_key,
                    "pendingConnectorToolCall": {"name": name, "arguments": arguments},
                    "approvedConnectorToolCalls": list(approved),
                },
            }

        if _custom_connector_needs_implementation(tool_doc):
            result = _custom_connector_implementation_result(name, arguments, tool_doc or {}, payload)
            tool_results.append(result)
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": result.get("error"), "status": result.get("status")})
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="blocked",
                payload={"arguments": arguments},
                result=result,
            )
            executed_any = True
            continue

        try:
            custom_result = await execute_custom_connector_tool(
                company_id=company_id,
                tool_name=name,
                arguments=arguments,
                tool_doc=tool_doc or {},
                agent_config=agent_config,
                payload=payload,
            )
            result = custom_result or await execute_connector_tool(company_id=company_id, tool_name=name, arguments=arguments)
            if tool_doc and (tool_doc.get("outputEntity") or tool_doc.get("outputCard")):
                result = {
                    **result,
                    "entity": {
                        "outputEntity": tool_doc.get("outputEntity", ""),
                        "inputEntities": tool_doc.get("inputEntities", []),
                        "outputCard": tool_doc.get("outputCard", {}),
                    },
                }
            tool_results.append(result)
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": result.get("success") is not False, "output": result.get("output"), "error": result.get("error")})
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="ok" if result.get("success") else "failed",
                payload={"arguments": arguments},
                result=result,
            )
            payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            await _record_usage_event(
                email=str(agent_config.get("email") or ""),
                company_id=company_id,
                agent_id=str(agent_config.get("agentId") or ""),
                run_id=str(payload.get("run_id") or payload.get("runId") or payload_context.get("runId") or ""),
                kind="tool_call",
                source=name,
                metadata={"toolName": name, "success": bool(result.get("success"))},
            )
            executed_any = True
        except ConnectorExecutionError as exc:
            tool_results.append({"tool": name, "success": False, "error": str(exc)})
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": str(exc)})
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="failed",
                payload={"arguments": arguments},
                error=str(exc),
            )
            executed_any = True
        except Exception as exc:
            logger.exception("Unexpected connector tool failure for %s", name)
            tool_results.append({"tool": name, "success": False, "error": str(exc)})
            executed_tool_calls.append({"name": name, "arguments": arguments, "success": False, "error": str(exc)})
            await record_runtime_event(
                agent_id=str(agent_config.get("agentId") or ""),
                company_id=company_id,
                event_type="tool.call",
                tool_name=name,
                status="failed",
                payload={"arguments": arguments},
                error=str(exc),
            )
            executed_any = True

    if not executed_any:
        return data

    return {
        **data,
        "tool_calls": passthrough_calls,
        "tool_results": tool_results,
        "executed_tool_calls": executed_tool_calls,
        "content": data.get("content") or _content_from_tool_results(tool_results) or "Connector tools executed.",
        "done": bool(data.get("done")) and not passthrough_calls,
    }


async def _load_skill_trajectory(skill: dict[str, Any]) -> dict[str, Any] | None:
    trajectory_ids = [str(item) for item in skill.get("trajectoryIds") or [] if item]
    if not trajectory_ids:
        return None
    query = {"trajectoryId": {"$in": trajectory_ids}}
    preferred = await trajectories_collection.find_one({**query, "status": "approved"}, {"_id": 0})
    if preferred:
        return preferred
    return await trajectories_collection.find_one(query, {"_id": 0})


async def _web_skill_response(agent_config: dict[str, Any], skill: dict[str, Any], prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    skill_id = str(skill.get("capabilityId") or skill.get("skillId") or skill.get("name") or "")

    trajectory = await _load_skill_trajectory(skill)
    raw_actions = []
    if trajectory:
        raw_actions = trajectory.get("trajectory") or trajectory.get("actions") or trajectory.get("steps") or []
    actions = [_normalize_action(action) for action in raw_actions if isinstance(action, dict)]
    actions = [action for action in actions if action["name"]]
    recovery_steps = [
        action
        for action in (_normalize_action(item) for item in (trajectory or {}).get("recoverySteps", []) if isinstance(item, dict))
        if action["name"]
    ]

    if actions and str(trajectory.get("status") if trajectory else "") in {"approved", "harvested"}:
        progress = state.get("automata_trajectory_progress") if isinstance(state.get("automata_trajectory_progress"), dict) else {}
        trajectory_id = str(trajectory.get("trajectoryId") or "")
        current = progress.get(trajectory_id) if isinstance(progress.get(trajectory_id), dict) else {}
        index = int(current.get("index") or 0)
        approval_pending = bool(current.get("approvalPending"))
        approved_actions = set(current.get("approvedActions") or [])
        recovered_failures = set(current.get("recoveredFailures") or [])

        recovery_index = current.get("recoveryIndex")
        if recovery_steps and isinstance(recovery_index, int) and 0 <= recovery_index < len(recovery_steps):
            recovery_action = recovery_steps[recovery_index]
            next_recovery_index = recovery_index + 1
            next_current = {
                **current,
                "index": index,
                "approvalPending": False,
                "approvedActions": list(approved_actions),
            }
            if next_recovery_index < len(recovery_steps):
                next_current["recoveryIndex"] = next_recovery_index
            else:
                next_current.pop("recoveryIndex", None)
                failed_key = str(current.get("recoveringFailure") or "")
                if failed_key:
                    next_current["recoveredFailures"] = sorted(recovered_failures | {failed_key})
                    next_current.pop("recoveringFailure", None)
            next_progress = {**progress, trajectory_id: next_current}
            return {
                "protocol_version": "1.0",
                "tool_calls": [{"name": recovery_action["name"], "arguments": recovery_action["arguments"]}],
                "content": None,
                "reasoning": recovery_action["reasoning"] or f"Repairing harvested skill '{skill.get('name', 'skill')}' after a failed trajectory action.",
                "done": False,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        failed_action_index = max(index - 1, 0)
        failed_action_name = actions[failed_action_index]["name"] if index > 0 and failed_action_index < len(actions) else ""
        failed_result = _last_failed_tool_result(state, failed_action_name)
        if recovery_steps and failed_result and failed_action_name:
            failure_key = f"{failed_action_index}:{failed_action_name}"
            if failure_key not in recovered_failures:
                recovery_action = recovery_steps[0]
                next_current = {
                    **current,
                    "index": index,
                    "approvalPending": False,
                    "approvedActions": list(approved_actions),
                    "recoveringFailure": failure_key,
                    "recoveredFailures": list(recovered_failures),
                }
                if len(recovery_steps) > 1:
                    next_current["recoveryIndex"] = 1
                else:
                    next_current["recoveredFailures"] = sorted(recovered_failures | {failure_key})
                    next_current.pop("recoveringFailure", None)
                next_progress = {
                    **progress,
                    trajectory_id: next_current,
                }
                return {
                    "protocol_version": "1.0",
                    "tool_calls": [{"name": recovery_action["name"], "arguments": recovery_action["arguments"]}],
                    "content": None,
                    "reasoning": recovery_action["reasoning"] or str(failed_result.get("error") or "Previous trajectory action failed; running recovery."),
                    "done": False,
                    "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                    "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
                }

        if index >= len(actions):
            return {
                "protocol_version": "1.0",
                "tool_calls": [],
                "content": f"Completed harvested skill '{skill.get('name', 'skill')}'.",
                "reasoning": "All harvested trajectory tools have been replayed.",
                "done": True,
                "state_out": state,
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        action = actions[index]
        action_key = f"{trajectory_id}:{index}"
        if action["name"] == "api.human_approval":
            approval_args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            body = str(approval_args.get("body") or approval_args.get("message") or approval_args.get("summary") or "")
            next_action_key = f"{trajectory_id}:{index + 1}" if index + 1 < len(actions) else action_key
            state_patch = {
                "matchedSkillId": skill_id,
                "automata_trajectory_progress": {
                    trajectory_id: {
                        "index": index + 1,
                        "approvalPending": False,
                        "approvedActions": sorted(approved_actions | {next_action_key}),
                    }
                },
            }
            next_progress = {
                **progress,
                trajectory_id: {"index": index + 1, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            run_id = str(payload.get("run_id") or payload.get("runId") or payload_context.get("runId") or "")
            work_item_id = str(payload_context.get("workItemId") or "")
            session_id = str(payload.get("sessionId") or payload.get("session_id") or payload_context.get("sessionId") or "")
            approval = await create_pending_approval(
                email=str(agent_config.get("email") or ""),
                company_id=str(agent_config.get("companyId") or ""),
                agent_id=str(agent_config.get("agentId") or ""),
                run_id=run_id,
                approval_key=next_action_key,
                title=str(approval_args.get("title") or f"Approve {skill.get('name', 'skill')}"),
                message=body or "This harvested skill prepared an action that needs human approval.",
                proposed_action=actions[index + 1] if index + 1 < len(actions) else action,
                metadata={
                    "approvalKind": "skill_action",
                    "skillId": skill_id,
                    "trajectoryId": trajectory_id,
                    "actionIndex": index + 1,
                    "workItemId": work_item_id,
                    "sessionId": session_id,
                    "runId": run_id,
                    "sourceKind": "work" if work_item_id else "session" if session_id else "runtime",
                    "statePatch": state_patch,
                },
            )
            return {
                "protocol_version": "1.0",
                "tool_calls": [
                    {
                        "name": "api.human_approval",
                        "arguments": {
                            "title": approval.get("title") or f"Approve {skill.get('name', 'skill')}",
                            "message": approval.get("message") or body,
                            "proposedAction": approval.get("proposedAction") or {},
                            "approvalKey": approval.get("approvalKey", ""),
                            "approvalId": approval.get("approvalId", ""),
                            "statePatch": state_patch,
                        },
                    }
                ],
                "content": None,
                "reasoning": action["reasoning"] or "Human approval is required before executing the proposed write/send action.",
                "done": False,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }
        if _callable_requires_approval(skill, agent_config, action["name"]) and action_key not in approved_actions and not approval_pending:
            next_progress = {
                **progress,
                trajectory_id: {"index": index, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            state_patch = {
                "matchedSkillId": skill_id,
                "automata_trajectory_progress": {
                    trajectory_id: {
                        "index": index,
                        "approvalPending": False,
                        "approvedActions": sorted(approved_actions | {action_key}),
                    }
                },
            }
            payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            run_id = str(payload.get("run_id") or payload.get("runId") or payload_context.get("runId") or "")
            work_item_id = str(payload_context.get("workItemId") or "")
            session_id = str(payload.get("sessionId") or payload.get("session_id") or payload_context.get("sessionId") or "")
            approval = await create_pending_approval(
                email=str(agent_config.get("email") or ""),
                company_id=str(agent_config.get("companyId") or ""),
                agent_id=str(agent_config.get("agentId") or ""),
                run_id=run_id,
                approval_key=action_key,
                title=f"Approve {action['name']}",
                message="This harvested trajectory is about to perform a write/send action. Confirm before continuing.",
                proposed_action=action,
                metadata={
                    "approvalKind": "skill_action",
                    "skillId": skill_id,
                    "trajectoryId": trajectory_id,
                    "actionIndex": index,
                    "workItemId": work_item_id,
                    "sessionId": session_id,
                    "runId": run_id,
                    "sourceKind": "work" if work_item_id else "session" if session_id else "runtime",
                    "statePatch": state_patch,
                },
            )
            return {
                "protocol_version": "1.0",
                "tool_calls": [
                    {
                        "name": "api.human_approval",
                        "arguments": {
                            "title": f"Approve {action['name']}",
                            "message": "This harvested trajectory is about to perform a write/send action. Confirm before continuing.",
                            "proposedAction": action,
                            "approvalKey": action_key,
                            "approvalId": approval.get("approvalId", ""),
                            "statePatch": state_patch,
                        },
                    }
                ],
                "content": None,
                "reasoning": f"Matched harvested skill '{skill.get('name', 'skill')}'. Human approval is required before executing {action['name']}.",
                "done": False,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        if approval_pending and action_key not in approved_actions:
            next_progress = {
                **progress,
                trajectory_id: {"index": index, "approvalPending": True, "approvedActions": list(approved_actions)},
            }
            return {
                "protocol_version": "1.0",
                "tool_calls": [],
                "content": f"Matched skill '{skill.get('name', 'skill')}' is waiting for human approval before executing {action['name']}.",
                "reasoning": "Human approval is required before this write/send action can continue.",
                "done": True,
                "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
                "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
            }

        next_index = index + 1
        next_progress = {
            **progress,
            trajectory_id: {"index": next_index, "approvalPending": False, "approvedActions": list(approved_actions)},
        }
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": action["name"], "arguments": action["arguments"]}],
            "content": None,
            "reasoning": action["reasoning"] or f"Replaying harvested skill '{skill.get('name', 'skill')}' step {next_index}/{len(actions)}.",
            "done": next_index >= len(actions),
            "state_out": {**state, "matchedSkillId": skill_id, "automata_trajectory_progress": next_progress},
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", ""), "trajectoryId": trajectory_id},
        }

    if state.get("matchedSkillId") == skill_id:
        return {
            "protocol_version": "1.0",
            "tool_calls": [],
            "content": f"Matched skill '{skill.get('name', 'skill')}', but it has no approved executable trajectory yet. Harvest and approve this skill before autonomous replay.",
            "reasoning": "Capability matched; stopped instead of falling back to an unrelated external runtime policy.",
            "done": True,
            "state_out": state,
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
        }

    url = str(payload.get("url") or agent_config.get("websiteUrl") or "").strip()
    if url:
        return {
            "protocol_version": "1.0",
            "tool_calls": [{"name": "browser.navigate", "arguments": {"url": url}}],
            "content": None,
            "reasoning": f"Matched skill '{skill.get('name', 'skill')}'. Navigating to the configured runtime surface before planning the skill steps.",
            "done": False,
            "state_out": {**state, "matchedSkillId": skill_id},
            "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
        }
    return {
        "protocol_version": "1.0",
        "tool_calls": [],
        "content": f"Matched skill '{skill.get('name', 'skill')}'. The trajectory is available as a draft and requires harvested executable steps before autonomous replay.",
        "reasoning": "Capability matched, but no executable trajectory steps are approved yet.",
        "done": True,
        "state_out": state,
        "capability_match": {"skillId": skill_id, "name": skill.get("name", ""), "status": skill.get("status", "")},
    }


async def agent_step_result(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent_config = await load_agent_config(agent_id)
    prompt = str(payload.get("prompt") or payload.get("task") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="task or prompt is required")

    payload = dict(payload)
    payload["prompt"] = prompt
    payload["task"] = prompt
    agent_config = _apply_runtime_overrides(agent_config, payload)

    context = await _capability_context(agent_config)
    state_in = payload.get("state_in") if isinstance(payload.get("state_in"), dict) else {}
    memory = state_in.get("memory") if isinstance(state_in.get("memory"), dict) else {}
    payload["agentConfig"] = _agent_config_payload(agent_config, context, memory)
    payload["context"] = {
        **(payload.get("context") if isinstance(payload.get("context"), dict) else {}),
        "automataCapabilities": context,
        "agentConfig": payload["agentConfig"],
    }
    await record_runtime_event(
        agent_id=agent_id,
        company_id=str(agent_config.get("companyId") or ""),
        event_type="agent.step.request",
        step_index=int(payload.get("step_index") or 0),
        payload={"prompt": prompt, "url": payload.get("url"), "agentConfig": payload["agentConfig"]},
    )

    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    skill_routing_disabled = bool(payload.get("disableSkillRouting") or payload_context.get("disableSkillRouting"))
    if skill_routing_disabled:
        router_trace = {
            "decision": "skill_routing_disabled",
            "reason": "Skill routing was disabled for this runtime smoke.",
            "confidence": 0.0,
            "candidates": [],
        }
    else:
        router_trace = await _route_skill_match(prompt, context["skills"])
    matched_skill = router_trace.get("skill") if router_trace.get("decision") == "matched_skill" else None
    matched_skill_id = str((matched_skill or {}).get("capabilityId") or (matched_skill or {}).get("skillId") or (matched_skill or {}).get("name") or "")
    router_public = {key: value for key, value in router_trace.items() if key != "skill"}
    if matched_skill and (_step_index(payload) == 0 or not state_in or state_in.get("matchedSkillId") == matched_skill_id):
        unavailable = _require_runtime_available(agent_config, _skill_callable(matched_skill).get("name", ""), matched_skill.get("runtimeRequirements") or [])
        if unavailable:
            data = {
                "protocol_version": "1.0",
                "tool_calls": [],
                "tool_results": [unavailable],
                "content": unavailable["error"],
                "reasoning": "Matched skill is unavailable for this AgentRuntime.",
                "done": True,
                "state_out": state_in,
                "capability_match": {"skillId": matched_skill_id, "name": matched_skill.get("name", ""), "status": matched_skill.get("status", "")},
            }
        else:
            data = await _web_skill_response(agent_config, matched_skill, prompt, payload)
    elif str(agent_config.get("runtimeType") or "") == "local_email_agent":
        router_public["fallbackRuntime"] = "local_email_agent"
        data = _email_agent_response(prompt, state_in)
    elif str(agent_config.get("runtimeType") or "") == "local_connector_agent":
        router_public["fallbackRuntime"] = "local_connector_agent"
        data = await _local_connector_agent_response(agent_config, prompt, state_in, payload)
    else:
        runtime_kind = _runtime_kind(agent_config.get("runtimeKind"))
        runtime_adapter = get_runtime_adapter(runtime_kind)
        router_public["fallbackRuntime"] = str(agent_config.get("runtimeType") or "external_agent_runtime")
        router_public["runtimeKind"] = runtime_kind
        router_public["runtimeAdapter"] = runtime_adapter.descriptor().model_dump()
        data = await runtime_adapter.step(payload, _runtime_adapter_context(agent_config, context))
        if isinstance(data, dict) and _external_runtime_looks_mismatched(agent_config, data):
            if matched_skill:
                data = await _web_skill_response(agent_config, matched_skill, prompt, payload)
            else:
                data = _site_fallback_response(agent_config, prompt, state_in)

    if isinstance(data, dict):
        data.setdefault("router_trace", router_public)
        data = _normalize_runtime_tool_calls(agent_config, data)
        data = _enforce_runtime_surface_permissions(agent_config, data, state_in)
        data = await _execute_connector_tool_calls(agent_config, data, payload)
        state_out = data.get("state_out") if isinstance(data.get("state_out"), dict) else {}
        data["state_out"] = {**state_out, "memory": {**memory, **(state_out.get("memory") if isinstance(state_out.get("memory"), dict) else {})}}
        state_out_for_mode = data.get("state_out") if isinstance(data.get("state_out"), dict) else {}
        data.setdefault(
            "executionMode",
            "skill_replay"
            if data.get("capability_match")
            else "connector_tool"
            if data.get("tool_results") or state_out_for_mode.get("pendingConnectorApproval")
            else "browser_tool"
            if _has_browser_tool_calls(data)
            else "generalist",
        )

    await record_runtime_event(
        agent_id=agent_id,
        company_id=str(agent_config.get("companyId") or ""),
        event_type="agent.step.result",
        step_index=int(payload.get("step_index") or 0),
        status="ok",
        result=data if isinstance(data, dict) else {"raw": data},
    )
    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    await _record_usage_event(
        email=str(agent_config.get("email") or ""),
        company_id=str(agent_config.get("companyId") or ""),
        agent_id=agent_id,
        run_id=str(payload.get("run_id") or payload.get("runId") or payload_context.get("runId") or ""),
        kind="agent_step",
        source=str((data or {}).get("executionMode") or "agent_step") if isinstance(data, dict) else "agent_step",
        metadata={
            "stepIndex": int(payload.get("step_index") or 0),
            "toolCallCount": len(data.get("tool_calls") or []) if isinstance(data, dict) and isinstance(data.get("tool_calls"), list) else 0,
        },
    )

    return data


async def agent_step(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent_config = await load_agent_config(agent_id)
    data = await agent_step_result(agent_id, payload)
    return {
        "agentId": agent_id,
        "agentConfigId": agent_id,
        "agentName": agent_config.get("name", ""),
        "runtimeEndpoint": agent_config.get("runtimeEndpoint", ""),
        "baseRuntimeEndpoint": agent_config.get("baseRuntimeEndpoint", ""),
        "result": data,
    }
