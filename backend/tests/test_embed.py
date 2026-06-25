import pytest
from fastapi import HTTPException

from app.routes import embed
from app.routes import companies
from app.request_scope import RequestScope


class _Companies:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if key == "embedSettings.publicToken":
                    current = (doc.get("embedSettings") or {}).get("publicToken")
                else:
                    current = doc.get(key)
                if current != value:
                    matched = False
                    break
            if matched:
                return dict(doc)
        return None


class _CompanySettingsCollection:
    def __init__(self, doc):
        self.doc = dict(doc)

    async def find_one(self, query, projection=None):
        for key, value in query.items():
            if self.doc.get(key) != value:
                return None
        return dict(self.doc)

    async def update_one(self, query, update):
        for key, value in query.items():
            if self.doc.get(key) != value:
                return
        self.doc.update(update.get("$set", {}))


class _Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, length=500):
        return [dict(doc) for doc in self.docs[:length]]


def _nested(doc, key):
    current = doc
    for part in key.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                return None
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, item) for item in value):
                return False
            continue
        current = _nested(doc, key)
        if isinstance(value, dict):
            if "$exists" in value:
                exists = current is not None
                if exists != bool(value["$exists"]):
                    return False
            if "$nin" in value and current in value["$nin"]:
                return False
            continue
        if current != value:
            return False
    return True


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if _matches(doc, query))

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])


def _host_jwt(payload, secret="host-secret"):
    header = embed._b64(b'{"alg":"HS256","typ":"JWT"}')
    body = embed._b64(embed.json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = embed._b64(embed.hmac.new(secret.encode("utf-8"), f"{header}.{body}".encode("ascii"), embed.hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


@pytest.mark.asyncio
async def test_create_embed_session_validates_origin_and_signs_token(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "allowedOrigins": ["https://erp.example.com"],
                    },
                }
            ]
        ),
    )

    result = await embed.create_embed_session(
        embed.EmbedSessionRequest(token="public-token", userRef="employee-1"),
        origin="https://erp.example.com",
    )
    payload = embed._verify(result["sessionToken"], "public-token")

    assert result["companyId"] == "company-1"
    assert payload["companyId"] == "company-1"
    assert payload["email"] == "owner@example.com"
    assert payload["userRef"] == "employee-1"


