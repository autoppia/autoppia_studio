from app.services.entity_mapping import build_entity_mapping_contract
from app.services.entity_mapping import relationship_edges
from app.services.entity_mapping import summarize_entity_mapping


def test_entity_mapping_contract_models_aliases_relationships_permissions_and_readiness():
    contract = build_entity_mapping_contract(
        {
            "name": "Poliza",
            "sourceConnectorId": "erp-1",
            "source": "openapi",
            "fields": [
                {"name": "id", "type": "string", "role": "identifier", "sourcePath": "$.id"},
                {"name": "clienteId", "type": "string", "role": "reference", "sourcePath": "$.cliente_id"},
            ],
            "relationships": [
                {"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"},
                {"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"},
            ],
            "metadata": {
                "aliases": ["Policy", "Insurance policy"],
                "schemaName": "PolicyRead",
                "permissions": {
                    "readTools": ["erp.search_policies"],
                    "writeTools": ["erp.update_policy"],
                    "scopes": ["policy:read", "policy:write"],
                },
            },
        }
    )

    assert contract["businessObject"] == "Poliza"
    assert contract["aliases"] == ["Policy", "Insurance policy"]
    assert contract["systemObjects"] == {
        "sourceConnectorId": "erp-1",
        "source": "openapi",
        "schemaName": "PolicyRead",
        "sourcePaths": ["$.id", "$.cliente_id"],
    }
    assert contract["relationships"] == [
        {"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"}
    ]
    assert contract["relationshipTargets"] == ["Cliente"]
    assert contract["permissions"]["readTools"] == ["erp.search_policies"]
    assert contract["permissions"]["writeTools"] == ["erp.update_policy"]
    assert contract["toolBinding"] == {
        "ready": True,
        "readable": True,
        "writable": True,
        "writeGoverned": True,
        "blockers": [],
        "nextActions": [],
    }
    assert contract["readiness"]["status"] == "ready"
    assert contract["readiness"]["identifierFields"] == ["id"]
    assert contract["readiness"]["hasRelationships"] is True
    assert contract["mappingCoverage"] == {
        "score": 1.0,
        "passedChecks": 7,
        "totalChecks": 7,
        "checks": {
            "aliases": True,
            "fields": True,
            "identifier": True,
            "permissions": True,
            "sourceConnector": True,
            "systemSchema": True,
            "relationships": True,
        },
        "fieldCount": 2,
        "relationshipCount": 1,
        "sourcePathCount": 2,
    }


def test_entity_mapping_contract_surfaces_mapping_gaps():
    contract = build_entity_mapping_contract({"name": "Siniestro"})

    assert contract["readiness"]["status"] == "needs_mapping"
    assert contract["readiness"]["gaps"] == ["aliases", "fields", "permissions", "source connector"]
    assert contract["toolBinding"] == {
        "ready": False,
        "readable": False,
        "writable": False,
        "writeGoverned": True,
        "blockers": ["identifier", "read_access", "relationships"],
        "nextActions": [
            "Mark at least one identifier field.",
            "Attach a read tool or read scope before binding this entity to runtime context.",
            "Declare relationships to connected business objects for graph-level reuse.",
        ],
    }
    assert contract["readiness"]["hasIdentifier"] is False
    assert contract["mappingCoverage"]["score"] == 0.0
    assert contract["mappingCoverage"]["checks"]["fields"] is False


def test_relationship_edges_remain_stable_for_graph_views():
    edges = relationship_edges(
        {
            "name": "Poliza",
            "relationships": [
                {"name": "cliente", "kind": "belongsTo", "target": "Cliente", "via": "clienteId"},
                {"name": "empty", "target": ""},
            ],
        }
    )

    assert edges == [
        {
            "from": "Poliza",
            "to": "Cliente",
            "name": "cliente",
            "kind": "belongsTo",
            "via": "clienteId",
            "description": "",
        }
    ]


def test_summarize_entity_mapping_counts_readiness_and_binding_gaps():
    summary = summarize_entity_mapping(
        [
            {
                "entityId": "policy-1",
                "name": "Poliza",
                "sourceConnectorId": "erp-1",
                "fields": [{"name": "id", "role": "identifier"}],
                "relationships": [{"name": "cliente", "target": "Cliente", "via": "clienteId"}],
                "metadata": {
                    "aliases": ["Policy"],
                    "permissions": {
                        "readTools": ["erp.search_policies"],
                        "scopes": ["policy:read"],
                    },
                },
            },
            {
                "entityId": "claim-1",
                "name": "Siniestro",
                "fields": [{"name": "status"}],
                "metadata": {"aliases": ["Claim"]},
            },
        ],
        sample_limit=1,
    )

    assert summary["total"] == 2
    assert summary["ready"] == 1
    assert summary["withAliases"] == 2
    assert summary["withRelationships"] == 1
    assert summary["withPermissions"] == 1
    assert summary["toolBindingReady"] == 1
    assert summary["coverageScore"] == 0.572
    assert summary["gaps"] == [
        {"name": "permissions", "count": 1},
        {"name": "source connector", "count": 1},
    ]
    assert summary["bindingBlockers"] == [
        {"name": "identifier", "count": 1},
        {"name": "read_access", "count": 1},
        {"name": "relationships", "count": 1},
    ]
    assert summary["sample"] == [
        {
            "entityId": "policy-1",
            "name": "Poliza",
            "status": "ready",
            "coverageScore": 0.857,
            "toolBindingReady": True,
            "gaps": [],
            "blockers": [],
        }
    ]
