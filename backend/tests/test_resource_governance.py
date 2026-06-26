from app.services.resource_governance import build_resource_contract, build_resource_gate, resource_payload, resource_tool_segment, summarize_resource_governance


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
                "citability": {"citable": True, "citationLabel": "Claims handbook", "sourceUrl": "https://docs.example.com/claims"},
                "acl": {"visibility": "company", "allowedRoles": ["claims_ops"]},
            },
            "readTools": ["knowledge.claims.search"],
        },
    }


def test_resource_payload_exposes_governed_runtime_resource_contract():
    payload = resource_payload(_resource())

    assert payload["resourceId"] == "resource-claims"
    assert payload["name"] == "claims-handbook.md"
    assert payload["connectorId"] == "knowledge-1"
    assert payload["vectorDatabaseId"] == "vector-claims"
    assert payload["vectorDatabaseName"] == "Claims Store"
    assert payload["vectorCollectionName"] == "claims"
    assert payload["indexed"] is True
    assert payload["citable"] is True
    assert payload["citationLabel"] == "Claims handbook"
    assert payload["sourceUrl"] == "https://docs.example.com/claims"
    assert payload["freshnessStatus"] == "current"
    assert payload["readTools"] == ["knowledge.claims.search"]


def test_build_resource_contract_declares_versioned_acl_citable_resource_gate():
    contract = build_resource_contract(
        {
            "documentId": "doc-1",
            "resourceId": "doc-1",
            "companyId": "co-1",
            "filename": "handbook.md",
            "status": "indexed",
            "source": "upload",
            "connectorId": "knowledge-1",
            "vectorDatabaseId": "vec-1",
            "vectorDatabaseName": "Company Knowledge",
            "vectorCollectionName": "company-co-1",
            "acl": {"visibility": "company", "allowedRoles": ["ops"]},
            "version": 2,
            "createdAt": "t-1",
            "updatedAt": "t-2",
        }
    )

    assert contract["surface"] == "knowledge_resource"
    assert contract["readOnly"] is True
    assert contract["indexing"]["indexed"] is True
    assert contract["governance"]["acl"]["allowedRoles"] == ["ops"]
    assert contract["governance"]["versioning"]["version"] == 2
    assert contract["governance"]["freshness"]["status"] == "current"
    assert contract["governance"]["citability"]["citable"] is True
    assert contract["readTools"] == [
        "knowledge.company_knowledge.search",
        "knowledge.company_knowledge.list_documents",
        "knowledge.company_knowledge.stats",
        "knowledge.company_knowledge.read_document",
    ]
    assert contract["resourceGate"]["readyForRuntime"] is True
    assert resource_tool_segment("Company Knowledge!") == "company_knowledge"


def test_build_resource_gate_blocks_unindexed_or_ungoverned_resources():
    gate = build_resource_gate(
        indexed=False,
        vector_database_id="vec-1",
        read_tools=["knowledge.company.search"],
        acl={},
        stale=False,
        citation_label="",
    )

    assert gate["state"] == "blocked"
    assert gate["readyForRuntime"] is False
    assert gate["blockers"] == ["indexed", "acl", "freshness", "citability"]
    assert "Declare ACL visibility, roles or users for the resource." in gate["nextActions"]


def test_summarize_resource_governance_counts_runtime_ready_resources():
    summary = summarize_resource_governance([_resource()])

    assert summary["total"] == 1
    assert summary["indexed"] == 1
    assert summary["citable"] == 1
    assert summary["withResourceContract"] == 1
    assert summary["withVectorStore"] == 1
    assert summary["acl"]["withAcl"] == 1
    assert summary["citations"] == {
        "labels": ["Claims handbook"],
        "sourceUrls": ["https://docs.example.com/claims"],
    }
    assert summary["runtimeGate"]["ready"] == 1
    assert summary["ready"] is True
