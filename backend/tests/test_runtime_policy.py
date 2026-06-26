from app.services.runtime_policy import browser_enabled, browser_runtime_policy, enterprise_runtime_policy


def test_browser_runtime_policy_adds_website_host_to_allowlist_and_sandbox_signal():
    policy = browser_runtime_policy(
        {
            "websiteUrl": "https://portal.example.com/start",
            "runtimeSpec": {"browserEnabled": True, "allowedDomains": ["erp.example.com"]},
        }
    )

    assert policy["enabled"] is True
    assert policy["allowedDomains"] == ["erp.example.com", "portal.example.com"]
    assert policy["restrictedByDomain"] is True
    assert policy["defaultUse"] == "exception"
    assert policy["riskLevel"] == "medium"
    assert browser_enabled({"runtimeSpec": {"browserEnabled": False}, "runtimeCapabilities": {"browser": True}}) is False


def test_enterprise_runtime_policy_models_hybrid_runtime_approvals_budgets_and_resources():
    policy = enterprise_runtime_policy(
        {
            "websiteUrl": "https://portal.example.com",
            "runtimeCapabilities": {"apiCalls": True, "browser": True, "humanApprovalForWrites": True},
            "runtimeSpec": {"tools": {"connectors": True}, "maxCreditsPerRun": 7.5},
        },
        tools=[
            {
                "name": "smtp.send_email",
                "policyBoundary": "send",
                "approvalPolicy": {"required": True},
            }
        ],
        skills=[{"name": "skill.draft_reply", "policyBoundary": "draft"}],
        resources=[{"indexed": True, "citable": True}, {"indexed": True, "citable": False}],
    )

    assert policy["runtimeClass"] == "hybrid"
    assert policy["runtimeType"] == "hybrid_runtime"
    assert policy["runtimeTypes"] == ["api_runtime", "browser_runtime", "hybrid_runtime"]
    assert policy["browser"]["requiresSandbox"] is True
    assert policy["browser"]["allowedDomains"] == ["portal.example.com"]
    assert policy["api"]["toolCount"] == 1
    assert policy["approvals"]["requiredFor"] == ["write", "send"]
    assert policy["approvals"]["requiredBoundaries"] == ["send"]
    assert policy["approvals"]["requiredTools"] == ["smtp.send_email"]
    assert policy["budgets"]["maxCreditsPerRun"] == 7.5
    assert policy["policyBoundaries"] == ["draft", "send"]
    assert policy["resources"] == {"total": 2, "indexed": 2, "citable": 1}