@pytest.mark.asyncio
async def test_create_embed_session_rejects_unallowed_origin(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "allowedOrigins": ["https://erp.example.com"],
                    },
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await embed.create_embed_session(
            embed.EmbedSessionRequest(token="public-token", userRef="employee-1"),
            origin="https://evil.example.com",
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_embed_session_requires_and_uses_host_jwt(monkeypatch):
    monkeypatch.setattr(
        embed,
        "companies_collection",
        _Companies(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "embedSettings": {
                        "enabled": True,
                        "publicToken": "public-token",
                        "hostJwtSecret": "host-secret",
                    },
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await embed.create_embed_session(embed.EmbedSessionRequest(token="public-token", userRef="untrusted"))
    assert exc.value.status_code == 401

    result = await embed.create_embed_session(
        embed.EmbedSessionRequest(token="public-token", userRef="untrusted", hostJwt=_host_jwt({"sub": "employee-42", "role": "broker"}))
    )
    payload = embed._verify(result["sessionToken"], "public-token")

    assert payload["userRef"] == "employee-42"
    assert payload["hostClaims"] == {"sub": "employee-42", "role": "broker"}


def test_company_serializer_redacts_embed_host_jwt_secret():
    serialized = companies._serialize(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {
                "enabled": True,
                "publicToken": "public-token",
                "hostJwtSecret": "host-secret",
                "allowedOrigins": ["https://erp.example.com"],
            },
        }
    )

    assert serialized["embedSettings"]["hostJwtConfigured"] is True
    assert "hostJwtSecret" not in serialized["embedSettings"]


@pytest.mark.asyncio
async def test_widget_js_uses_script_origin_for_frame():
    response = await embed.embed_widget_js()
    body = response.body.decode("utf-8")

    assert "scriptUrl.origin" in body
    assert "new URL('/embed/v1/frame',scriptUrl.origin)" in body
    assert "data-user-ref" in body
    assert "data-host-jwt" in body


@pytest.mark.asyncio
async def test_embed_frame_posts_user_ref_and_host_jwt():
    response = await embed.embed_frame("public-token", userRef="employee-1", hostJwt="jwt-1")
    body = response.body.decode("utf-8")

    assert 'var embedUserRef="employee-1";' in body
    assert 'var embedHostJwt="jwt-1";' in body
    assert "hostJwt:embedHostJwt" in body


def test_company_serializer_reports_cleared_embed_host_jwt_secret():
    serialized = companies._serialize(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {
                "enabled": True,
                "publicToken": "public-token",
                "hostJwtSecret": "",
            },
        }
    )

    assert serialized["embedSettings"]["hostJwtConfigured"] is False


@pytest.mark.asyncio
async def test_update_company_embed_settings_preserves_and_clears_secret(monkeypatch):
    collection = _CompanySettingsCollection(
        {
            "companyId": "company-1",
            "email": "owner@example.com",
            "name": "Company",
            "embedSettings": {"hostJwtSecret": "old-secret"},
        }
    )
    monkeypatch.setattr(companies, "companies_collection", collection)
    scope = RequestScope(email="owner@example.com", token_email="owner@example.com")

    preserved = await companies.update_company_embed_settings(
        "company-1",
        companies.CompanyEmbedSettingsRequest(enabled=True, publicToken="public-token", allowedOrigins=[]),
        scope,
    )
    assert collection.doc["embedSettings"]["hostJwtSecret"] == "old-secret"
    assert preserved["embedSettings"]["hostJwtConfigured"] is True
    assert "hostJwtSecret" not in preserved["embedSettings"]

    cleared = await companies.update_company_embed_settings(
        "company-1",
        companies.CompanyEmbedSettingsRequest(enabled=True, publicToken="public-token", clearHostJwtSecret=True),
        scope,
    )
    assert collection.doc["embedSettings"]["hostJwtSecret"] == ""
    assert cleared["embedSettings"]["hostJwtConfigured"] is False


@pytest.mark.asyncio
async def test_company_setup_contract_aggregates_factory_runtime_and_governance(monkeypatch):
    scope = RequestScope(email="owner@example.com", token_email="owner@example.com")
    monkeypatch.setattr(
        companies,
        "companies_collection",
        _Collection(
            [
                {
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "name": "Celeris",
                    "industry": "Insurance",
                    "description": "Claims and policy operations",
                    "embedSettings": {
                        "enabled": True,
                        "allowedOrigins": ["https://erp.example.com"],
                        "hostJwtSecret": "host-secret",
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        companies,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "connector-api",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "name": "ERP API",
                    "type": "api",
                    "category": "software",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"baseUrl": "https://erp.example.com/api"},
                    "runtimeRequirements": ["network", "api_credentials"],
                    "capabilityDiscovery": {
                        "entityMapping": {
                            "status": "mapped",
                            "businessObjects": ["Claim", "Policy"],
                            "readyForToolBinding": True,
                        },
                        "toolSynthesis": {
                            "typedToolCount": 3,
                            "governedToolCount": 3,
                        },
                        "candidateTasks": {"recommended": True},
                        "ingestionPipeline": {
                            "state": "ready",
                            "readyStages": 5,
                            "totalStages": 5,
                        },
                    },
                },
                {
                    "connectorId": "connector-web",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "name": "Broker Portal",
                    "type": "web",
                    "category": "web",
                    "status": "needs_auth",
                    "provider": "official",
                    "authRequired": True,
                    "config": {"startUrl": "https://portal.example.com/login"},
                    "runtimeRequirements": ["browser_or_http"],
                    "capabilityDiscovery": {
                        "entityMapping": {"status": "pending", "businessObjects": [], "readyForToolBinding": False},
                        "toolSynthesis": {"typedToolCount": 0, "governedToolCount": 0},
                        "candidateTasks": {"recommended": False},
                        "ingestionPipeline": {
                            "state": "blocked",
                            "readyStages": 1,
                            "totalStages": 5,
                            "nextStage": {"label": "Authenticate portal", "summary": "Connector needs browser credentials"},
                        },
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(companies, "credentials_collection", _Collection([{"credentialId": "cred-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(
        companies,
        "knowledge_documents_collection",
        _Collection(
            [
                {
                    "documentId": "doc-1",
                    "resourceId": "resource-1",
                    "resourceKind": "document",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "filename": "claims-policy.pdf",
                    "status": "indexed",
                    "vectorDatabaseId": "vec-1",
                    "resourceContract": {
                        "resourceId": "resource-1",
                        "resourceKind": "document",
                        "readOnly": True,
                        "indexing": {"vectorDatabaseId": "vec-1"},
                        "governance": {
                            "acl": {"visibility": "company", "allowedRoles": ["claims"], "allowedUsers": ["owner@example.com"]},
                            "citability": {"citable": True, "citationLabel": "Claims Policy"},
                        },
                        "readTools": ["knowledge.claims.search", "knowledge.claims.read_document"],
                        "resourceGate": {
                            "state": "ready",
                            "readyForRuntime": True,
                            "blockers": [],
                            "checks": {
                                "indexed": True,
                                "vectorStore": True,
                                "readTools": True,
                                "acl": True,
                                "freshness": True,
                                "citability": True,
                            },
                        },
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        companies,
        "vector_databases_collection",
        _Collection([{"vectorDatabaseId": "vec-1", "companyId": "company-1", "email": "owner@example.com", "collectionName": "claims-knowledge"}]),
    )
    monkeypatch.setattr(companies, "entities_collection", _Collection([{"entityId": "entity-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(companies, "agents_collection", _Collection([{"agentId": "agent-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(
        companies,
        "tools_collection",
        _Collection(
            [
                {"toolId": "tool-1", "companyId": "company-1", "email": "owner@example.com", "inputEntities": ["Policy"], "outputEntity": "Claim", "sideEffects": "read", "runtimeRequirements": ["api"]},
                {"toolId": "tool-2", "companyId": "company-1", "email": "owner@example.com", "inputEntities": [], "outputEntity": "", "sideEffects": "write", "runtimeRequirements": ["browser"]},
            ]
        ),
    )
    monkeypatch.setattr(companies, "benchmarks_collection", _Collection([{"benchmarkId": "bench-1", "companyId": "company-1", "email": "owner@example.com", "vertical": "insurance"}]))
    monkeypatch.setattr(
        companies,
        "benchmark_tasks_collection",
        _Collection(
            [
                {
                    "taskId": "task-1",
                    "name": "Draft claim status response",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "businessIntent": "Respond to a customer about claim status",
                    "allowedSystems": ["email", "insurance_erp", "knowledge"],
                    "expectedArtifacts": ["draft_email", "claim_summary"],
                    "riskClass": "draft",
                    "successCriteria": "Draft response cites claim status and is not sent",
                    "metadata": {
                        "taskContract": {
                            "businessIntent": "Respond to a customer about claim status",
                            "allowedSystems": ["email", "insurance_erp", "knowledge"],
                            "expectedArtifacts": ["draft_email", "claim_summary"],
                            "riskClass": "draft",
                            "successCriteria": "Draft response cites claim status and is not sent",
                        },
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(companies, "evals_collection", _Collection([{"evalId": "eval-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(companies, "eval_runs_collection", _Collection([{"runId": "eval-run-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(
        companies,
        "trajectories_collection",
        _Collection(
            [
                {"trajectoryId": "traj-1", "companyId": "company-1", "email": "owner@example.com", "status": "approved"},
                {"trajectoryId": "traj-2", "companyId": "company-1", "email": "owner@example.com", "status": "draft"},
            ]
        ),
    )
    monkeypatch.setattr(
        companies,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "companyId": "company-1",
                    "capabilityKind": "skill",
                    "riskPolicy": "human_approval_for_writes",
                    "status": "approved",
                    "instructions": "Search claim state, cite policy knowledge, draft the customer reply and stop before sending.",
                    "whenToUse": "Customer asks about claim status.",
                    "expectedArtifacts": ["draft_email", "claim_summary"],
                    "inputEntities": ["Claim"],
                    "outputEntity": "DraftEmail",
                    "preconditions": ["claim id known"],
                    "trajectoryIds": ["traj-1"],
                    "latestRegression": {"label": "pass"},
                    "version": "1.0.0",
                    "runtimeRequirements": ["network"],
                },
                {"capabilityId": "skill-2", "companyId": "company-1", "capabilityKind": "skill", "riskPolicy": "human_approval_always", "status": "ready", "runtimeRequirements": ["browser"]},
            ]
        ),
    )
    monkeypatch.setattr(
        companies,
        "sessions_collection",
        _Collection(
            [
                {"sessionId": "session-api", "companyId": "company-1", "email": "owner@example.com", "actionHistory": [{"action": "holded.search_invoices"}]},
                {
                    "sessionId": "session-browser",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "actionHistory": [{"action": "browser.navigate"}],
                    "sessionContract": {
                        "agentRuntime": {"runtimeKind": "browser", "sourceKind": "work"},
                        "selectedSkill": {"matched": True, "skillId": "skill-1"},
                        "approvalState": {"pending": 1, "requiredFor": ["send"], "hasHumanBoundary": True},
                        "artifactState": {"count": 1, "hasBusinessOutput": True},
                        "costState": {"creditsSpent": 1.5},
                        "traceState": {"traceIds": ["trace-1", "trace-2"], "replayReady": False},
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(companies, "artifacts_collection", _Collection([{"artifactId": "artifact-1", "companyId": "company-1", "email": "owner@example.com"}]))
    monkeypatch.setattr(
        companies,
        "approvals_collection",
        _Collection(
            [
                {"approvalId": "approval-1", "companyId": "company-1", "email": "owner@example.com", "status": "pending"},
                {
                    "approvalId": "approval-2",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "status": "approved",
                    "metadata": {"workItemId": "work-2"},
                },
                {
                    "approvalId": "approval-3",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "status": "pending",
                    "metadata": {"workItemId": "work-1"},
                },
            ]
        ),
    )
    monkeypatch.setattr(
        companies,
        "work_items_collection",
        _Collection(
            [
                {
                    "workItemId": "work-1",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "status": "REVIEW",
                    "triggerType": "manual",
                    "maxBudgetCredits": 2,
                    "report": {"creditsSpent": 0.5},
                    "pendingApproval": {"approvalId": "approval-3"},
                },
                {
                    "workItemId": "work-2",
                    "companyId": "company-1",
                    "email": "owner@example.com",
                    "status": "RUNNING",
                    "triggerType": "scheduled",
                    "scheduleFrequency": "daily",
                    "nextRunAt": "2000-01-01T00:00:00+00:00",
                    "maxBudgetCredits": 1,
                    "report": {"creditsSpent": 1.25},
                    "runHistory": [{"runId": "run-1"}, {"runId": "run-2"}],
                },
            ]
        ),
    )

    result = await companies.get_company_setup_contract("company-1", scope)

    assert result["company"]["name"] == "Celeris"
    assert result["contract"]["systems"]["summary"]["totalConnectors"] == 2
    assert result["contract"]["systems"]["summary"]["connectedConnectors"] == 1
    assert result["contract"]["systemFactory"]["connectorMap"]["entityMapped"] == 1
    assert result["contract"]["systemFactory"]["connectorMap"]["typedToolReady"] == 1
    assert result["contract"]["systemFactory"]["connectorMap"]["candidateTasksReady"] == 1
    assert result["contract"]["systemFactory"]["connectorMap"]["ingestionBlocked"] == 1
    assert result["contract"]["systemFactory"]["connectorMap"]["readyStages"] == 6
    assert result["contract"]["systemFactory"]["connectorMap"]["totalStages"] == 10
    assert result["contract"]["systemFactory"]["connectorMap"]["sample"][0]["businessObjects"] == ["Claim", "Policy"]
    assert result["contract"]["context"]["typedTools"] == 1
    assert result["contract"]["factory"]["readySkills"] == 2
    assert result["contract"]["runtime"]["sessions"] == 2
    assert result["contract"]["runtime"]["sessionContracts"]["withContract"] == 1
    assert result["contract"]["runtime"]["sessionContracts"]["selectedSkill"] == 1
    assert result["contract"]["runtime"]["sessionContracts"]["pendingApprovals"] == 1
    assert result["contract"]["runtime"]["sessionContracts"]["artifactOutputs"] == 1
    assert result["contract"]["runtime"]["sessionContracts"]["traceIds"] == 2
    assert result["contract"]["runtime"]["sessionContracts"]["creditsSpent"] == 1.5
    assert result["contract"]["runtime"]["pendingApprovals"] == 2
    assert result["contract"]["runtimePolicyMap"]["defaultBrowserUse"] == "exception"
    assert result["contract"]["runtimePolicyMap"]["browserRestrictedByDomain"] is True
    assert result["contract"]["runtimePolicyMap"]["runtimeClasses"]["browserCapabilities"] == 2
    assert result["contract"]["runtimePolicyMap"]["runtimeClasses"]["browserSessions"] == 1
    assert {"name": "write", "count": 4} in result["contract"]["runtimePolicyMap"]["approvalBoundaries"]["all"]
    assert result["contract"]["runtimePolicyMap"]["humanApproval"]["writesProtected"] is True
    assert result["contract"]["runtimePolicyMap"]["humanApproval"]["sendsProtected"] is True
    assert result["contract"]["runtimePolicyMap"]["gaps"] == []
    assert result["contract"]["governance"]["credentials"] == 1
    assert result["contract"]["governance"]["hostJwtConfigured"] is True
    assert "erp.example.com" in result["contract"]["governance"]["allowedOriginHosts"]
    assert "portal.example.com" in result["contract"]["governance"]["discoveredDomains"]
    assert result["contract"]["integration"]["systems"] == 2
    assert result["contract"]["integration"]["secrets"] == 1
    assert "portal.example.com" in result["contract"]["integration"]["domainAllowlist"]
    assert result["contract"]["integration"]["approvalBoundary"]["pending"] == 2
    assert result["contract"]["integration"]["acl"]["resourceAclComplete"] is True
    assert result["contract"]["integration"]["acl"]["resourcesWithAcl"] == 1
    assert result["contract"]["integration"]["compliance"]["auditEvidence"]["sessions"] == 2
    assert result["contract"]["integration"]["compliance"]["resourceAclComplete"] is True
    assert result["contract"]["resourceMap"]["documents"]["total"] == 1
    assert result["contract"]["resourceMap"]["documents"]["indexed"] == 1
    assert result["contract"]["resourceMap"]["documents"]["withResourceContract"] == 1
    assert result["contract"]["resourceMap"]["documents"]["withVectorStore"] == 1
    assert result["contract"]["resourceMap"]["documents"]["acl"]["withAcl"] == 1
    assert result["contract"]["resourceMap"]["documents"]["acl"]["companyVisible"] == 1
    assert result["contract"]["resourceMap"]["documents"]["acl"]["visibility"] == [{"name": "company", "count": 1}]
    assert result["contract"]["resourceMap"]["documents"]["sample"][0]["aclVisibility"] == "company"
    assert result["contract"]["resourceMap"]["documents"]["runtimeGate"]["ready"] == 1
    assert result["contract"]["resourceMap"]["documents"]["runtimeGate"]["blocked"] == 0
    assert result["contract"]["resourceMap"]["documents"]["runtimeGate"]["states"] == [{"name": "ready", "count": 1}]
    assert result["contract"]["resourceMap"]["documents"]["sample"][0]["runtimeGate"]["readyForRuntime"] is True
    assert "knowledge.claims.search" in result["contract"]["resourceMap"]["documents"]["readTools"]
    assert result["contract"]["resourceMap"]["vectorStores"]["total"] == 1
    assert result["contract"]["resourceMap"]["vectorStores"]["linked"] == 1
    assert result["contract"]["resourceMap"]["gaps"] == []
    assert result["contract"]["workOrchestration"]["queues"]["total"] == 2
    assert result["contract"]["workOrchestration"]["queues"]["blockedByApproval"] == 1
    assert result["contract"]["workOrchestration"]["triggers"]["scheduled"] == 1
    assert result["contract"]["workOrchestration"]["triggers"]["due"] == 1
    assert result["contract"]["workOrchestration"]["budgets"]["exhaustedItems"] == 1
    assert result["contract"]["workOrchestration"]["retries"]["totalRetryCount"] == 1
    assert result["contract"]["workOrchestration"]["approvalBoundary"]["linkedApprovalWorkItems"] == 1
    assert result["contract"]["workOrchestration"]["sla"]["needsAttention"] == 3
    assert result["contract"]["capabilityMap"]["taskContracts"]["ready"] == 1
    assert result["contract"]["capabilityMap"]["taskContracts"]["coverageRatio"] == 1
    assert "insurance_erp" in result["contract"]["capabilityMap"]["taskContracts"]["allowedSystems"]
    assert "claim_summary" in result["contract"]["capabilityMap"]["taskContracts"]["expectedArtifacts"]
    assert result["contract"]["capabilityMap"]["benchmarks"]["verticals"] == [{"name": "insurance", "count": 1}]
    assert result["contract"]["capabilityMap"]["tools"]["typed"] == 1
    assert "Claim" in result["contract"]["capabilityMap"]["tools"]["mappedEntities"]
    assert result["contract"]["capabilityMap"]["skills"]["hardened"] == 1
    assert result["contract"]["capabilityMap"]["skills"]["packages"]["manifestReady"] == 1
    assert result["contract"]["capabilityMap"]["skills"]["packages"]["publishable"] == 1
    assert result["contract"]["capabilityMap"]["skills"]["packages"]["withIoContract"] == 1
    assert result["contract"]["capabilityMap"]["skills"]["packages"]["withRegressionSuite"] == 1
    assert result["contract"]["capabilityMap"]["skills"]["packages"]["versioned"] == 1
    assert result["contract"]["factory"]["publishableSkillPackages"] == 1
    assert "draft_email" in result["contract"]["capabilityMap"]["skills"]["expectedArtifacts"]
    assert result["contract"]["readiness"]["checks"]["systems"] is True
    assert result["contract"]["readiness"]["checks"]["capabilityCoverage"] is True
    assert result["contract"]["readiness"]["checks"]["credentials"] is True
    assert result["contract"]["readiness"]["checks"]["runtime"] is True
    assert any(gap["key"] == "auth" for gap in result["contract"]["readiness"]["gaps"])
