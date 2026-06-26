from app.services.runtime_policy import (
    approval_boundary_matrix,
    browser_enabled,
    browser_runtime_policy,
    enterprise_runtime_policy,
    ordered_policy_boundaries,
    serialize_runtime_policy,
)
from app.services.runtime_policy_summary import observed_browser_domains, summarize_runtime_policy_map


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
    assert policy["runtimeClasses"] == ["api_runtime", "connector_runtime", "skill_runtime", "browser_runtime", "hybrid_runtime"]
    assert policy["browser"]["requiresSandbox"] is True
    assert policy["browser"]["allowedDomains"] == ["portal.example.com"]
    assert policy["api"]["toolCount"] == 1
    assert policy["approvals"]["requiredFor"] == ["write", "send"]
    assert policy["approvals"]["requiredBoundaries"] == ["send"]
    assert policy["approvals"]["requiredTools"] == ["smtp.send_email"]
    assert policy["approvals"]["boundaryMatrix"] == {
        "boundaries": [
            {"boundary": "read", "requiresApproval": False, "observed": False},
            {"boundary": "draft", "requiresApproval": False, "observed": True},
            {"boundary": "write", "requiresApproval": True, "observed": False},
            {"boundary": "send", "requiresApproval": True, "observed": True},
        ],
        "requiredFor": ["write", "send"],
        "missingObservedApproval": [],
        "hasHumanBoundary": True,
    }
    assert policy["budgets"]["maxCreditsPerRun"] == 7.5
    assert policy["policyBoundaries"] == ["draft", "send"]
    assert policy["resources"] == {"total": 2, "indexed": 2, "citable": 1}


def test_policy_boundaries_are_ordered_by_enterprise_side_effect_severity():
    assert ordered_policy_boundaries(["send", "Read", "write", "draft", "send"]) == ["read", "draft", "write", "send"]
    assert approval_boundary_matrix(["send"], observed_boundaries=["write", "send"]) == {
        "boundaries": [
            {"boundary": "read", "requiresApproval": False, "observed": False},
            {"boundary": "draft", "requiresApproval": False, "observed": False},
            {"boundary": "write", "requiresApproval": False, "observed": True},
            {"boundary": "send", "requiresApproval": True, "observed": True},
        ],
        "requiredFor": ["send"],
        "missingObservedApproval": ["write"],
        "hasHumanBoundary": True,
    }


def test_serialize_runtime_policy_exposes_approval_matrix_for_callable_capabilities():
    policy = serialize_runtime_policy(
        {
            "riskPolicy": "human_approval_for_writes",
            "policyBoundary": "write",
            "runtimeRequirements": ["api", "browser"],
            "runtimeSpec": {"allowedDomains": ["ERP.example.com"]},
        }
    )

    assert policy["runtimeClass"] == "hybrid"
    assert policy["runtimeTypes"] == ["api_runtime", "browser_runtime", "hybrid_runtime"]
    assert policy["approvalRequiredFor"] == ["write", "send"]
    assert policy["approvalPolicy"] == {
        "boundaries": [
            {"boundary": "read", "requiresApproval": False, "observed": False},
            {"boundary": "draft", "requiresApproval": False, "observed": False},
            {"boundary": "write", "requiresApproval": True, "observed": True},
            {"boundary": "send", "requiresApproval": True, "observed": False},
        ],
        "requiredFor": ["write", "send"],
        "missingObservedApproval": [],
        "hasHumanBoundary": True,
    }
    assert policy["browserPolicy"]["allowedDomains"] == ["ERP.example.com"]


