from __future__ import annotations

from typing import Any

from app.services.tool_synthesis import GENERIC_DISCOVERY_TOOLS
from app.services.tool_synthesis import summarize_tool_synthesis


INGESTION_STAGE_ACTIONS = {
    "connector_docs": "Attach OpenAPI/docs for API connectors or a start URL for web connectors.",
    "auth_state": "Configure required credentials or OAuth fields before runtime discovery.",
    "entity_mapping": "Generate and persist business entities from docs, schemas or runtime observations.",
    "tool_synthesis": "Generate typed tools with schemas, side effects, scopes and entity bindings.",
    "candidate_tasks": "Seed benchmark tasks so harvested trajectories can be judged and promoted.",
}


def _ingestion_playbook(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for stage in stages:
        status = str(stage.get("status") or "").strip()
        if status == "ready":
            continue
        key = str(stage.get("key") or "").strip()
        playbook.append(
            {
                "stage": key,
                "status": status or "pending",
                "target": str(stage.get("target") or ""),
                "severity": "high" if status == "pending" else "medium",
                "action": INGESTION_STAGE_ACTIONS.get(
                    key,
                    str(stage.get("summary") or "Complete this ingestion stage."),
                ),
            }
        )
    return playbook


def connector_capability_discovery(
    connector: dict[str, Any],
    toolkit: dict[str, Any],
    *,
    secret_placeholder: str = "__configured__",
) -> dict[str, Any]:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    connector_type = str(connector.get("type") or "api").lower()
    provider = str(connector.get("provider") or "official").lower()
    docs_urls = [
        str(config.get(key) or "").strip()
        for key in ("openApiUrl", "docsUrl", "sourceUrl")
        if str(config.get(key) or "").strip()
    ]
    surface_urls = [
        str(config.get(key) or "").strip()
        for key in ("startUrl", "baseUrl", "loginUrl")
        if str(config.get(key) or "").strip()
    ]
    auth_fields = list(toolkit.get("authFields") or [])
    credential_fields = connector.get("credentialFields") if isinstance(connector.get("credentialFields"), dict) else {}
    configured_auth = sum(
        1
        for field in auth_fields
        if credential_fields.get(field, {}).get("configured")
        or config.get(field) == secret_placeholder
        or bool(config.get(field))
    )
    tool_specs = list(toolkit.get("tools") or [])
    tool_synthesis = summarize_tool_synthesis(tool_specs, runtime_requirements=toolkit.get("runtimeRequirements", []))
    typed_tools = [
        str(tool.get("name") or "")
        for tool in tool_specs
        if str(tool.get("name") or "") and str(tool.get("name") or "") not in GENERIC_DISCOVERY_TOOLS
    ]
    tool_entity_names: list[str] = []
    read_tools: list[str] = []
    write_tools_for_entities: list[str] = []
    for tool in tool_specs:
        side_effects = str(tool.get("sideEffects") or "").lower()
        tool_name = str(tool.get("name") or "")
        if side_effects in {"write", "writes", "send", "mutates"}:
            if tool_name:
                write_tools_for_entities.append(tool_name)
        elif tool_name:
            read_tools.append(tool_name)
        tool_contract = tool.get("toolContract") if isinstance(tool.get("toolContract"), dict) else {}
        for value in [
            *(tool.get("inputEntities") if isinstance(tool.get("inputEntities"), list) else []),
            tool.get("outputEntity"),
            *(tool_contract.get("inputEntities") if isinstance(tool_contract.get("inputEntities"), list) else []),
            tool_contract.get("outputEntity"),
        ]:
            clean = str(value or "").strip()
            if clean and clean not in tool_entity_names:
                tool_entity_names.append(clean)
    raw_connector_entities = (
        connector.get("discoveredEntities")
        if isinstance(connector.get("discoveredEntities"), list)
        else connector.get("entityCandidates")
        if isinstance(connector.get("entityCandidates"), list)
        else []
    )
    connector_entity_candidates: list[str] = []
    for item in raw_connector_entities:
        clean = str((item.get("name") or item.get("entity") or "") if isinstance(item, dict) else item or "").strip()
        if clean and clean not in connector_entity_candidates:
            connector_entity_candidates.append(clean)
    entity_names = []
    for name in [*tool_entity_names, *connector_entity_candidates]:
        clean = str(name or "").strip()
        if clean and clean not in entity_names:
            entity_names.append(clean)
    discovery_gaps = []
    if provider == "custom" and connector_type == "api" and not docs_urls:
        discovery_gaps.append({"key": "docs", "label": "Add OpenAPI or documentation URL.", "target": "config.openApiUrl"})
    if provider == "custom" and connector_type == "web" and not (config.get("startUrl") or config.get("baseUrl")):
        discovery_gaps.append({"key": "startUrl", "label": "Add the web app start URL.", "target": "config.startUrl"})
    if auth_fields and configured_auth < len(auth_fields):
        discovery_gaps.append({"key": "auth", "label": "Configure required auth fields.", "target": "credentials"})
    if not tool_specs:
        discovery_gaps.append({"key": "tools", "label": "Publish or synthesize callable tools.", "target": "capabilities"})
    requires_docs = provider == "custom" and connector_type == "api"
    requires_surface = provider == "custom" and connector_type == "web"
    docs_ready = bool(docs_urls) or not requires_docs
    surface_ready = bool(surface_urls) or not requires_surface
    auth_ready = not auth_fields or configured_auth >= len(auth_fields)
    typed_tools_ready = provider != "custom" or bool(typed_tools)
    entity_source_ready = docs_ready if requires_docs else surface_ready if requires_surface else True
    entity_ready = bool(entity_names) or entity_source_ready
    pipeline_stages = [
        {
            "key": "connector_docs",
            "label": "Connector docs/OpenAPI",
            "status": "ready" if docs_ready and surface_ready else "pending",
            "target": "config.openApiUrl" if requires_docs else "config.startUrl" if requires_surface else "config",
            "summary": "Docs or start surface are available." if docs_ready and surface_ready else "Add API docs/OpenAPI or a web start URL.",
        },
        {
            "key": "auth_state",
            "label": "Auth state",
            "status": "ready" if auth_ready else "pending",
            "target": "credentials",
            "summary": f"{configured_auth}/{len(auth_fields)} required auth fields configured.",
        },
        {
            "key": "entity_mapping",
            "label": "Entity mapping",
            "status": "ready" if entity_ready else "pending",
            "target": "entities",
            "summary": "Entity discovery source is available." if entity_ready else "Provide docs or observations before entity mapping.",
        },
        {
            "key": "tool_synthesis",
            "label": "Typed tool synthesis",
            "status": "ready" if typed_tools_ready else "pending",
            "target": "capabilities",
            "summary": f"{len(typed_tools)} typed tools available." if typed_tools_ready else "Generate typed tools from docs, UI observations, or benchmarks.",
        },
        {
            "key": "candidate_tasks",
            "label": "Candidate tasks",
            "status": "recommended" if provider == "custom" else "ready",
            "target": "evals",
            "summary": "Seed benchmark tasks to harvest trajectories." if provider == "custom" else "Connector benchmark seeding is available.",
        },
    ]
    blocking_stages = [stage for stage in pipeline_stages if stage["status"] == "pending"]
    playbook = _ingestion_playbook(pipeline_stages)
    pipeline_state = "blocked" if blocking_stages else "needs_benchmark" if provider == "custom" else "ready"
    return {
        "mode": connector.get("discoveryMode") or ("task_scoped" if provider == "custom" else "official_toolkit"),
        "status": connector.get("discoveryStatus") or ("pending" if discovery_gaps or blocking_stages else "ready"),
        "surface": connector.get("surface") or ("browser" if connector_type == "web" else "api" if connector_type == "api" else connector_type),
        "docs": {
            "available": bool(docs_urls),
            "urls": docs_urls,
            "surfaceUrls": surface_urls,
            "generationStatus": connector.get("generationStatus", ""),
        },
        "auth": {
            "required": bool(auth_fields) or bool(connector.get("authRequired")),
            "requiredFields": auth_fields,
            "configuredFields": configured_auth,
            "totalFields": len(auth_fields),
        },
        "entityDiscovery": {
            "source": "openapi" if connector_type == "api" and docs_urls else "runtime_observation" if connector_type == "web" else "toolkit",
            "status": "available" if entity_source_ready else "pending",
        },
        "entityMapping": {
            "status": "mapped" if entity_names else "source_ready" if entity_source_ready else "pending",
            "businessObjectCount": len(entity_names),
            "businessObjects": entity_names,
            "source": "tool_contracts" if tool_entity_names else "connector_candidates" if connector_entity_candidates else "openapi" if docs_urls else "runtime_observation" if connector_type == "web" and entity_source_ready else "toolkit" if provider != "custom" else "",
            "sourceUrls": [*docs_urls, *surface_urls],
            "permissions": {
                "readTools": read_tools,
                "writeTools": write_tools_for_entities,
            },
            "readyForToolBinding": bool(entity_names and tool_specs),
            "nextAction": "Review and persist business entities from tool contracts." if entity_names else "Generate entity models from OpenAPI/schema/docs or runtime observations.",
        },
        "toolSynthesis": {**tool_synthesis, "typedToolCount": len(typed_tools), "typedTools": typed_tools},
        "candidateTasks": {
            "recommended": provider == "custom",
            "source": "benchmarks",
            "reason": "Custom connectors should generate capabilities from benchmark tasks." if provider == "custom" else "Official toolkit is ready for connector benchmark seeding.",
        },
        "ingestionPipeline": {
            "state": pipeline_state,
            "readyStages": sum(1 for stage in pipeline_stages if stage["status"] == "ready"),
            "totalStages": len(pipeline_stages),
            "blockedStages": [stage["key"] for stage in blocking_stages],
            "nextStage": (
                blocking_stages[0]
                if blocking_stages
                else next((stage for stage in pipeline_stages if stage["status"] == "recommended"), None)
            ),
            "stages": pipeline_stages,
            "playbook": playbook,
        },
        "gaps": discovery_gaps,
    }
