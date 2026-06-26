from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


SETUP_GATE_ACTIONS = {
    "systems": {
        "area": "systems",
        "severity": "high",
        "action": "Add the ERP, CRM, email, document and portal systems that define the operating surface.",
    },
    "secrets": {
        "area": "credentials",
        "severity": "high",
        "action": "Attach credentials or OAuth profiles for systems that need authenticated runtime access.",
    },
    "domain_allowlist": {
        "area": "security",
        "severity": "high",
        "action": "Declare allowed Studio/embed/browser domains before enabling browser or embedded runtime surfaces.",
    },
    "human_approval": {
        "area": "approvals",
        "severity": "high",
        "action": "Configure human approval policies for write and send boundaries.",
    },
    "resource_acl": {
        "area": "resources",
        "severity": "high",
        "action": "Declare resource ACL visibility, roles or users for all knowledge resources.",
    },
    "host_jwt": {
        "area": "embed",
        "severity": "high",
        "action": "Configure host JWT settings for authenticated embedded Studio access.",
    },
    "audit_evidence": {
        "area": "observability",
        "severity": "medium",
        "action": "Run a session, eval or artifact-producing workflow to create audit evidence.",
    },
}


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


def _policy_counts_include_human_approval(policy_counts: list[dict[str, Any]]) -> bool:
    for policy in policy_counts:
        name = str(policy.get("name") or "").strip().lower()
        if "approval" in name or "human" in name or name in {"always", "required", "write", "send"}:
            return True
    return False


def _setup_gate(
    *,
    systems: int,
    secrets: int,
    domain_allowlist: list[str],
    human_approval_configured: bool,
    resource_acl_complete: bool,
    host_jwt_ready: bool,
    audit_evidence: dict[str, int],
) -> dict[str, Any]:
    checks = {
        "systems": systems > 0,
        "secrets": secrets > 0,
        "domain_allowlist": bool(domain_allowlist),
        "human_approval": human_approval_configured,
        "resource_acl": resource_acl_complete,
        "host_jwt": host_jwt_ready,
        "audit_evidence": any(int(value or 0) > 0 for value in audit_evidence.values()),
    }
    blockers = [key for key, ready in checks.items() if not ready]
    playbook = [
        {
            "gap": blocker,
            "area": SETUP_GATE_ACTIONS[blocker]["area"],
            "severity": SETUP_GATE_ACTIONS[blocker]["severity"],
            "action": SETUP_GATE_ACTIONS[blocker]["action"],
        }
        for blocker in blockers
    ]
    return {
        "state": "ready" if not blockers else "partial" if any(checks.values()) else "missing",
        "ready": not blockers,
        "checks": checks,
        "blockers": blockers,
        "nextActions": [item["action"] for item in playbook],
        "hardeningPlaybook": playbook,
    }


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
    discovered_domains = connector_domains
    allowed_hosts = allowed_origin_hosts(company)
    host_jwt_ready = host_jwt_configured(company)
    resource_acl_complete = not knowledge_doc_count or docs_with_acl == knowledge_doc_count
    human_approval_configured = _policy_counts_include_human_approval(policy_counts)
    audit_evidence = {"sessions": 0, "artifacts": 0, "evalRuns": 0}
    return {
        "credentials": counts["credentials"],
        "allowedOrigins": list(settings.get("allowedOrigins") or []),
        "allowedOriginHosts": allowed_hosts,
        "hostJwtConfigured": host_jwt_ready,
        "discoveredDomains": discovered_domains,
        "skillPolicies": policy_counts,
        "resourceAcl": {
            "documents": knowledge_doc_count,
            "withAcl": docs_with_acl,
            "companyVisible": company_visible_docs,
            "restricted": restricted_docs,
            "visibility": acl_visibility_counts,
        },
        "setupGate": _setup_gate(
            systems=len(discovered_domains),
            secrets=counts["credentials"],
            domain_allowlist=sorted(set(discovered_domains + allowed_hosts)),
            human_approval_configured=human_approval_configured,
            resource_acl_complete=resource_acl_complete,
            host_jwt_ready=host_jwt_ready,
            audit_evidence=audit_evidence,
        ),
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
    human_approval_configured = bool(_policy_counts_include_human_approval(policy_counts) or counts["pendingApprovals"] or counts["approvedApprovals"])
    audit_evidence = {
        "sessions": counts["sessions"],
        "artifacts": counts["artifacts"],
        "evalRuns": counts["evalRuns"],
    }
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
            "humanApprovalConfigured": human_approval_configured,
            "resourceAclComplete": resource_acl_complete,
            "auditEvidence": audit_evidence,
        },
        "setupGate": _setup_gate(
            systems=counts["connectors"],
            secrets=counts["credentials"],
            domain_allowlist=domain_allowlist,
            human_approval_configured=human_approval_configured,
            resource_acl_complete=resource_acl_complete,
            host_jwt_ready=host_jwt_configured(company),
            audit_evidence=audit_evidence,
        ),
    }
