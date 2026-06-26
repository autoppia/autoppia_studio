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
    return {
        "businessObject": doc.get("name", ""),
        "aliases": aliases,
        "systemObjects": {
            "sourceConnectorId": doc.get("sourceConnectorId", ""),
            "source": doc.get("source", "manual"),
            "schemaName": schema_name,
            "sourcePaths": _field_source_paths(fields),
        },
        "relationships": relationship_refs,
        "relationshipTargets": [item["target"] for item in relationship_refs],
        "permissions": {
            "readTools": read_tools,
            "writeTools": write_tools,
            "scopes": scopes,
        },
        "readiness": {
            "status": "ready" if not readiness_gaps else "needs_mapping",
            "gaps": readiness_gaps,
            "hasIdentifier": bool(identifiers),
            "identifierFields": identifiers,
            "hasRelationships": bool(relationship_refs),
        },
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
