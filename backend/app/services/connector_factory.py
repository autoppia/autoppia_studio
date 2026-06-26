from __future__ import annotations

from typing import Any

from app.services.tool_synthesis import tool_hardening_playbook


FACTORY_PIPELINE_ACTIONS = {
    "connectors_present": {
        "area": "connectors",
        "severity": "high",
        "action": "Attach at least one connector before running the Capability Factory pipeline.",
    },
    "ingestion_pipeline": {
        "area": "ingestion",
        "severity": "high",
        "action": "Complete connector ingestion with docs/auth/surface evidence before synthesis.",
    },
    "entity_mapping": {
        "area": "entities",
        "severity": "high",
        "action": "Map connector schemas or observations to business entities before tool binding.",
    },
    "typed_tools": {
        "area": "tools",
        "severity": "high",
        "action": "Synthesize typed atomic tools with schemas, side effects, scopes and entity bindings.",
    },
    "candidate_tasks": {
        "area": "evals",
        "severity": "medium",
        "action": "Generate candidate benchmark tasks from discovered connector capabilities.",
    },
    "tool_production": {
        "area": "tools",
        "severity": "high",
        "action": "Harden synthesized tools before exposing them as production capabilities.",
    },
}


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _factory_pipeline_playbook(gap_counts: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = FACTORY_PIPELINE_ACTIONS.get(
            gap,
            {
                "area": "capabilities",
                "severity": "medium",
                "action": "Review the Capability Factory pipeline before production use.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


def _factory_pipeline_gate(
    *,
    total: int,
    ingestion_ready: int,
    ingestion_blocked: int,
    entity_mapped: int,
    typed_tool_ready: int,
    tool_synthesis_pending: int,
    candidate_tasks_ready: int,
    tool_gate_ready: bool,
) -> dict[str, Any]:
    gap_counts: dict[str, int] = {}
    if total == 0:
        gap_counts["connectors_present"] = 1
    if total and (ingestion_ready < total or ingestion_blocked):
        gap_counts["ingestion_pipeline"] = max(total - ingestion_ready, ingestion_blocked)
    if total and entity_mapped < total:
        gap_counts["entity_mapping"] = total - entity_mapped
    if total and (typed_tool_ready < total or tool_synthesis_pending):
        gap_counts["typed_tools"] = max(total - typed_tool_ready, tool_synthesis_pending)
    if total and candidate_tasks_ready < total:
        gap_counts["candidate_tasks"] = total - candidate_tasks_ready
    if not tool_gate_ready:
        gap_counts["tool_production"] = max(1, total)
    checks = {
        "connectorsPresent": total > 0,
        "ingestionComplete": total > 0 and ingestion_ready == total and ingestion_blocked == 0,
        "entityMappingComplete": total > 0 and entity_mapped == total,
        "typedToolsReady": total > 0 and typed_tool_ready == total and tool_synthesis_pending == 0,
        "candidateTasksSeeded": total > 0 and candidate_tasks_ready == total,
        "toolProductionReady": tool_gate_ready,
    }
    blockers = [name for name, ready in checks.items() if not ready]
    return {
        "state": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "checks": checks,
        "blockers": blockers,
        "hardeningPlaybook": _factory_pipeline_playbook(gap_counts),
    }


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
    send_tool_count = 0
    send_tools: list[str] = []
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
        connector_send_tools = _list_values(tool_synthesis.get("sendTools"))
        total_synthesized_tools += hardened_count + needs_hardening
        send_tool_count += int(tool_synthesis.get("sendToolCount") or len(connector_send_tools))
        send_tools.extend(connector_send_tools)
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
                    "sendToolCount": int(tool_synthesis.get("sendToolCount") or len(connector_send_tools)),
                    "sendTools": connector_send_tools[:8],
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
    factory_pipeline_gate = _factory_pipeline_gate(
        total=len(connectors),
        ingestion_ready=ingestion_ready,
        ingestion_blocked=ingestion_blocked,
        entity_mapped=entity_mapped,
        typed_tool_ready=typed_tool_ready,
        tool_synthesis_pending=tool_synthesis_pending,
        candidate_tasks_ready=candidate_tasks_ready,
        tool_gate_ready=tool_gate_ready,
    )
    return {
        "total": len(connectors),
        "entityMapped": entity_mapped,
        "entitySourceReady": entity_source_ready,
        "entityPending": entity_pending,
        "typedToolReady": typed_tool_ready,
        "toolSynthesisPending": tool_synthesis_pending,
        "hardenedToolCount": hardened_tool_count,
        "needsHardeningCount": needs_hardening_count,
        "sendToolCount": send_tool_count,
        "sendTools": _dedupe_values(send_tools)[:20],
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
        "factoryPipelineGate": factory_pipeline_gate,
        "candidateTasksReady": candidate_tasks_ready,
        "ingestionReady": ingestion_ready,
        "ingestionBlocked": ingestion_blocked,
        "ingestionPlaybook": ingestion_playbook[:gap_limit],
        "readyStages": ready_stage_count,
        "totalStages": total_stage_count,
        "sample": samples,
        "gaps": gaps[:gap_limit],
    }
