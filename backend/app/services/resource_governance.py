from __future__ import annotations

from typing import Any


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unspecified").strip() or "unspecified"
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def resource_contract(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource.get("resourceContract")
    return contract if isinstance(contract, dict) else {}


def resource_indexing(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource_contract(resource)
    indexing = contract.get("indexing")
    return indexing if isinstance(indexing, dict) else {}


def resource_governance(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource_contract(resource)
    governance = contract.get("governance")
    return governance if isinstance(governance, dict) else {}


def resource_acl(resource: dict[str, Any]) -> dict[str, Any]:
    governance = resource_governance(resource)
    acl = governance.get("acl") if isinstance(governance.get("acl"), dict) else resource.get("acl") if isinstance(resource.get("acl"), dict) else {}
    visibility = str(acl.get("visibility") or "").strip()
    return {
        "explicit": bool(acl),
        "visibility": visibility or "unspecified",
        "allowedRoles": _list_values(acl.get("allowedRoles")),
        "allowedUsers": _list_values(acl.get("allowedUsers")),
    }


def resource_read_tools(resource: dict[str, Any]) -> list[str]:
    contract = resource_contract(resource)
    return _list_values(contract.get("readTools") or resource.get("readTools"))


def resource_vector_id(resource: dict[str, Any]) -> str:
    indexing = resource_indexing(resource)
    return str(resource.get("vectorDatabaseId") or indexing.get("vectorDatabaseId") or "").strip()


def resource_status(resource: dict[str, Any]) -> str:
    indexing = resource_indexing(resource)
    return str(resource.get("status") or resource_contract(resource).get("status") or indexing.get("status") or "unknown").strip().lower()


def resource_indexed(resource: dict[str, Any]) -> bool:
    indexing = resource_indexing(resource)
    if isinstance(indexing.get("indexed"), bool):
        return indexing["indexed"]
    return resource_status(resource) in {"indexed", "ready", "active", "completed"}


def resource_citable(resource: dict[str, Any]) -> bool:
    governance = resource_governance(resource)
    citability = governance.get("citability")
    if isinstance(citability, dict) and isinstance(citability.get("citable"), bool):
        return citability["citable"]
    return resource_indexed(resource)


def resource_payload(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource_contract(resource)
    indexing = resource_indexing(resource)
    governance = resource_governance(resource)
    citability = governance.get("citability") if isinstance(governance.get("citability"), dict) else {}
    freshness = governance.get("freshness") if isinstance(governance.get("freshness"), dict) else {}
    filename = resource.get("filename") or resource.get("name") or resource.get("title") or ""
    indexed = resource_indexed(resource)
    return {
        "resourceId": resource.get("resourceId") or resource.get("documentId", ""),
        "documentId": resource.get("documentId", ""),
        "resourceKind": resource.get("resourceKind") or contract.get("resourceKind") or "document",
        "filename": filename,
        "name": filename or "Untitled resource",
        "status": resource.get("status") or contract.get("status") or "uploaded",
        "source": resource.get("source") or governance.get("source") or "upload",
        "connectorId": resource.get("connectorId") or governance.get("connectorId") or "",
        "vectorDatabaseId": resource_vector_id(resource),
        "vectorDatabaseName": resource.get("vectorDatabaseName") or indexing.get("vectorDatabaseName") or "",
        "vectorCollectionName": resource.get("vectorCollectionName") or indexing.get("vectorCollectionName") or "",
        "contentType": resource.get("contentType") or governance.get("contentType") or "",
        "size": resource.get("size", 0),
        "indexed": indexed,
        "citable": resource_citable(resource),
        "citationLabel": citability.get("citationLabel") or resource.get("citationLabel") or resource.get("filename") or "",
        "sourceUrl": citability.get("sourceUrl") or "",
        "freshnessStatus": freshness.get("status") or ("current" if indexed else "indexing"),
        "readTools": resource_read_tools(resource),
        "resourceContract": contract,
        "createdAt": resource.get("createdAt"),
        "updatedAt": resource.get("updatedAt"),
    }


def resource_gate(resource: dict[str, Any]) -> dict[str, Any]:
    contract = resource_contract(resource)
    gate = contract.get("resourceGate")
    return gate if isinstance(gate, dict) else {}


def derived_resource_gate(resource: dict[str, Any]) -> dict[str, Any]:
    gate = resource_gate(resource)
    if gate:
        return gate
    checks = {
        "indexed": resource_indexed(resource),
        "vectorStore": bool(resource_vector_id(resource)),
        "readTools": bool(resource_read_tools(resource)),
        "acl": bool(resource_acl(resource).get("explicit")),
        "citability": resource_citable(resource),
    }
    blockers = [key for key, ready in checks.items() if not ready]
    return {
        "state": "ready" if not blockers else "blocked",
        "readyForRuntime": not blockers,
        "blockers": blockers,
        "nextActions": [],
        "checks": checks,
    }


def summarize_resource_governance(resources: list[dict[str, Any]], *, sample_limit: int = 8) -> dict[str, Any]:
    read_tools = _dedupe([tool for resource in resources for tool in resource_read_tools(resource)])
    gates = [derived_resource_gate(resource) for resource in resources]
    runtime_ready = sum(1 for gate in gates if bool(gate.get("readyForRuntime")))
    gate_states = _sorted_counts([str(gate.get("state") or "unknown").lower() for gate in gates])
    gate_blockers = _sorted_counts([blocker for gate in gates for blocker in _list_values(gate.get("blockers"))])
    resource_acls = [resource_acl(resource) for resource in resources]
    with_acl = sum(1 for acl in resource_acls if acl.get("explicit"))
    roles = _dedupe([role for acl in resource_acls for role in _list_values(acl.get("allowedRoles"))])
    users = _dedupe([user for acl in resource_acls for user in _list_values(acl.get("allowedUsers"))])
    sample: list[dict[str, Any]] = []
    for resource in resources[:sample_limit]:
        governance = resource_governance(resource)
        freshness = governance.get("freshness") if isinstance(governance.get("freshness"), dict) else {}
        citability = governance.get("citability") if isinstance(governance.get("citability"), dict) else {}
        gate = derived_resource_gate(resource)
        sample.append(
            {
                "documentId": str(resource.get("documentId") or ""),
                "resourceId": str(resource.get("resourceId") or resource.get("documentId") or ""),
                "name": str(resource.get("filename") or resource.get("name") or resource.get("title") or "Untitled resource"),
                "resourceKind": str(resource.get("resourceKind") or resource_contract(resource).get("resourceKind") or "document"),
                "status": resource_status(resource),
                "indexed": resource_indexed(resource),
                "citable": resource_citable(resource),
                "freshnessStatus": str(freshness.get("status") or ("current" if resource_indexed(resource) else "indexing")),
                "citationLabel": str(citability.get("citationLabel") or resource.get("filename") or ""),
                "vectorDatabaseId": resource_vector_id(resource),
                "aclVisibility": resource_acl(resource)["visibility"],
                "readTools": resource_read_tools(resource)[:8],
                "runtimeGate": {
                    "state": str(gate.get("state") or "unknown"),
                    "readyForRuntime": bool(gate.get("readyForRuntime")),
                    "blockers": _list_values(gate.get("blockers"))[:8],
                },
            }
        )
    total = len(resources)
    indexed = sum(1 for resource in resources if resource_indexed(resource))
    citable = sum(1 for resource in resources if resource_citable(resource))
    with_contract = sum(1 for resource in resources if resource_contract(resource))
    with_vector_store = sum(1 for resource in resources if resource_vector_id(resource))
    visibility_counts = _sorted_counts([str(acl.get("visibility") or "unspecified") for acl in resource_acls])
    acl = {
        "withAcl": with_acl,
        "companyVisible": sum(1 for item in resource_acls if item.get("visibility") == "company"),
        "restricted": sum(1 for item in resource_acls if item.get("visibility") not in {"", "company", "unspecified"}),
        "visibility": visibility_counts,
        "roles": roles[:20],
        "users": users[:20],
    }
    gaps = [
        gap
        for gap in [
            {"key": "resource_contracts", "label": "Knowledge documents exist but are not exposed as governed resources.", "target": "knowledge"} if total and with_contract == 0 else None,
            {"key": "resource_acl", "label": "Knowledge resources need explicit ACL visibility before runtime grounding.", "target": "knowledge"} if total and with_acl < total else None,
            {"key": "resource_indexing", "label": "Knowledge resources exist but none are indexed for retrieval.", "target": "knowledge"} if total and indexed == 0 else None,
            {"key": "resource_citations", "label": "Knowledge resources are not citable yet, so answers cannot cite source evidence.", "target": "knowledge"} if total and citable == 0 else None,
            {"key": "resource_read_tools", "label": "Knowledge resources need read-only tools before AgentRuntimes can ground work in them.", "target": "knowledge"} if total and not read_tools else None,
            {"key": "vector_store", "label": "Knowledge resources are not linked to vector stores.", "target": "knowledge"} if total and with_vector_store == 0 else None,
        ]
        if gap
    ]
    return {
        "total": total,
        "indexed": indexed,
        "citable": citable,
        "withResourceContract": with_contract,
        "withVectorStore": with_vector_store,
        "acl": acl,
        "status": _sorted_counts([resource_status(resource) for resource in resources]),
        "readTools": read_tools[:20],
        "runtimeGate": {
            "ready": runtime_ready,
            "blocked": max(0, total - runtime_ready),
            "states": gate_states,
            "blockers": gate_blockers,
        },
        "sample": sample,
        "ready": bool(total and runtime_ready == total),
        "gaps": gaps,
    }
