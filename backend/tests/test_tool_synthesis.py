from app.services.tool_synthesis import summarize_tool_synthesis
from app.services.tool_synthesis import capability_tool_synthesis_contract
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
                "outputSchema": {"type": "object", "properties": {"claims": {"type": "array"}}},
                "inputEntities": ["Policy"],
                "outputEntity": "Claim",
                "permissions": {"scopes": ["claims:read"]},
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
    assert summary["hardenedToolCount"] == 1
    assert summary["needsHardeningCount"] == 2
    assert summary["hardenedTools"] == ["claims.search_claims"]
    assert summary["hardeningGaps"] == {
        "typed_input_schema": 2,
        "typed_output_schema": 2,
        "side_effects": 1,
        "approval_policy": 1,
        "scopes": 2,
        "entity_bindings": 2,
    }
    assert summary["hardeningPlaybook"][:3] == [
        {
            "gap": "entity_bindings",
            "count": 2,
            "area": "entities",
            "severity": "medium",
            "action": "Bind input and output business entities before promoting reusable skills.",
        },
        {
            "gap": "scopes",
            "count": 2,
            "area": "permissions",
            "severity": "medium",
            "action": "Attach connector scopes or permission claims for least-privilege execution.",
        },
        {
            "gap": "typed_input_schema",
            "count": 2,
            "area": "schema",
            "severity": "high",
            "action": "Define a typed input schema with required business identifiers.",
        },
    ]
    assert summary["productionGate"] == {
        "state": "needs_hardening",
        "ready": False,
        "checks": {
            "typedInputSchemas": False,
            "typedOutputSchemas": False,
            "sideEffectsDeclared": False,
            "riskClassified": True,
            "approvalPolicies": False,
            "scopesDeclared": False,
            "entityBindings": False,
        },
        "blockers": [
            {"name": "entity_bindings", "count": 2},
            {"name": "scopes", "count": 2},
            {"name": "typed_input_schema", "count": 2},
            {"name": "typed_output_schema", "count": 2},
            {"name": "approval_policy", "count": 1},
            {"name": "side_effects", "count": 1},
        ],
        "hardeningPlaybook": summary["hardeningPlaybook"],
    }
    assert summary["promotionReadiness"] == {
        "publishable": ["claims.search_claims"],
        "hardened": ["claims.search_claims"],
        "safeAtomicReadOnly": ["claims.search_claims"],
        "needsHardening": [
            {
                "toolName": "api.call",
                "gaps": ["typed_input_schema", "typed_output_schema", "side_effects", "approval_policy", "scopes", "entity_bindings"],
            },
            {
                "toolName": "smtp.send_email",
                "gaps": ["typed_input_schema", "typed_output_schema", "scopes", "entity_bindings"],
            },
        ],
        "blockedByApproval": ["api.call"],
        "canPromoteCount": 1,
        "blockedCount": 2,
    }
    assert summary["governedToolCount"] == 3
    assert summary["writeTools"] == ["api.call", "smtp.send_email"]
    assert summary["sendToolCount"] == 1
    assert summary["sendTools"] == ["smtp.send_email"]
    assert summary["approvalRequiredTools"] == ["smtp.send_email"]
    assert summary["riskCounts"] == {"medium": 1, "low": 1, "high": 1}
    assert summary["policyBoundaryCounts"] == {"write": 1, "read": 1, "send": 1}
    assert summary["runtimeRequirements"] == ["network"]
    assert summary["tools"][1]["schema"]["inputTyped"] is True


def test_capability_tool_synthesis_contract_preserves_route_payload_shape():
    contract = capability_tool_synthesis_contract(
        {
            "toolId": "tool-1",
            "name": "erp.update_claim",
            "inputSchema": {"type": "object", "properties": {"claimId": {"type": "string"}}},
            "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
            "sideEffects": "writes",
            "riskLevel": "high",
            "permissions": {"approval": "always", "oauthScopes": ["claims:write"]},
            "inputEntities": ["Claim"],
            "outputEntity": "Claim",
            "toolContract": {"format": "autoppia.tool_contract", "policyBoundary": "write"},
        }
    )

    assert contract == {
        "toolId": "tool-1",
        "action": "erp.update_claim",
        "atomic": True,
        "typedInput": True,
        "typedOutput": True,
        "sideEffects": "writes",
        "riskLevel": "high",
        "policyBoundary": "write",
        "riskClassification": {
            "level": "high",
            "requiresApproval": True,
            "approvalMode": "always",
        },
        "permissions": {
            "scopes": ["claims:write"],
            "readTools": [],
            "writeTools": [],
            "approval": "always",
        },
        "entityBindings": {
            "inputEntities": ["Claim"],
            "outputEntity": "Claim",
            "declared": True,
        },
        "readiness": {"status": "ready", "gaps": []},
    }
