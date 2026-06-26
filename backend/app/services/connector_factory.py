from __future__ import annotations

from typing import Any

from app.services.tool_synthesis import tool_hardening_playbook


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
    hardened_tool_count = 0
    needs_hardening_count = 0
    hardening_gap_counts: dict[str, int] = {}
    candidate_tasks_ready = 0
    ingestion_ready = 0
    ingestion_blocked = 0
    total_synthesized_tools = 0
    ready_stage_count = 0
    total_stage_count = 0
    gaps: list[dict[str, str]] = []
    ingestion_playbook: list[dict[str, Any]] = []
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
        hardened_count = int(tool_synthesis.get("hardenedToolCount") or 0)
        needs_hardening = int(tool_synthesis.get("needsHardeningCount") or 0)
        total_synthesized_tools += hardened_count + needs_hardening
        hardened_tool_count += hardened_count
        needs_hardening_count += needs_hardening
        hardening_gaps = tool_synthesis.get("hardeningGaps") if isinstance(tool_synthesis.get("hardeningGaps"), dict) else {}
        for key, value in hardening_gaps.items():
            clean_key = str(key or "").strip()
            if not clean_key:
                continue
            hardening_gap_counts[clean_key] = hardening_gap_counts.get(clean_key, 0) + int(value or 0)
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
        if needs_hardening:
            gaps.append({"key": "tool_hardening", "label": f"{doc.get('name') or 'Connector'} has {needs_hardening} synthesized tool(s) needing hardening.", "target": "connectors"})
        if ingestion_state == "blocked":
            next_stage = ingestion.get("nextStage") if isinstance(ingestion.get("nextStage"), dict) else {}
            label = str(next_stage.get("summary") or next_stage.get("label") or "ingestion pipeline is blocked")
            gaps.append({"key": "ingestion", "label": f"{doc.get('name') or 'Connector'}: {label}.", "target": "connectors"})
        for item in ingestion.get("playbook") if isinstance(ingestion.get("playbook"), list) else []:
            if not isinstance(item, dict):
                continue
            ingestion_playbook.append(
                {
                    "connectorId": str(doc.get("connectorId") or ""),
                    "connectorName": str(doc.get("name") or ""),
                    **item,
                }
            )
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
                    "hardenedToolCount": hardened_count,
                    "needsHardeningCount": needs_hardening,
                    "hardeningGaps": hardening_gaps,
                    "candidateTasksRecommended": bool(candidate_tasks.get("recommended")),
                    "ingestionState": ingestion_state or "unknown",
                    "readyStages": ready_stages,
                    "totalStages": total_stages,
                }
            )
    tool_gate_blockers = {
        **hardening_gap_counts,
        **({"tool_synthesis_pending": tool_synthesis_pending} if tool_synthesis_pending else {}),
    }
    tool_gate_ready = bool(total_synthesized_tools) and not needs_hardening_count and not tool_synthesis_pending
    return {
        "total": len(connectors),
        "entityMapped": entity_mapped,
        "entitySourceReady": entity_source_ready,
        "entityPending": entity_pending,
        "typedToolReady": typed_tool_ready,
        "toolSynthesisPending": tool_synthesis_pending,
        "hardenedToolCount": hardened_tool_count,
        "needsHardeningCount": needs_hardening_count,
        "toolHardeningGaps": [
            {"name": key, "count": hardening_gap_counts[key]}
            for key in sorted(hardening_gap_counts, key=lambda item: (-hardening_gap_counts[item], item))
        ],
        "toolHardeningPlaybook": tool_hardening_playbook(hardening_gap_counts),
        "toolProductionGate": {
            "state": "ready" if tool_gate_ready else ("no_tools" if not total_synthesized_tools else "needs_hardening"),
            "ready": tool_gate_ready,
            "totalTools": total_synthesized_tools,
            "hardenedTools": hardened_tool_count,
            "needsHardening": needs_hardening_count,
            "typedConnectorCoverage": {"ready": typed_tool_ready, "total": len(connectors)},
            "checks": {
                "typedTools": bool(total_synthesized_tools) and tool_synthesis_pending == 0,
                "hardenedContracts": bool(total_synthesized_tools) and needs_hardening_count == 0,
                "schemasPoliciesScopesEntities": bool(total_synthesized_tools) and not hardening_gap_counts,
            },
            "blockers": [
                {"name": key, "count": tool_gate_blockers[key]}
                for key in sorted(tool_gate_blockers, key=lambda item: (-tool_gate_blockers[item], item))
            ],
            "hardeningPlaybook": tool_hardening_playbook(tool_gate_blockers),
        },
        "candidateTasksReady": candidate_tasks_ready,
        "ingestionReady": ingestion_ready,
        "ingestionBlocked": ingestion_blocked,
        "ingestionPlaybook": ingestion_playbook[:gap_limit],
        "readyStages": ready_stage_count,
        "totalStages": total_stage_count,
        "sample": samples,
        "gaps": gaps[:gap_limit],
    }
