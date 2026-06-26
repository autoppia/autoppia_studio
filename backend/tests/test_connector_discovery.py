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
    assert discovery["toolSynthesis"]["tools"][0]["toolName"] == "api.call"
    assert discovery["toolSynthesis"]["tools"][0]["governed"] is True
    assert discovery["toolSynthesis"]["tools"][0]["policyBoundary"] == "write"
    assert discovery["ingestionPipeline"]["state"] == "blocked"
    assert discovery["ingestionPipeline"]["blockedStages"] == [
        "connector_docs",
        "auth_state",
        "entity_mapping",
        "tool_synthesis",
    ]
    assert discovery["ingestionPipeline"]["nextStage"]["key"] == "connector_docs"
    assert discovery["ingestionPipeline"]["playbook"][:2] == [
        {
            "stage": "connector_docs",
            "status": "pending",
            "target": "config.openApiUrl",
            "severity": "high",
            "action": "Attach OpenAPI/docs for API connectors or a start URL for web connectors.",
        },
        {
            "stage": "auth_state",
            "status": "pending",
            "target": "credentials",
            "severity": "high",
            "action": "Configure required credentials or OAuth fields before runtime discovery.",
        },
    ]
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
    assert discovery["toolSynthesis"]["tools"][0]["entities"] == {"input": ["Policy"], "output": "Claim", "linked": True}
    assert discovery["toolSynthesis"]["tools"][1]["approval"]["required"] is True
    assert discovery["ingestionPipeline"]["state"] == "needs_benchmark"
    assert discovery["ingestionPipeline"]["blockedStages"] == []
    assert discovery["ingestionPipeline"]["playbook"] == [
        {
            "stage": "candidate_tasks",
            "status": "recommended",
            "target": "evals",
            "severity": "medium",
            "action": "Seed benchmark tasks so harvested trajectories can be judged and promoted.",
        }
    ]
