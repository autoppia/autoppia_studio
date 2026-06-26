from app.services.agent_config_contract import build_runtime_spec
from app.services.agent_config_contract import control_plane_separation_gate
from app.services.agent_config_contract import dedupe_runtime_values
from app.services.agent_config_contract import runtime_allowed_domains
from app.services.agent_config_contract import runtime_classes


def test_build_runtime_spec_models_api_browser_hybrid_classes_and_policies():
    spec = build_runtime_spec(
        browser_enabled=True,
        browser_mode="headless",
        max_credits_per_run=7.5,
        existing_tools={"knowledge": True},
        website_url="https://ERP.example.com/app",
        existing_spec={
            "allowedDomains": ["portal.example.com", "ERP.example.com"],
            "approvalRequiredFor": ["write", "send", "write"],
        },
    )

    assert spec["browserEnabled"] is True
    assert spec["browserMode"] == "headless"
    assert spec["browserDefaultUse"] == "exception"
    assert spec["browserRestrictedByDomain"] is True
    assert spec["allowedDomains"] == ["portal.example.com", "erp.example.com"]
    assert spec["approvalRequiredFor"] == ["write", "send"]
    assert spec["runtimeClasses"] == [
        "api_runtime",
        "connector_runtime",
        "skill_runtime",
        "browser_runtime",
        "hybrid_runtime",
    ]
    assert spec["tools"] == {"browser": True, "connectors": True, "skills": True, "knowledge": True}
    assert spec["maxCreditsPerRun"] == 7.5


def test_build_runtime_spec_disables_browser_without_losing_connector_skill_runtime():
    spec = build_runtime_spec(
        browser_enabled=False,
        browser_mode="invalid",
        max_credits_per_run=-3,
        existing_tools={"connectors": False, "skills": True},
        website_url="https://example.com",
    )

    assert spec["browserEnabled"] is False
    assert spec["browserMode"] == "visible"
    assert spec["maxCreditsPerRun"] == 0.0
    assert spec["tools"]["browser"] is False
    assert spec["tools"]["connectors"] is False
    assert spec["tools"]["skills"] is True
    assert spec["runtimeClasses"] == ["api_runtime", "skill_runtime"]


def test_runtime_helpers_dedupe_domains_and_classes():
    assert dedupe_runtime_values(["Write", "write", "", "Send"]) == ["write", "send"]
    assert runtime_allowed_domains(
        "https://app.example.com/path",
        {"browserAllowedDomains": ["api.example.com", "APP.example.com"]},
    ) == ["api.example.com", "app.example.com"]
    assert runtime_classes(browser_enabled=False, tools={"connectors": True, "skills": False}) == [
        "api_runtime",
        "connector_runtime",
    ]


def test_control_plane_separation_gate_blocks_execution_state_leaks():
    gate = control_plane_separation_gate(
        {
            "agentId": "agent-1",
            "runtimeSpec": {"tools": {"connectors": True, "skills": True}},
            "capabilityDiscovery": {"mode": "task_scoped"},
            "sessionId": "runtime-session-1",
            "artifacts": [{"artifactId": "draft-1"}],
        },
        tools=[{"name": "imap.search_emails"}],
    )

    assert gate["state"] == "blocked"
    assert gate["ready"] is False
    assert gate["checks"]["executionStateExternalized"] is False
    assert gate["leakedExecutionKeys"] == ["artifacts", "sessionId"]
    assert "executionStateExternalized" in gate["blockers"]
    assert gate["hardeningPlaybook"][0]["area"] == "runtime_state"


def test_control_plane_separation_gate_accepts_declarative_capability_config():
    gate = control_plane_separation_gate(
        {
            "agentId": "agent-1",
            "runtimeSpec": {"tools": {"connectors": True, "skills": True}},
            "capabilityDiscovery": {"mode": "task_scoped"},
        },
        tools=[{"name": "imap.search_emails"}],
        skills=[{"name": "skill.claim_status_reply"}],
        resources=[{"resourceId": "claims-policy"}],
    )

    assert gate["state"] == "ready"
    assert gate["ready"] is True
    assert gate["checks"] == {
        "agentConfigDeclared": True,
        "runtimeSpecDeclared": True,
        "capabilityDiscoveryDeclared": True,
        "capabilityInventoryDeclared": True,
        "executionStateExternalized": True,
    }
    assert gate["hardeningPlaybook"] == []
