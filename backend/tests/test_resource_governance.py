from app.services.resource_governance import resource_payload, summarize_resource_governance


def _resource():
    return {
        "documentId": "doc-claims",
        "resourceId": "resource-claims",
        "resourceKind": "document",
        "filename": "claims-handbook.md",
        "status": "indexed",
        "connectorId": "knowledge-1",
        "resourceContract": {
            "resourceKind": "document",
            "indexing": {
                "indexed": True,
                "vectorDatabaseId": "vector-claims",
                "vectorDatabaseName": "Claims Store",
                "vectorCollectionName": "claims",
            },
            "governance": {
                "connectorId": "knowledge-1",
                "citability": {"citable": True, "citationLabel": "Claims handbook"},
                "acl": {"visibility": "company", "allowedRoles": ["claims_ops"]},
            },
            "readTools": ["knowledge.claims.search"],
        },
    }


def test_resource_payload_exposes_governed_runtime_resource_contract():
    payload = resource_payload(_resource())

    assert payload["resourceId"] == "resource-claims"
    assert payload["connectorId"] == "knowledge-1"
    assert payload["vectorDatabaseId"] == "vector-claims"
    assert payload["vectorDatabaseName"] == "Claims Store"
    assert payload["vectorCollectionName"] == "claims"
    assert payload["indexed"] is True
    assert payload["citable"] is True
    assert payload["citationLabel"] == "Claims handbook"
    assert payload["readTools"] == ["knowledge.claims.search"]


def test_summarize_resource_governance_counts_runtime_ready_resources():
    summary = summarize_resource_governance([_resource()])

    assert summary["total"] == 1
    assert summary["indexed"] == 1
    assert summary["citable"] == 1
    assert summary["withResourceContract"] == 1
    assert summary["withVectorStore"] == 1
    assert summary["acl"]["withAcl"] == 1
    assert summary["runtimeGate"]["ready"] == 1
    assert summary["ready"] is True
