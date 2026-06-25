from __future__ import annotations

from typing import Any


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def summarize_connector_factory(connectors: list[dict[str, Any]], *, sample_limit: int = 8, gap_limit: int = 10) -> dict[str, Any]:
    entity_mapped = 0
    entity_source_ready = 0
    entity_pending = 0
    typed_tool_ready = 0
    tool_synthesis_pending = 0
    candidate_tasks_ready = 0
    ingestion_ready = 0
    ingestion_blocked = 0
    ready_stage_count = 0
    total_stage_count = 0
    gaps: list[dict[str, str]] = []
    samples: list[dict[str, Any]] = []
    for doc in connectors:
        discovery = doc.get("capabilityDiscovery") if isinstance(doc.get("capabilityDiscovery"), dict) else {}
        entity_mapping = discovery.get("entityMapping") if isinstance(discovery.get("entityMapping"), dict) else {}
        tool_synthesis = discovery.get("toolSynthesis") if isinstance(discovery.get("toolSynthesis"), dict) else {}
        candidate_tasks = discovery.get("candidateTasks") if isinstance(discovery.get("candidateTasks"), dict) else {}
        ingestion = discovery.get("ingestionPipeline") if isinstance(discovery.get("ingestionPipeline"), dict) else {}
        entity_status = str(entity_mapping.get("status") or "").strip().lower()
        ingestion_state = str(ingestion.get("state") or "").strip().lower()
        typed_tool_count = int(tool_synthesis.get("typedToolCount") or 0)
        ready_stages = int(ingestion.get("readyStages") or 0)
        total_stages = int(ingestion.get("totalStages") or 0)
        ready_stage_count += ready_stages
        total_stage_count += total_stages
        if entity_status == "mapped" or entity_mapping.get("readyForToolBinding"):
            entity_mapped += 1
        elif entity_status == "source_ready":
            entity_source_ready += 1
        else:
            entity_pending += 1
        if typed_tool_count > 0:
            typed_tool_ready += 1
        elif discovery:
            tool_synthesis_pending += 1
        if candidate_tasks.get("recommended") or int(candidate_tasks.get("count") or 0) > 0:
            candidate_tasks_ready += 1
        if ingestion_state == "ready":
            ingestion_ready += 1
        elif ingestion_state == "blocked":
            ingestion_blocked += 1
        if entity_status not in {"mapped", "source_ready"} and not entity_mapping.get("readyForToolBinding"):
            gaps.append({"key": "entity_mapping", "label": f"{doc.get('name') or 'Connector'} needs business entity mapping.", "target": "connectors"})
        if discovery and typed_tool_count == 0:
            gaps.append({"key": "tool_synthesis", "label": f"{doc.get('name') or 'Connector'} has no typed synthesized tools yet.", "target": "connectors"})
        if ingestion_state == "blocked":
            next_stage = ingestion.get("nextStage") if isinstance(ingestion.get("nextStage"), dict) else {}
            label = str(next_stage.get("summary") or next_stage.get("label") or "ingestion pipeline is blocked")
            gaps.append({"key": "ingestion", "label": f"{doc.get('name') or 'Connector'}: {label}.", "target": "connectors"})
        if len(samples) < sample_limit:
            samples.append(
                {
                    "connectorId": str(doc.get("connectorId") or ""),
                    "name": str(doc.get("name") or ""),
                    "entityMapping": entity_status or "unknown",
                    "businessObjects": _list_values(entity_mapping.get("businessObjects"))[:5],
                    "readyForToolBinding": bool(entity_mapping.get("readyForToolBinding")),
                    "typedToolCount": typed_tool_count,
                    "governedToolCount": int(tool_synthesis.get("governedToolCount") or 0),
                    "candidateTasksRecommended": bool(candidate_tasks.get("recommended")),
                    "ingestionState": ingestion_state or "unknown",
                    "readyStages": ready_stages,
                    "totalStages": total_stages,
                }
            )
    return {
        "total": len(connectors),
        "entityMapped": entity_mapped,
        "entitySourceReady": entity_source_ready,
        "entityPending": entity_pending,
        "typedToolReady": typed_tool_ready,
        "toolSynthesisPending": tool_synthesis_pending,
        "candidateTasksReady": candidate_tasks_ready,
        "ingestionReady": ingestion_ready,
        "ingestionBlocked": ingestion_blocked,
        "readyStages": ready_stage_count,
        "totalStages": total_stage_count,
        "sample": samples,
        "gaps": gaps[:gap_limit],
    }
