from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def connector_domains(connector: dict[str, Any]) -> list[str]:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    domains: set[str] = set()
    for key in ("baseUrl", "startUrl", "loginUrl", "docsUrl", "openApiUrl", "sourceUrl"):
        raw = str(config.get(key) or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname:
            domains.add(parsed.hostname.lower())
    return sorted(domains)


def allowed_origin_hosts(company: dict[str, Any]) -> list[str]:
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    hosts: set[str] = set()
    for origin in settings.get("allowedOrigins") or []:
        raw = str(origin or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return sorted(hosts)


def host_jwt_configured(company: dict[str, Any]) -> bool:
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    return bool(settings.get("hostJwtConfigured") or settings.get("hostJwtSecret"))


def build_company_governance(
    *,
    company: dict[str, Any],
    counts: dict[str, int],
    connector_domains: list[str],
    policy_counts: list[dict[str, Any]],
    acl_visibility_counts: list[dict[str, Any]],
    knowledge_doc_count: int,
    docs_with_acl: int,
    company_visible_docs: int,
    restricted_docs: int,
) -> dict[str, Any]:
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    return {
        "credentials": counts["credentials"],
        "allowedOrigins": list(settings.get("allowedOrigins") or []),
        "allowedOriginHosts": allowed_origin_hosts(company),
        "hostJwtConfigured": host_jwt_configured(company),
        "discoveredDomains": connector_domains,
        "skillPolicies": policy_counts,
        "resourceAcl": {
            "documents": knowledge_doc_count,
            "withAcl": docs_with_acl,
            "companyVisible": company_visible_docs,
            "restricted": restricted_docs,
            "visibility": acl_visibility_counts,
        },
    }


def build_company_integration_contract(
    *,
    company: dict[str, Any],
    owner_email: str,
    counts: dict[str, int],
    surface_counts: list[dict[str, Any]],
    connector_domains: list[str],
    policy_counts: list[dict[str, Any]],
    acl_visibility_counts: list[dict[str, Any]],
    knowledge_doc_count: int,
    docs_with_acl: int,
) -> dict[str, Any]:
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    allowed_origins = list(settings.get("allowedOrigins") or [])
    domain_allowlist = sorted(set(connector_domains + allowed_origin_hosts(company)))
    resource_acl_complete = not knowledge_doc_count or docs_with_acl == knowledge_doc_count
    return {
        "systems": counts["connectors"],
        "secrets": counts["credentials"],
        "environments": surface_counts,
        "domainAllowlist": domain_allowlist,
        "approvalBoundary": {
            "pending": counts["pendingApprovals"],
            "approved": counts["approvedApprovals"],
            "skillPolicies": policy_counts,
        },
        "acl": {
            "ownerEmail": owner_email,
            "hostJwtConfigured": host_jwt_configured(company),
            "allowedOrigins": allowed_origins,
            "resourceVisibility": acl_visibility_counts,
            "resourcesWithAcl": docs_with_acl,
            "resourceAclComplete": resource_acl_complete,
        },
        "compliance": {
            "browserRestrictedByDomain": bool(domain_allowlist),
            "humanApprovalConfigured": bool(policy_counts or counts["pendingApprovals"] or counts["approvedApprovals"]),
            "resourceAclComplete": resource_acl_complete,
            "auditEvidence": {
                "sessions": counts["sessions"],
                "artifacts": counts["artifacts"],
                "evalRuns": counts["evalRuns"],
            },
        },
    }
