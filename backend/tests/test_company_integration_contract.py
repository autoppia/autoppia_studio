from app.services.company_integration_contract import (
    allowed_origin_hosts,
    build_company_governance,
    build_company_integration_contract,
    connector_domains,
)


def test_connector_domains_and_allowed_origins_normalize_hosts():
    connector = {
        "config": {
            "baseUrl": "https://ERP.Example.com/app",
            "openApiUrl": "https://api.example.com/openapi.json",
            "docsUrl": "",
            "loginUrl": "not-a-url",
        }
    }
    company = {"embedSettings": {"allowedOrigins": ["https://studio.example.com", "http://ERP.example.com"]}}

    assert connector_domains(connector) == ["api.example.com", "erp.example.com"]
    assert allowed_origin_hosts(company) == ["erp.example.com", "studio.example.com"]


def test_company_integration_contract_models_setup_governance_and_compliance():
    company = {
        "embedSettings": {
            "allowedOrigins": ["https://studio.example.com"],
            "hostJwtSecret": "configured",
        }
    }
    counts = {
        "connectors": 2,
        "credentials": 1,
        "pendingApprovals": 1,
        "approvedApprovals": 2,
        "sessions": 3,
        "artifacts": 4,
        "evalRuns": 5,
    }
    policies = [{"name": "human_approval_for_writes", "count": 1}]
    visibility = [{"name": "company", "count": 2}]

    integration = build_company_integration_contract(
        company=company,
        owner_email="owner@example.com",
        counts=counts,
        surface_counts=[{"name": "api", "count": 1}, {"name": "browser", "count": 1}],
        connector_domains=["erp.example.com"],
        policy_counts=policies,
        acl_visibility_counts=visibility,
        knowledge_doc_count=2,
        docs_with_acl=2,
    )

    assert integration["systems"] == 2
    assert integration["secrets"] == 1
    assert integration["domainAllowlist"] == ["erp.example.com", "studio.example.com"]
    assert integration["approvalBoundary"]["pending"] == 1
    assert integration["acl"]["ownerEmail"] == "owner@example.com"
    assert integration["acl"]["hostJwtConfigured"] is True
    assert integration["acl"]["resourceAclComplete"] is True
    assert integration["compliance"] == {
        "browserRestrictedByDomain": True,
        "humanApprovalConfigured": True,
        "resourceAclComplete": True,
        "auditEvidence": {"sessions": 3, "artifacts": 4, "evalRuns": 5},
    }


def test_company_governance_exposes_resource_acl_and_domain_state():
    governance = build_company_governance(
        company={"embedSettings": {"allowedOrigins": ["https://studio.example.com"]}},
        counts={"credentials": 2},
        connector_domains=["erp.example.com"],
        policy_counts=[{"name": "autonomous", "count": 1}],
        acl_visibility_counts=[{"name": "restricted", "count": 1}],
        knowledge_doc_count=1,
        docs_with_acl=1,
        company_visible_docs=0,
        restricted_docs=1,
    )

    assert governance["credentials"] == 2
    assert governance["allowedOriginHosts"] == ["studio.example.com"]
    assert governance["discoveredDomains"] == ["erp.example.com"]
    assert governance["resourceAcl"] == {
        "documents": 1,
        "withAcl": 1,
        "companyVisible": 0,
        "restricted": 1,
        "visibility": [{"name": "restricted", "count": 1}],
    }
