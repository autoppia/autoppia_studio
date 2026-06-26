from __future__ import annotations

from typing import Any


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _field_source_paths(fields: list[Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        path = str(field.get("sourcePath") or field.get("jsonPath") or field.get("column") or "").strip()
        if path and path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def _relationship_refs(relationships: list[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        target = str(rel.get("target") or "").strip()
        if not target:
            continue
        item = {
            "name": str(rel.get("name") or "").strip(),
            "kind": str(rel.get("kind") or "references").strip(),
            "target": target,
            "via": str(rel.get("via") or "").strip(),
        }
        key = (item["name"], item["target"], item["via"])
        if key not in seen:
            refs.append(item)
            seen.add(key)
    return refs


def _identifier_fields(fields: list[Any]) -> list[str]:
    return [
        str(field.get("name") or "").strip()
        for field in fields
        if isinstance(field, dict)
        and str(field.get("name") or "").strip()
        and (
            str(field.get("role") or "").lower() == "identifier"
            or str(field.get("name") or "").strip().lower() in {"id", "uuid"}
        )
    ]


def build_entity_mapping_contract(
    doc: dict[str, Any],
    *,
    fields: list[Any] | None = None,
    relationships: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields = fields if isinstance(fields, list) else doc.get("fields") if isinstance(doc.get("fields"), list) else []
    relationships = relationships if isinstance(relationships, list) else doc.get("relationships") if isinstance(doc.get("relationships"), list) else []
    metadata = metadata if isinstance(metadata, dict) else doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    aliases = string_list(metadata.get("aliases") or metadata.get("businessAliases"))
    schema_name = str(metadata.get("schemaName") or metadata.get("tableName") or metadata.get("objectName") or "").strip()
    permissions = metadata.get("permissions") if isinstance(metadata.get("permissions"), dict) else {}
    read_tools = string_list(metadata.get("readTools") or permissions.get("readTools"))
    write_tools = string_list(metadata.get("writeTools") or permissions.get("writeTools"))
    scopes = string_list(metadata.get("scopes") or permissions.get("scopes"))
    relationship_refs = _relationship_refs(relationships)
    identifiers = _identifier_fields(fields)
    readiness_gaps = []
    if not aliases:
        readiness_gaps.append("aliases")
    if not fields:
        readiness_gaps.append("fields")
    if not read_tools and not write_tools and not scopes:
        readiness_gaps.append("permissions")
    if not doc.get("sourceConnectorId"):
        readiness_gaps.append("source connector")
    source_paths = _field_source_paths(fields)
    coverage_checks = {
        "aliases": bool(aliases),
        "fields": bool(fields),
        "identifier": bool(identifiers),
        "permissions": bool(read_tools or write_tools or scopes),
        "sourceConnector": bool(doc.get("sourceConnectorId")),
        "systemSchema": bool(schema_name or source_paths),
        "relationships": bool(relationship_refs),
    }
    passed_checks = sum(1 for ready in coverage_checks.values() if ready)
    tool_binding_blockers: list[str] = []
    if not identifiers:
        tool_binding_blockers.append("identifier")
    if not read_tools and not scopes:
        tool_binding_blockers.append("read_access")
    if write_tools and not scopes:
        tool_binding_blockers.append("write_scopes")
    if not relationship_refs:
        tool_binding_blockers.append("relationships")
    return {
        "businessObject": doc.get("name", ""),
        "aliases": aliases,
        "systemObjects": {
            "sourceConnectorId": doc.get("sourceConnectorId", ""),
            "source": doc.get("source", "manual"),
            "schemaName": schema_name,
            "sourcePaths": source_paths,
        },
        "relationships": relationship_refs,
        "relationshipTargets": [item["target"] for item in relationship_refs],
        "permissions": {
            "readTools": read_tools,
            "writeTools": write_tools,
            "scopes": scopes,
        },
        "toolBinding": {
            "ready": bool(identifiers and (read_tools or scopes) and not (write_tools and not scopes)),
            "readable": bool(read_tools or scopes),
            "writable": bool(write_tools),
            "writeGoverned": bool(not write_tools or scopes),
            "blockers": tool_binding_blockers,
            "nextActions": [
                action
                for action in [
                    "Mark at least one identifier field." if "identifier" in tool_binding_blockers else "",
                    "Attach a read tool or read scope before binding this entity to runtime context." if "read_access" in tool_binding_blockers else "",
                    "Attach write scopes before exposing write tools for this entity." if "write_scopes" in tool_binding_blockers else "",
                    "Declare relationships to connected business objects for graph-level reuse." if "relationships" in tool_binding_blockers else "",
                ]
                if action
            ],
        },
        "readiness": {
            "status": "ready" if not readiness_gaps else "needs_mapping",
            "gaps": readiness_gaps,
            "hasIdentifier": bool(identifiers),
            "identifierFields": identifiers,
            "hasRelationships": bool(relationship_refs),
        },
        "mappingCoverage": {
            "score": round(passed_checks / len(coverage_checks), 3),
            "passedChecks": passed_checks,
            "totalChecks": len(coverage_checks),
            "checks": coverage_checks,
            "fieldCount": len(fields),
            "relationshipCount": len(relationship_refs),
            "sourcePathCount": len(source_paths),
        },
    }


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def summarize_entity_mapping(entities: list[dict[str, Any]], *, sample_limit: int = 5) -> dict[str, Any]:
    ready = 0
    with_aliases = 0
    with_relationships = 0
    with_permissions = 0
    binding_ready = 0
    coverage_total = 0.0
    gap_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for entity in entities:
        contract = build_entity_mapping_contract(entity)
        readiness = contract.get("readiness") if isinstance(contract.get("readiness"), dict) else {}
        coverage = contract.get("mappingCoverage") if isinstance(contract.get("mappingCoverage"), dict) else {}
        permissions = contract.get("permissions") if isinstance(contract.get("permissions"), dict) else {}
        tool_binding = contract.get("toolBinding") if isinstance(contract.get("toolBinding"), dict) else {}
        if readiness.get("status") == "ready":
            ready += 1
        if contract.get("aliases"):
            with_aliases += 1
        if contract.get("relationships"):
            with_relationships += 1
        if permissions.get("readTools") or permissions.get("writeTools") or permissions.get("scopes"):
            with_permissions += 1
        if tool_binding.get("ready"):
            binding_ready += 1
        coverage_total += _safe_float(coverage.get("score"))
        for gap in readiness.get("gaps") if isinstance(readiness.get("gaps"), list) else []:
            key = str(gap or "").strip()
            if key:
                gap_counts[key] = gap_counts.get(key, 0) + 1
        for blocker in tool_binding.get("blockers") if isinstance(tool_binding.get("blockers"), list) else []:
            key = str(blocker or "").strip()
            if key:
                blocker_counts[key] = blocker_counts.get(key, 0) + 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "entityId": str(entity.get("entityId") or ""),
                    "name": str(entity.get("name") or ""),
                    "status": str(readiness.get("status") or "unknown"),
                    "coverageScore": _safe_float(coverage.get("score")),
                    "toolBindingReady": bool(tool_binding.get("ready")),
                    "gaps": readiness.get("gaps") if isinstance(readiness.get("gaps"), list) else [],
                    "blockers": tool_binding.get("blockers") if isinstance(tool_binding.get("blockers"), list) else [],
                }
            )
    return {
        "total": len(entities),
        "ready": ready,
        "withAliases": with_aliases,
        "withRelationships": with_relationships,
        "withPermissions": with_permissions,
        "toolBindingReady": binding_ready,
        "coverageScore": round(coverage_total / len(entities), 3) if entities else 0.0,
        "gaps": [
            {"name": key, "count": gap_counts[key]}
            for key in sorted(gap_counts, key=lambda item: (-gap_counts[item], item))
        ],
        "bindingBlockers": [
            {"name": key, "count": blocker_counts[key]}
            for key in sorted(blocker_counts, key=lambda item: (-blocker_counts[item], item))
        ],
        "sample": samples,
    }


def relationship_edges(entity: dict[str, Any]) -> list[dict[str, Any]]:
    source = str(entity.get("name") or "")
    edges = []
    for rel in entity.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        target = str(rel.get("target") or "").strip()
        if not source or not target:
            continue
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
    return edges
