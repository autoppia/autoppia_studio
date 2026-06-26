from app.services.tool_synthesis import summarize_tool_synthesis
from app.services.tool_synthesis import tool_synthesis_contract


def test_tool_synthesis_contract_exposes_schema_risk_permissions_and_entities():
    contract = tool_synthesis_contract(
        {
            "name": "claims.update_claim",
            "sideEffects": "writes",
            "riskLevel": "medium",
            "inputSchema": {"type": "object", "properties": {"claimId": {"type": "string"}}, "required": ["claimId"]},
            "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
            "inputEntities": ["Claim"],
            "outputEntity": "Claim",
            "approvalPolicy": {"required": True, "mode": "always", "requiredFor": ["write"]},
            "permissions": {"connectorId": "erp-1", "requiresApproval": True, "approval": "always", "scopes": ["write", "connector:erp-1"]},
            "toolContract": {"format": "autoppia.tool_contract", "policyBoundary": "write"},
        }
    )

    assert contract["toolName"] == "claims.update_claim"
    assert contract["typed"] is True
    assert contract["governed"] is True
    assert contract["schema"] == {"inputTyped": True, "outputTyped": True, "required": ["claimId"]}
    assert contract["sideEffects"] == "writes"
    assert contract["policyBoundary"] == "write"
    assert contract["riskLevel"] == "medium"
    assert contract["approval"] == {"required": True, "mode": "always", "requiredFor": ["write"]}
    assert contract["permissions"]["scopes"] == ["write", "connector:erp-1"]
    assert contract["entities"] == {"input": ["Claim"], "output": "Claim", "linked": True}


def test_summarize_tool_synthesis_keeps_atomic_tool_inventory_for_capability_factory():
    summary = summarize_tool_synthesis(
        [
            {"name": "api.call", "toolContract": {"format": "autoppia.tool_contract", "riskLevel": "medium", "policyBoundary": "write"}},
            {
                "name": "claims.search_claims",
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputSchema": {"type": "object", "properties": {"policyId": {"type": "string"}}},
                "toolContract": {"format": "autoppia.tool_contract", "policyBoundary": "read"},
            },
            {
                "name": "smtp.send_email",
                "sideEffects": "send",
                "riskLevel": "high",
                "approvalPolicy": {"required": True, "mode": "always", "requiredFor": ["send"]},
                "toolContract": {"format": "autoppia.tool_contract", "policyBoundary": "send"},
            },
        ],
        runtime_requirements=["network"],
    )

    assert summary["toolCount"] == 3
    assert summary["typedTools"] == ["claims.search_claims"]
    assert summary["governedToolCount"] == 3
    assert summary["writeTools"] == ["api.call", "smtp.send_email"]
    assert summary["approvalRequiredTools"] == ["smtp.send_email"]
    assert summary["riskCounts"] == {"medium": 1, "low": 1, "high": 1}
    assert summary["policyBoundaryCounts"] == {"write": 1, "read": 1, "send": 1}
    assert summary["runtimeRequirements"] == ["network"]
    assert summary["tools"][1]["schema"]["inputTyped"] is True
