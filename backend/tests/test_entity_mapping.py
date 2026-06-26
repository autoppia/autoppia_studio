from app.services.entity_mapping import build_entity_mapping_contract
from app.services.entity_mapping import relationship_edges


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
    assert contract["readiness"]["status"] == "ready"
    assert contract["readiness"]["identifierFields"] == ["id"]
    assert contract["readiness"]["hasRelationships"] is True


def test_entity_mapping_contract_surfaces_mapping_gaps():
    contract = build_entity_mapping_contract({"name": "Siniestro"})

    assert contract["readiness"]["status"] == "needs_mapping"
    assert contract["readiness"]["gaps"] == ["aliases", "fields", "permissions", "source connector"]
    assert contract["readiness"]["hasIdentifier"] is False


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
