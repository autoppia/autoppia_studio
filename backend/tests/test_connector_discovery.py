from app.services.connector_discovery import connector_capability_discovery


def test_connector_capability_discovery_blocks_custom_api_until_docs_and_auth():
    discovery = connector_capability_discovery(
        {
            "connectorId": "conn-1",
            "name": "Claims ERP",
            "type": "api",
            "provider": "custom",
            "generationStatus": "needs_docs",
            "config": {"baseUrl": "https://erp.example.com"},
            "credentialFields": {},
        },
        {
            "authFields": ["apiKey"],
            "runtimeRequirements": ["api_docs_or_openapi", "network"],
            "tools": [
                {
                    "name": "api.call",
                    "sideEffects": "writes",
                    "riskLevel": "medium",
                    "approvalPolicy": {"required": True},
                    "toolContract": {"format": "autoppia.tool_contract"},
                }
            ],
        },
    )

    assert discovery["docs"]["available"] is False
    assert discovery["docs"]["surfaceUrls"] == ["https://erp.example.com"]
    assert discovery["auth"]["configuredFields"] == 0
    assert discovery["toolSynthesis"]["approvalRequiredTools"] == ["api.call"]
    assert discovery["ingestionPipeline"]["state"] == "blocked"
    assert discovery["ingestionPipeline"]["nextStage"]["key"] == "connector_docs"
    assert {gap["key"] for gap in discovery["gaps"]} == {"docs", "auth"}


def test_connector_capability_discovery_maps_entities_from_tool_contracts():
    discovery = connector_capability_discovery(
        {
            "connectorId": "conn-1",
            "name": "Claims ERP",
            "type": "api",
            "provider": "custom",
            "generationStatus": "generated",
            "config": {"openApiUrl": "https://erp.example.com/openapi.json"},
            "credentialFields": {"apiKey": {"configured": True}},
        },
        {
            "authFields": ["apiKey"],
            "runtimeRequirements": ["network"],
            "tools": [
                {
                    "name": "claims.search_claims",
                    "sideEffects": "reads",
                    "inputEntities": ["Policy"],
                    "outputEntity": "Claim",
                    "toolContract": {"format": "autoppia.tool_contract"},
                },
                {
                    "name": "claims.update_claim",
                    "sideEffects": "writes",
                    "inputEntities": ["Claim"],
                    "outputEntity": "Claim",
                    "approvalPolicy": {"required": True},
                    "toolContract": {"format": "autoppia.tool_contract"},
                },
            ],
        },
    )

    assert discovery["auth"]["configuredFields"] == 1
    assert discovery["entityMapping"]["status"] == "mapped"
    assert discovery["entityMapping"]["businessObjects"] == ["Policy", "Claim"]
    assert discovery["entityMapping"]["permissions"]["readTools"] == ["claims.search_claims"]
    assert discovery["entityMapping"]["permissions"]["writeTools"] == ["claims.update_claim"]
    assert discovery["toolSynthesis"]["typedTools"] == ["claims.search_claims", "claims.update_claim"]
    assert discovery["ingestionPipeline"]["state"] == "needs_benchmark"