def test_runtime_policy_summary_exposes_browser_domain_coverage_gaps():
    summary = summarize_runtime_policy_map(
        skills=[{"runtimeRequirements": ["browser"], "runtimeSpec": {"allowedDomains": ["portal.example.com"]}}],
        tools=[{"policyBoundary": "write", "riskPolicy": "human_approval_for_writes"}],
        runtime_kinds=["browser"],
        browser_allowlisted=True,
        browser_allowed_domains=["portal.example.com"],
        browser_observed_domains=["https://portal.example.com/cases", "https://unknown.example.net"],
        pending_approvals=0,
        approved_approvals=0,
    )

    assert summary["browserRestrictedByDomain"] is True
    assert summary["browserDomainGovernance"] == {
        "allowedDomains": ["portal.example.com"],
        "observedDomains": ["portal.example.com", "unknown.example.net"],
        "coveredDomains": ["portal.example.com"],
        "uncoveredDomains": ["unknown.example.net"],
        "coverageRatio": 0.5,
        "sessionsRequireAllowlist": True,
    }
    assert summary["approvalBoundaries"]["missingObservedApproval"] == []
    assert summary["approvalBoundaries"]["sideEffectsProtected"] is True
    assert summary["approvalBoundaries"]["hardening"] == {
        "ready": True,
        "missingBoundaries": [],
        "severity": "none",
        "nextActions": [],
    }
    assert summary["runtimeClassGate"] == {
        "state": "needs_hardening",
        "ready": False,
        "declared": ["api", "browser"],
        "observed": ["browser"],
        "checks": {
            "declaredPolicies": True,
            "observedRuntimeCovered": True,
            "browserAsException": False,
            "browserDomainGoverned": False,
            "sideEffectsApproved": True,
        },
        "blockers": [
            {"name": "browser_domain_governance", "count": 1},
            {"name": "browser_runtime_default_discipline", "count": 1},
        ],
    }
    assert summary["runtimeTaxonomy"] == {
        "defaultMode": "api_runtime",
        "browserDefault": "exception",
        "apiFirst": True,
        "browserRequiresAllowlist": True,
        "browserExceptionDiscipline": {
            "state": "needs_review",
            "ready": False,
            "apiFirstSessions": 0,
            "browserOnlySessions": 1,
            "hybridSessions": 0,
            "checks": {
                "browserNotDefault": False,
                "hybridCountsAsFallback": False,
            },
        },
        "modes": [
            {
                "runtimeType": "api_runtime",
                "role": "Structured API, connector, database, email and document operations.",
                "capabilities": 1,
                "observedSessions": 0,
            },
            {
                "runtimeType": "browser_runtime",
                "role": "Sandboxed UI automation for legacy portals or UI-only steps.",
                "capabilities": 1,
                "observedSessions": 1,
            },
            {
                "runtimeType": "hybrid_runtime",
                "role": "API-first execution with browser fallback for uncovered enterprise steps.",
                "capabilities": 0,
                "observedSessions": 0,
            },
        ],
    }
    assert any(gap["key"] == "browser_domain_coverage" for gap in summary["gaps"])


def test_runtime_policy_summary_flags_observed_side_effects_without_approval():
    summary = summarize_runtime_policy_map(
        skills=[],
        tools=[{"policyBoundary": "write", "riskPolicy": "autonomous", "permissions": {"approval": "never"}}],
        runtime_kinds=["api"],
        browser_allowlisted=False,
        pending_approvals=0,
        approved_approvals=0,
    )

    assert summary["approvalBoundaries"]["missingObservedApproval"] == ["write"]
    assert summary["approvalBoundaries"]["sideEffectsProtected"] is False
    assert summary["approvalBoundaries"]["hardening"] == {
        "ready": False,
        "missingBoundaries": ["write"],
        "severity": "high",
        "nextActions": [
            {
                "boundary": "write",
                "severity": "high",
                "action": "Require human approval for observed write side effects before publishing runtime capabilities.",
            }
        ],
    }
    assert summary["runtimeClassGate"]["checks"]["sideEffectsApproved"] is False
    assert {"name": "side_effect_approval_coverage", "count": 1} in summary["runtimeClassGate"]["blockers"]
    assert any(gap["key"] == "side_effect_approval_coverage" for gap in summary["gaps"])


def test_observed_browser_domains_extracts_urls_only_from_browser_sessions():
    domains = observed_browser_domains(
        [
            {
                "runtimeKind": "hybrid",
                "runtimeState": {"currentUrl": "https://Portal.Example.com/cases"},
                "actionHistory": [{"action": "browser.navigate", "url": "https://claims.example.com/claim/1"}],
            },
            {
                "runtimeKind": "api",
                "runtimeState": {"currentUrl": "https://ignored.example.com"},
                "actionHistory": [{"action": "api.read"}],
            },
        ]
    )

    assert domains == ["claims.example.com", "portal.example.com"]
