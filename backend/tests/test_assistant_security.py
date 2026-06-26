import pytest
from fastapi import HTTPException

from app.assistant import context as assistant_context
from app.assistant import tools as assistant_tools_module
from app.assistant.context import AssistantContext, build_assistant_context
from app.assistant.service import ASSISTANT_FUNCTION_TOOLS, AutomataAssistantService
from app.assistant.tools import AutomataAssistantTools
from app.request_scope import RequestScope


class _CompanyCollection:
    def __init__(self, doc=None):
        self.doc = doc
        self.last_query = None

    async def find_one(self, query, projection=None):
        self.last_query = dict(query)
        if self.doc and all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None


class _Cursor:
    def __init__(self, docs, collection):
        self.docs = docs
        self.collection = collection

    def sort(self, *args):
        return self

    def limit(self, *_args):
        return self

    async def to_list(self, length):
        return list(self.docs[:length])


def _matches_query(doc, query):
    for key, value in query.items():
        current = doc.get(key)
        if isinstance(value, dict) and "$in" in value:
            if current not in value["$in"]:
                return False
            continue
        if isinstance(value, dict) and "$ne" in value:
            if current == value["$ne"]:
                return False
            continue
        if current != value:
            return False
    return True


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.last_find_query = None
        self.last_count_query = None
        self.last_delete_query = None

    def find(self, query, projection=None):
        self.last_find_query = dict(query)
        docs = [
            doc
            for doc in self.docs
            if _matches_query(doc, query)
        ]
        return _Cursor(docs, self)

    async def count_documents(self, query):
        self.last_count_query = dict(query)
        return len(
            [
                doc
                for doc in self.docs
                if _matches_query(doc, query)
            ]
        )

    async def delete_many(self, query):
        self.last_delete_query = dict(query)
        kept = [doc for doc in self.docs if not _matches_query(doc, query)]
        deleted_count = len(self.docs) - len(kept)
        self.docs = kept

        class _DeleteResult:
            pass

        result = _DeleteResult()
        result.deleted_count = deleted_count
        return result


def test_eval_coverage_gap_summarizes_uncovered_capabilities():
    gap = assistant_tools_module._eval_coverage_gap(
        {
            "connectors": {"covered": 1, "total": 3},
            "entities": {"covered": 0, "total": 1},
            "skills": {"covered": 2, "total": 2},
        }
    )

    assert gap == {
        "missing": {"connectors": 2, "entities": 1},
        "label": "2 connectors, 1 entity",
    }


class _ConversationCollection:
    def __init__(self, doc):
        self.doc = dict(doc)
        self.last_update_query = None
        self.last_update = None

    async def find_one(self, query, projection=None):
        if all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        self.last_update_query = dict(query)
        self.last_update = dict(update)
        self.doc.update(update.get("$set", {}))


class _ConversationListCollection:
    def __init__(self, docs):
        self.docs = docs
        self.last_find_query = None

    def find(self, query, projection=None):
        self.last_find_query = dict(query)
        docs = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return _Cursor(docs, self)


@pytest.mark.asyncio
async def test_assistant_context_rejects_foreign_company(monkeypatch):
    companies = _CompanyCollection({"email": "owner@example.com", "companyId": "company-1"})
    monkeypatch.setattr(assistant_context, "companies_collection", companies)

    with pytest.raises(HTTPException) as exc:
        await build_assistant_context(
            scope=RequestScope(email="other@example.com", token_email="other@example.com"),
            email="other@example.com",
            mode="studio_global",
            company_id="company-1",
        )

    assert exc.value.status_code == 404
    assert companies.last_query == {"email": "other@example.com", "companyId": "company-1"}


@pytest.mark.asyncio
async def test_assistant_tools_scope_queries_by_email_and_company(monkeypatch):
    from app.assistant import tools as assistant_tools

    connectors = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "name": "Owned"},
            {"email": "other@example.com", "companyId": "company-1", "name": "Foreign"},
        ]
    )
    monkeypatch.setattr(assistant_tools, "connectors_collection", connectors)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    docs = await tools.list_connectors()

    assert connectors.last_find_query == {"email": "owner@example.com", "companyId": "company-1"}
    assert [doc["name"] for doc in docs] == ["Owned"]


@pytest.mark.asyncio
async def test_assistant_tools_mask_secret_like_fields(monkeypatch):
    from app.assistant import tools as assistant_tools

    connectors = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "name": "API",
                "config": {"apiKey": "secret-value", "baseUrl": "https://example.com"},
            }
        ]
    )
    monkeypatch.setattr(assistant_tools, "connectors_collection", connectors)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    docs = await tools.list_connectors()

    assert docs[0]["config"]["apiKey"] == "***"
    assert docs[0]["config"]["baseUrl"] == "https://example.com"


@pytest.mark.asyncio
async def test_assistant_tools_delete_chat_history_scoped_to_owner_and_company(monkeypatch):
    from app.assistant import tools as assistant_tools

    conversations = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "conversationId": "current"},
            {"email": "owner@example.com", "companyId": "company-1", "conversationId": "old"},
            {"email": "owner@example.com", "companyId": "company-2", "conversationId": "other-company"},
            {"email": "other@example.com", "companyId": "company-1", "conversationId": "other-user"},
        ]
    )
    monkeypatch.setattr(assistant_tools, "assistant_conversations_collection", conversations)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    result = await tools.delete_assistant_conversations(delete_all=True, exclude_conversation_id="current")

    assert result["deleted"] == 1
    assert conversations.last_delete_query == {
        "email": "owner@example.com",
        "companyId": "company-1",
        "conversationId": {"$ne": "current"},
    }
    assert [doc["conversationId"] for doc in conversations.docs] == ["current", "other-company", "other-user"]


@pytest.mark.asyncio
async def test_assistant_tools_count_and_list_skills_from_capabilities(monkeypatch):
    from app.assistant import tools as assistant_tools

    companies = _Collection([{"email": "owner@example.com", "companyId": "company-1", "name": "Celeris"}])
    capabilities = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "capabilityKind": "skill",
                "name": "Approved skill",
                "instructions": "Search the claim, draft the answer and stop before sending.",
                "whenToUse": "Customer asks about claim status.",
                "expectedArtifacts": ["draft_email"],
                "riskPolicy": "human_approval_for_writes",
                "trajectoryIds": ["traj-1"],
                "inputEntities": ["Claim"],
                "outputEntity": "Draft email",
                "runtimeRequirements": ["browser", "network"],
                "version": 2,
                "skillPackage": {
                    "manifestVersion": 1,
                    "activation": {"description": "Customer asks about claim status."},
                    "ioContract": {
                        "declared": True,
                        "outputs": {"entity": "Draft email", "artifacts": ["draft_email"]},
                    },
                    "policies": {"riskPolicy": "human_approval_for_writes"},
                    "evidence": {
                        "regressionSuite": {"cases": [{"taskId": "task-claim"}], "publishable": True},
                    },
                },
            },
            {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "tool", "name": "Not a skill"},
        ]
    )
    connectors = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "connectorId": "conn-1",
                "status": "connected",
                "name": "ERP",
                "config": {"baseUrl": "https://claims.example.com/api"},
                "capabilityDiscovery": {
                    "entityMapping": {
                        "status": "pending",
                        "businessObjects": [],
                        "readyForToolBinding": False,
                    },
                    "toolSynthesis": {
                        "typedToolCount": 0,
                        "sendToolCount": 1,
                        "sendTools": ["smtp.send_email"],
                    },
                    "ingestionPipeline": {"state": "blocked"},
                },
            }
        ]
    )
    entity_docs = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "entityId": "ent-policy",
                "name": "Poliza",
                "sourceConnectorId": "conn-1",
                "fields": [{"name": "id", "role": "identifier", "sourcePath": "$.id"}],
                "relationships": [{"name": "cliente", "target": "Cliente", "via": "clienteId"}],
                "metadata": {
                    "aliases": ["Policy"],
                    "schemaName": "PolicyRead",
                    "permissions": {"readTools": ["erp.search_policies"], "scopes": ["policy:read"]},
                },
            },
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "entityId": "ent-claim",
                "name": "Siniestro",
            },
        ]
    )
    sessions = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "sessionId": "session-1",
                "runtimeState": {"currentUrl": "https://claims.example.com/cases"},
                "actionHistory": [{"action": "browser.navigate", "url": "https://claims.example.com/cases"}],
                "runtimeLab": {
                    "timeline": {"steps": 4, "browserSteps": 1, "toolSteps": 2, "skillSteps": 1, "failedSteps": 0, "pendingSteps": 1},
                },
                "sessionContract": {
                    "sessionId": "session-1",
                    "agentRuntime": {"runtimeKind": "hybrid", "sourceKind": "work", "workItemId": "work-1", "runId": "run-1"},
                    "selectedSkill": {"matched": True, "skillId": "skill-1", "skillName": "Approved skill"},
                    "approvalState": {"pending": 1, "requiredFor": ["send"], "hasHumanBoundary": True},
                    "artifactState": {"count": 1, "hasBusinessOutput": True},
                    "costState": {"creditsSpent": 1.25, "durationSeconds": 3.0},
                    "traceState": {"traceIds": ["run-1", "trace-1"], "traceCount": 2, "timelineSteps": 4, "replayReady": False},
                    "replayContract": {"state": "blocked", "ready": False},
                },
            }
        ]
    )
    artifacts = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "artifactId": "artifact-1",
                "sessionId": "session-1",
                "title": "Draft claim status reply",
                "artifactType": "markdown",
                "sourceTool": "smtp.draft_email",
                "metadata": {"skillId": "skill-1", "trajectoryId": "traj-1", "workItemId": "work-1", "requiresReview": True},
            }
        ]
    )
    eval_runs = _Collection([{"email": "owner@example.com", "companyId": "company-1", "label": "fail"}])
    approvals = _Collection([{"email": "owner@example.com", "companyId": "company-1", "status": "pending", "metadata": {"workItemId": "work-1"}}])
    trajectories = _Collection(
        [
            {"email": "owner@example.com", "companyId": "company-1", "trajectoryId": "traj-1", "taskId": "task-claim", "status": "approved"},
            {"email": "owner@example.com", "companyId": "company-1", "trajectoryId": "legacy-pending", "taskId": "task-legacy", "status": "needs_harvest"},
        ]
    )
    benchmark_tasks = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "benchmarkId": "bench-insurance",
                "taskId": "task-claim",
                "metadata": {
                    "businessIntent": "Respond to claim status",
                    "initialState": {"mailbox": "claims"},
                    "allowedSystems": ["email", "insurance_erp"],
                    "expectedInputs": ["claim_id"],
                    "expectedArtifacts": ["draft_email"],
                    "riskClass": "draft",
                    "evaluatorConfig": {"evaluator": "rules"},
                    "fixtures": ["claim-123"],
                    "seed": "claim-seed",
                },
            }
        ]
    )
    benchmarks = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "benchmarkId": "bench-insurance",
                "metadata": {
                    "vertical": "insurance",
                    "verticalDemo": {
                        "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
                        "runtimePath": "hybrid_api_first",
                        "coverage": [
                            {"key": "email_read", "label": "Email read"},
                            {"key": "erp_lookup", "label": "ERP lookup"},
                            {"key": "draft_artifact", "label": "Draft artifact"},
                            {"key": "trajectory", "label": "Trajectory"},
                            {"key": "skill_promotion", "label": "Skill promotion"},
                        ],
                    },
                },
            }
        ]
    )
    published_tools = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "name": "erp.search_claims",
                "inputEntities": ["Claim"],
            }
        ]
    )
    work_items = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "workItemId": "work-1",
                "status": "REVIEW",
                "triggerType": "scheduled",
                "nextRunAt": "2000-01-01T00:00:00+00:00",
                "maxBudgetCredits": 1,
                "report": {"creditsSpent": 1.25},
                "runHistory": [{"runId": "run-1"}, {"runId": "run-2"}],
                "operational": {
                    "reviewBlocked": True,
                    "pendingApprovalCount": 1,
                    "orchestration": {
                        "queueState": "REVIEW",
                        "triggerType": "scheduled",
                        "schedule": {"deadlineState": "overdue", "dueAt": "2000-01-01T00:00:00+00:00"},
                        "budget": {"maxBudgetCredits": 1, "latestCreditsSpent": 1.25, "remainingCredits": 0, "exhausted": True},
                        "retry": {"runAttempts": 2, "maxSteps": 8},
                        "approval": {"reviewBlocked": True, "pendingApprovalCount": 1},
                        "sla": {"state": "blocked", "deadlineState": "overdue", "needsAttention": True},
                        "automationGate": {"state": "blocked", "canRunUnattended": False, "blockers": ["pending_approval", "budget_exhausted"]},
                        "browserPolicy": {"state": "restricted", "enabled": True, "allowedDomains": ["claims.example.com"]},
                        "auditTrail": {"uniform": True, "eventCount": 4},
                    },
                },
            }
        ]
    )
    knowledge_docs = _Collection(
        [
            {
                "email": "owner@example.com",
                "companyId": "company-1",
                "documentId": "doc-1",
                "resourceId": "doc-1",
                "filename": "claims-policy.md",
                "status": "indexing",
                "vectorDatabaseId": "vector-1",
                "resourceContract": {
                    "resourceId": "doc-1",
                    "resourceKind": "document",
                    "readOnly": True,
                    "status": "indexing",
                    "indexing": {"indexed": False, "vectorDatabaseId": "vector-1"},
                    "governance": {
                        "freshness": {"status": "indexing"},
                        "citability": {"citable": False, "citationLabel": "claims-policy.md"},
                    },
                    "readTools": ["knowledge.claims.search", "knowledge.claims.read_document"],
                    "resourceGate": {
                        "state": "blocked",
                        "readyForRuntime": False,
                        "blockers": ["indexed", "acl", "freshness", "citability"],
                        "nextActions": ["Declare ACL visibility, roles or users for the resource."],
                        "checks": {
                            "indexed": False,
                            "vectorStore": True,
                            "readTools": True,
                            "acl": False,
                            "freshness": False,
                            "citability": False,
                        },
                    },
                },
            }
        ]
    )
    empty = _Collection([])
    monkeypatch.setattr(assistant_tools, "companies_collection", companies)
    monkeypatch.setattr(assistant_tools, "agents_collection", empty)
    monkeypatch.setattr(assistant_tools, "connectors_collection", connectors)
    monkeypatch.setattr(assistant_tools, "credentials_collection", empty)
    monkeypatch.setattr(assistant_tools, "knowledge_documents_collection", knowledge_docs)
    monkeypatch.setattr(assistant_tools, "capabilities_collection", capabilities)
    monkeypatch.setattr(assistant_tools, "tools_collection", published_tools)
    monkeypatch.setattr(assistant_tools, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(assistant_tools, "benchmark_tasks_collection", benchmark_tasks)
    monkeypatch.setattr(assistant_tools, "work_items_collection", work_items)
    monkeypatch.setattr(assistant_tools, "entities_collection", entity_docs)
    monkeypatch.setattr(assistant_tools, "sessions_collection", sessions)
    monkeypatch.setattr(assistant_tools, "artifacts_collection", artifacts)
    monkeypatch.setattr(assistant_tools, "eval_runs_collection", eval_runs)
    monkeypatch.setattr(assistant_tools, "approvals_collection", approvals)
    monkeypatch.setattr(assistant_tools, "trajectories_collection", trajectories)

    tools = AutomataAssistantTools(AssistantContext(email="owner@example.com", company_id="company-1"))
    snapshot = await tools.studio_snapshot()
    capabilities_payload = await tools.list_capabilities()

    assert snapshot["counts"]["skills"] == 1
    assert snapshot["counts"]["pendingApprovals"] == 1
    assert snapshot["operatingState"]["factory"]["connectedConnectors"] == 1
    assert snapshot["operatingState"]["factory"]["connectorMap"]["entityPending"] == 1
    assert snapshot["operatingState"]["factory"]["connectorMap"]["ingestionBlocked"] == 1
    assert snapshot["operatingState"]["factory"]["connectorMap"]["factoryPipelineGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["factory"]["connectorMap"]["factoryPipelineGate"]["checks"]["entityMappingComplete"] is False
    assert snapshot["operatingState"]["factory"]["factoryEvalGate"] == {
        "state": "blocked",
        "ready": False,
        "factoryConnectors": 1,
        "referencedConnectors": 0,
        "coveredConnectors": 0,
        "missingConnectorRefs": 1,
        "ungatedConnectors": 1,
        "checks": {
            "connectorsPresent": True,
            "connectorsReferencedByBenchmarks": False,
            "connectorRegressionsPassing": False,
        },
        "blockers": ["connectorsReferencedByBenchmarks", "connectorRegressionsPassing"],
        "hardeningPlaybook": [
            {
                "gap": "connector_benchmark_refs",
                "count": 1,
                "area": "evals",
                "severity": "high",
                "action": "Reference every factory connector from benchmark tasks or promoted skill regression suites.",
            },
            {
                "gap": "connector_regression_gate",
                "count": 1,
                "area": "evals",
                "severity": "high",
                "action": "Run passing regressions for every connector-backed production capability.",
            },
        ],
    }
    assert snapshot["operatingState"]["factory"]["approvedTrajectories"] == 1
    assert snapshot["operatingState"]["companySetup"]["integration"]["systems"] == 1
    assert snapshot["operatingState"]["companySetup"]["integration"]["domainAllowlist"] == ["claims.example.com"]
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["state"] == "partial"
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["ready"] is False
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["blockers"] == ["secrets", "resource_acl", "host_jwt"]
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["checks"]["human_approval"] is True
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["checks"]["audit_evidence"] is True
    assert snapshot["operatingState"]["companySetup"]["setupGate"]["hardeningPlaybook"][0] == {
        "gap": "secrets",
        "area": "credentials",
        "severity": "high",
        "action": "Attach credentials or OAuth profiles for systems that need authenticated runtime access.",
    }
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["ready"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["expectedInputs"] == ["claim_id"]
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["reproducibility"]["readyForReplay"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["reproducibility"]["replayReadyRatio"] == 1.0
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["hardening"]["complete"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["hardening"]["evaluationReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["taskContracts"]["hardening"]["missingFields"] == [
        {"name": "successCriteria", "count": 1}
    ]
    assert snapshot["operatingState"]["capabilityMap"]["tools"]["typed"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["total"] == 2
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["ready"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["toolBindingReady"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["withRelationships"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["coverageScore"] == 0.5
    assert snapshot["operatingState"]["capabilityMap"]["entityMap"]["bindingBlockers"] == [
        {"name": "identifier", "count": 1},
        {"name": "read_access", "count": 1},
        {"name": "relationships", "count": 1},
    ]
    assert {
        "gap": "identifier",
        "count": 1,
        "area": "schema",
        "severity": "high",
        "action": "Mark at least one identifier field before binding this entity to tool calls.",
    } in snapshot["operatingState"]["capabilityMap"]["entityMap"]["hardeningPlaybook"]
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["hardened"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["productionGate"]["missingGate"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["manifestReady"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["ioContracts"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["regressionSuites"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["publishable"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["versioned"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["releaseStatus"] == [{"name": "draft", "count": 1}]
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["releaseReadiness"]["readyForPublish"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["releaseReadiness"]["draft"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["releaseGate"]["state"] == "needs_hardening"
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["releaseGate"]["checks"] == {
        "versionedPackages": True,
        "publishablePackages": True,
        "reviewedReleaseStatus": False,
        "publishedSkillsSafe": True,
    }
    assert snapshot["operatingState"]["capabilityMap"]["skills"]["packages"]["hardeningPlaybook"][0] == {
        "gap": "release_status",
        "count": 1,
        "area": "release",
        "severity": "medium",
        "action": "Move publishable skills from draft to ready or published once review is complete.",
    }
    assert snapshot["operatingState"]["capabilityMap"]["evalGate"]["totalSkills"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["evalGate"]["regressionLinked"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["evalGate"]["passing"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["evalGate"]["missing"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["evalCoverage"]["connectors"]["total"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["evalCoverage"]["entities"]["total"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["evalCoverage"]["skills"]["total"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["benchmarks"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["tasks"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["taskContracts"]["complete"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["promotionGate"]["blockers"] == [
        "incomplete_task_contracts",
        "no_skills",
        "no_regression_runs",
    ]
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["regressionGate"]["state"] == "empty"
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["regressionGate"]["nextActions"] == [
        "Create benchmarks that reference connectors, entities or skills before evaluating coverage."
    ]
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["evalCenterGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["evalCenterGate"]["checks"]["promotionGateReady"] is False
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["judgeStrategyGate"]["state"] == "needs_hardening"
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["judgeStrategyGate"]["deterministic"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["judgeStrategyGate"]["stateful"] == 1
    assert {
        "gap": "no_regression_runs",
        "count": 1,
        "area": "evals",
        "severity": "high",
        "action": "Run benchmark regressions and judge task trials before promotion.",
    } in snapshot["operatingState"]["capabilityMap"]["benchmarkPortfolio"]["hardeningPlaybook"]
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["total"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["partial"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["smokeReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["smokeBlocked"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["proofReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["proofBlocked"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["replayContractReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["replayContractBlocked"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["enterpriseReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["integrationReady"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["factoryReady"] == 0
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["runtimeReady"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["demos"][0]["missing"] == ["trajectory", "skill_promotion"]
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["demos"][0]["insuranceFlowProofGate"]["state"] == "needs_hardening"
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["demos"][0]["insuranceFlowProofGate"]["readySteps"] == 3
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["demos"][0]["insuranceFlowProofGate"]["missing"] == [
        "document_grounding",
        "approval_boundary",
        "benchmark",
        "trajectory",
        "skill_promotion",
        "runtime_replay",
        "smoke_gate",
    ]
    assert {
        "gap": "skill_promotion",
        "count": 1,
        "group": "factory",
        "area": "skills",
        "severity": "high",
        "action": "Promote the approved trajectory into a reusable skill package.",
        "example": {
            "benchmarkId": "bench-insurance",
            "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
        },
    } in snapshot["operatingState"]["capabilityMap"]["verticalDemos"]["hardeningPlaybook"]
    assert snapshot["operatingState"]["capabilityMap"]["verticalDemoGaps"] == [
        {
            "benchmarkId": "bench-insurance",
            "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
            "group": "factory",
            "label": "Capability factory",
            "state": "missing",
            "missing": ["trajectory", "skill_promotion"],
        }
    ]
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["tasks"]["withTrajectory"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["trajectories"]["approved"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["trajectories"]["legacyPendingRows"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["skills"]["withApprovedTrajectory"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["skills"]["reusable"] == 1
    assert snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["path"]["trajectoryToSkill"] is True
    assert {
        "gap": "pending_trajectory_rows",
        "count": 1,
        "area": "data_model",
        "severity": "medium",
        "action": "Keep pending harvest work in benchmark tasks; trajectories should contain generated execution evidence only.",
    } in snapshot["operatingState"]["capabilityMap"]["promotionPipeline"]["hardeningPlaybook"]
    assert snapshot["operatingState"]["resourceMap"]["total"] == 1
    assert snapshot["operatingState"]["resourceMap"]["indexed"] == 0
    assert snapshot["operatingState"]["resourceMap"]["citable"] == 0
    assert snapshot["operatingState"]["resourceMap"]["withResourceContract"] == 1
    assert snapshot["operatingState"]["resourceMap"]["acl"]["withAcl"] == 0
    assert snapshot["operatingState"]["resourceMap"]["acl"]["visibility"] == [{"name": "unspecified", "count": 1}]
    assert snapshot["operatingState"]["resourceMap"]["sample"][0]["aclVisibility"] == "unspecified"
    assert snapshot["operatingState"]["resourceMap"]["citations"]["labels"] == ["claims-policy.md"]
    assert snapshot["operatingState"]["resourceMap"]["readTools"] == ["knowledge.claims.search", "knowledge.claims.read_document"]
    assert snapshot["operatingState"]["resourceMap"]["runtimeGate"]["ready"] == 0
    assert snapshot["operatingState"]["resourceMap"]["runtimeGate"]["blocked"] == 1
    assert snapshot["operatingState"]["resourceMap"]["runtimeGate"]["blockers"] == [
        {"name": "acl", "count": 1},
        {"name": "citability", "count": 1},
        {"name": "freshness", "count": 1},
        {"name": "indexed", "count": 1},
    ]
    assert snapshot["operatingState"]["resourceMap"]["sample"][0]["runtimeGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["resourceMap"]["gaps"][0]["key"] == "resource_acl"
    assert snapshot["operatingState"]["resourceMap"]["hardeningPlaybook"][0] == {
        "gap": "resource_acl",
        "count": 1,
        "area": "security",
        "severity": "high",
        "action": "Declare ACL visibility, allowed roles or users before enabling AgentRuntime grounding.",
    }
    assert snapshot["operatingState"]["workOrchestration"]["triggers"]["due"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["budgets"]["exhaustedItems"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["retries"]["totalRetryCount"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["sla"]["needsAttention"] == 3
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["withContract"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["budgeted"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["retryConfigured"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["runAttempts"] == 2
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["slaTracked"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["slaNeedsAttention"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["approvalGates"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["auditTrails"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["browserAllowlists"] == 1
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["workOperationsGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["workOperationsGate"]["checks"]["budgetsAvailable"] is False
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["workOperationsGate"]["checks"]["automationUnblocked"] is False
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["hardeningPlaybook"][0] == {
        "gap": "budget_exhausted",
        "count": 1,
        "area": "budgets",
        "severity": "high",
        "action": "Increase budget or reduce runtime scope before retrying this work item.",
    }
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["sample"][0]["workItemId"] == "work-1"
    assert snapshot["operatingState"]["workOrchestration"]["contracts"]["sample"][0]["slaState"] == "blocked"
    assert snapshot["operatingState"]["runtime"]["failingEvalRuns"] == 1
    assert snapshot["operatingState"]["runtime"]["sessions"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["withContract"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["selectedSkill"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["pendingApprovals"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["artifactOutputs"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["traceIds"] == 2
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["runtimeKinds"] == [{"name": "hybrid", "count": 1}]
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["replayContracts"] == {"ready": 0, "blocked": 1, "total": 1}
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["timeline"]["steps"] == 4
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["timeline"]["toolSteps"] == 2
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["timeline"]["skillSteps"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["sample"][0]["sessionId"] == "session-1"
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["sample"][0]["skillId"] == "skill-1"
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["sample"][0]["pendingApprovals"] == 1
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["sample"][0]["timelineSteps"] == 4
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["runtimeSessionGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["runtime"]["sessionContracts"]["runtimeSessionGate"]["checks"]["approvalsResolved"] is False
    assert {
        "gap": "pending_approvals",
        "count": 1,
        "area": "approvals",
        "severity": "high",
        "action": "Resolve pending human approvals before delivering side effects or publishing the capability.",
    } in snapshot["operatingState"]["runtime"]["sessionContracts"]["hardeningPlaybook"]
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["total"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["separatedFromTrace"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["runtimeLinked"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["capabilityLinked"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["workLinked"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["knowledgeReady"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["reviewRequired"] == 1
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["hardeningPlaybook"][0] == {
        "gap": "artifact_review",
        "count": 1,
        "area": "approvals",
        "severity": "high",
        "action": "Complete human review before reusing or delivering this business output.",
    }
    assert snapshot["operatingState"]["runtime"]["artifactOutputs"]["sample"][0]["source"]["sourceTool"] == "smtp.draft_email"
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["defaultBrowserUse"] == "exception"
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["browserRestrictedByDomain"] is True
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["browserDomainGovernance"]["allowedDomains"] == ["claims.example.com"]
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["browserDomainGovernance"]["observedDomains"] == ["claims.example.com"]
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["browserDomainGovernance"]["coverageRatio"] == 1.0
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClasses"]["browserCapabilities"] == 1
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClasses"]["hybridCapabilities"] == 1
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClasses"]["hybridSessions"] == 1
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClasses"]["browserSessions"] == 1
    assert [mode["runtimeType"] for mode in snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeTaxonomy"]["modes"]] == [
        "api_runtime",
        "browser_runtime",
        "hybrid_runtime",
    ]
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeTaxonomy"]["apiFirst"] is True
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeTaxonomy"]["browserDefault"] == "exception"
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClassGate"]["state"] == "ready"
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["runtimeClassGate"]["checks"] == {
        "declaredPolicies": True,
        "observedRuntimeCovered": True,
        "browserAsException": True,
        "browserDomainGoverned": True,
        "sideEffectsApproved": True,
    }
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["approvalBoundaries"]["hardening"]["ready"] is True
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["humanApproval"]["writesProtected"] is True
    assert snapshot["operatingState"]["runtime"]["runtimePolicyMap"]["humanApproval"]["sendsProtected"] is True
    assert snapshot["operatingState"]["studioOsGate"]["state"] == "blocked"
    assert snapshot["operatingState"]["studioOsGate"]["surfaces"] == {"total": 5, "ready": 1, "needsWork": 4, "missing": 0}
    assert snapshot["operatingState"]["studioOsGate"]["blockers"] == [
        "Company Setup",
        "Capability Factory",
        "Runtime Lab",
        "Work Orchestration",
    ]
    assert snapshot["automataGuidance"]["studioOsGate"] == snapshot["operatingState"]["studioOsGate"]
    assert snapshot["operatingState"]["recommendedNextActions"][0]["area"] == "evals"
    assert snapshot["automataGuidance"]["role"] == "studio_copilot"
    assert snapshot["automataGuidance"]["primaryNextAction"]["area"] == "evals"
    assert snapshot["automataGuidance"]["riskAlerts"][0]["area"] == "approvals"
    assert any(alert["message"] == "Connector send tools are not fully covered by human approval gates." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["area"] == "connectors" for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "The insurance flow is not proof-ready across email, ERP, documents, approvals, benchmark, trajectory, skill and replay." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Business entities exist but are not all ready for runtime tool binding." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["area"] == "company_setup" for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Benchmark portfolio is not fully gated by passing regressions." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Factory connectors are not fully covered by benchmark regression gates." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "A vertical demo is missing operational readiness evidence." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Capability Factory pipeline is not ready end-to-end." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Eval center gate is not ready for production promotion." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Runtime Lab sessions are not yet durable, replay-ready evidence." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Business output delivery gate is blocked by missing traceability, capability linkage or review." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Insurance replay contract is blocked; AgentRuntime replay, approved skill, draft artifact and approval boundary evidence must all be present." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Insurance business output contract is blocked; draft artifact, approval boundary and replay assertion must be proven before delivery." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Work operations gate is not ready for unattended orchestration." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(alert["message"] == "Knowledge resources exist without explicit ACL visibility." for alert in snapshot["automataGuidance"]["riskAlerts"])
    assert any(item["surface"] == "Capability Factory" for item in snapshot["automataGuidance"]["surfacePlaybook"])
    assert any(
        action["area"] == "approvals"
        and action["action"] == "Require human approval for write/send boundaries."
        and "send tool(s)" in action["reason"]
        for action in snapshot["operatingState"]["recommendedNextActions"]
    )
    assert any(
        action["area"] == "entities"
        and action["action"] == "Complete entity mapping for runtime binding before publishing connector tools."
        and action["reason"] == "1 entity blocked by identifier."
        for action in snapshot["operatingState"]["recommendedNextActions"]
    )
    assert any(
        action["area"] == "artifacts"
        and action["action"] == "Record a passing replay that proves the draft artifact and approval boundary."
        and action["reason"] == "Insurance business output contract is needs_hardening; missing passing replay asserting artifact and approval boundary."
        for action in snapshot["operatingState"]["recommendedNextActions"]
    )
    assert any(
        action["area"] == "vertical_demo"
        and action["action"] == "Attach governed knowledge resources or read tools for document grounding."
        and action["reason"] == "Insurance flow proof gate is needs_hardening; missing knowledge system or document search tool, human approval or send boundary, benchmark task, approved/source trajectory, promoted skill package, passing replay/eval run, draft-only approval-safe smoke gate."
        for action in snapshot["operatingState"]["recommendedNextActions"]
    )
    assert any(
        action["area"] == "runtime"
        and action["reason"].startswith("Insurance replay contract is needs_hardening; missing ")
        for action in snapshot["operatingState"]["recommendedNextActions"]
    )
    company_setup = next(item for item in snapshot["automataGuidance"]["surfacePlaybook"] if item["surface"] == "Company Setup")
    assert company_setup["status"] == "needs_work"
    assert company_setup["hardening"] == {
        "gap": "secrets",
        "area": "credentials",
        "severity": "high",
        "action": "Attach credentials or OAuth profiles for systems that need authenticated runtime access.",
    }
    assert company_setup["evidence"] == {
        "systems": 1,
        "secrets": 0,
        "allowedDomains": 1,
        "setupGate": "partial",
    }
    assert company_setup["nextAction"] == company_setup["hardening"]["action"]
    capability_factory = next(item for item in snapshot["automataGuidance"]["surfacePlaybook"] if item["surface"] == "Capability Factory")
    assert capability_factory["status"] == "needs_work"
    assert capability_factory["hardening"]["action"]
    assert capability_factory["evidence"] == {
        "connectors": 1,
        "typedTools": 0,
        "sendTools": 1,
        "sendApprovalReady": False,
        "uncoveredSendTools": 1,
        "evalCoveredConnectors": 0,
        "evalReferencedConnectors": 0,
        "evalUngatedConnectors": 1,
        "entities": 2,
        "benchmarkTasks": 1,
        "approvedTrajectories": 1,
        "skills": 1,
        "proofReady": 0,
        "proofBlocked": 1,
        "replayContractReady": 0,
        "replayContractBlocked": 1,
        "businessOutputContractReady": 0,
        "businessOutputContractBlocked": 1,
    }
    assert capability_factory["nextAction"] == capability_factory["hardening"]["action"]
    runtime_lab = next(item for item in snapshot["automataGuidance"]["surfacePlaybook"] if item["surface"] == "Runtime Lab")
    assert runtime_lab["status"] == "needs_work"
    assert runtime_lab["hardening"]["gap"] == "agentRuntimeReplay"
    assert runtime_lab["evidence"] == {
        "sessions": 1,
        "replayReadySessions": 0,
        "replayContractsReady": 0,
        "replayContractsBlocked": 1,
        "pendingApprovals": 1,
        "artifacts": 1,
        "reviewRequiredArtifacts": 1,
        "deliveryReadyArtifacts": 0,
        "deliveryBlockedArtifacts": 1,
        "replayContractReady": 0,
        "replayContractBlocked": 1,
        "businessOutputContractReady": 0,
        "businessOutputContractBlocked": 1,
    }
    assert runtime_lab["nextAction"] == runtime_lab["hardening"]["action"]
    work_orchestration = next(item for item in snapshot["automataGuidance"]["surfacePlaybook"] if item["surface"] == "Work Orchestration")
    assert work_orchestration["evidence"] == {
        "workItems": 1,
        "contractReady": 1,
        "scheduledDue": 1,
        "approvalBlocked": 1,
        "budgetExhausted": 1,
        "retries": 1,
    }
    automata = next(item for item in snapshot["automataGuidance"]["surfacePlaybook"] if item["surface"] == "Automata")
    assert automata["evidence"]["role"] == "studio_copilot"
    assert automata["evidence"]["riskAlerts"] == len(snapshot["automataGuidance"]["riskAlerts"])
    assert automata["evidence"]["recommendedActionCandidates"] >= len(snapshot["operatingState"]["recommendedNextActions"])
    assert automata["evidence"]["failurePrompts"] == 3
    assert capabilities.last_count_query == {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill"}
    assert len(capabilities_payload["skills"]) == 1
    listed_skill = capabilities_payload["skills"][0]
    assert listed_skill["name"] == "Approved skill"
    assert listed_skill["expectedArtifacts"] == ["draft_email"]
    assert listed_skill["trajectoryIds"] == ["traj-1"]
    assert listed_skill["inputEntities"] == ["Claim"]
    assert listed_skill["skillPackage"]["ioContract"]["declared"] is True
    assert capabilities.last_find_query == {"email": "owner@example.com", "companyId": "company-1", "capabilityKind": "skill"}


@pytest.mark.asyncio
async def test_assistant_uses_gpt5_mini_with_low_latency_studio_tools(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "studio_list_companies",
                            "arguments": '{"limit": 10}',
                        }
                    ]
                )
            assert any(item.get("type") == "function_call_output" for item in kwargs["input"])
            return _FakeResponse([], "The active company is Celeris.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_companies(self, limit=10):
            return [{"companyId": "company-1", "name": "Celeris"}][:limit]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("AUTOMATA_ASSISTANT_MODEL", raising=False)
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("list my companies and mention what I can do next")

    assert draft is None
    assert "Celeris" in reply
    assert calls[0]["model"] == "gpt-5-mini"
    assert calls[0]["reasoning"] == {"effort": "minimal"}
    assert calls[0]["text"] == {"verbosity": "low"}
    assert calls[0]["max_output_tokens"] == 700
    assert {tool["name"] for tool in calls[0]["tools"]} >= {"studio_list_companies", "studio_list_connectors", "studio_list_capabilities"}
    assert any(event.get("toolName") == "studio_list_companies" for event in events)
    assert any("Celeris" in item.get("output", "") for item in calls[1]["input"] if item.get("type") == "function_call_output")


@pytest.mark.asyncio
async def test_assistant_executes_chat_history_delete_tool_with_current_conversation_excluded(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    deletions = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-delete",
                            "name": "studio_delete_assistant_conversations",
                            "arguments": '{"deleteAll": true}',
                        }
                    ]
                )
            return _FakeResponse([], "Deleted the old Automata chat history.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def delete_assistant_conversations(self, *, conversation_ids=None, delete_all=False, exclude_conversation_id=""):
            deletions.append(
                {
                    "conversation_ids": conversation_ids,
                    "delete_all": delete_all,
                    "exclude_conversation_id": exclude_conversation_id,
                }
            )
            return {"deleted": 3, "requested": 0, "deleteAll": delete_all, "excludedConversationId": exclude_conversation_id}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    service.current_conversation_id = "current-conversation"
    reply, events, draft = await service.respond("delete my chat history")

    assert draft is None
    assert reply == "Deleted the old Automata chat history."
    assert deletions == [
        {
            "conversation_ids": [],
            "delete_all": True,
            "exclude_conversation_id": "current-conversation",
        }
    ]
    assert any(event.get("toolName") == "studio_delete_assistant_conversations" for event in events)


@pytest.mark.asyncio
async def test_assistant_executes_create_work_item_tool_after_user_confirmation(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    created = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-create-work",
                            "name": "studio_create_work_item",
                            "arguments": (
                                '{"title":"Daily Good Morning Email",'
                                '"prompt":"Send an email to mauricio.munozlopez@gmail.com saying Good morning.",'
                                '"triggerType":"scheduled",'
                                '"scheduleFrequency":"daily",'
                                '"scheduleTime":"09:00"}'
                            ),
                        }
                    ]
                )
            return _FakeResponse([], "Created Daily Good Morning Email.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def create_work_item(self, **kwargs):
            created.append(kwargs)
            return {
                "success": True,
                "workItem": {
                    "workItemId": "work-1",
                    "title": kwargs["title"],
                    "triggerType": kwargs["trigger_type"],
                    "scheduleFrequency": kwargs["schedule_frequency"],
                    "scheduleTime": kwargs["schedule_time"],
                },
            }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("yes create it")

    assert draft is None
    assert reply == "Created Daily Good Morning Email."
    assert created == [
        {
            "title": "Daily Good Morning Email",
            "prompt": "Send an email to mauricio.munozlopez@gmail.com saying Good morning.",
            "success_criteria": "",
            "agent_id": "",
            "agent_name": "",
            "run_target": "all",
            "browser_enabled": True,
            "browser_mode": "headless",
            "max_credits_per_run": 5.0,
            "max_budget_credits": None,
            "max_steps": 8,
            "trigger_type": "scheduled",
            "schedule_frequency": "daily",
            "schedule_time": "09:00",
            "schedule_day_of_week": 1,
            "trigger_config": {},
            "judge_implementation": "llm",
        }
    ]
    assert any(event.get("toolName") == "studio_create_work_item" for event in events)


def test_assistant_exposes_core_action_tools():
    names = {tool["name"] for tool in ASSISTANT_FUNCTION_TOOLS}
    snapshot_tool = next(tool for tool in ASSISTANT_FUNCTION_TOOLS if tool["name"] == "studio_snapshot")

    assert {
        "studio_snapshot",
        "studio_create_work_item",
        "studio_update_work_item",
        "studio_run_work_item",
        "studio_create_connector",
        "studio_test_connector",
        "studio_create_agent",
        "studio_approve_approval",
        "studio_save_knowledge_document_from_url",
        "studio_update_tool_approval",
        "studio_promote_trajectory_to_skill",
        "studio_list_credentials",
        "studio_list_api_keys",
        "studio_list_browser_profiles",
        "studio_get_account_info",
        "studio_get_analytics_summary",
        "studio_get_billing_plan_status",
        "studio_get_assistant_memory",
        "studio_rebuild_assistant_memory",
    } <= names
    assert "operating state" in snapshot_tool["description"]


def test_assistant_snapshot_reply_surfaces_operating_next_action():
    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))

    reply = service._snapshot_reply(
        {
            "counts": {"companies": 1, "agents": 1, "connectors": 2, "tools": 3, "skills": 4},
            "operatingState": {
                "readiness": {"score": 0.6},
                "studioOsGate": {"state": "blocked", "surfaces": {"ready": 2, "total": 5}, "blockers": ["Capability Factory"]},
                "companySetup": {
                    "integration": {"systems": 2, "secrets": 1, "domainAllowlist": ["erp.example.com", "studio.example.com"]},
                    "setupGate": {"state": "partial", "blockers": ["resource_acl"]},
                },
                "factory": {
                    "connectorMap": {
                        "total": 3,
                        "entityMapped": 1,
                        "entityPending": 1,
                        "typedToolReady": 2,
                        "toolSynthesisPending": 1,
                        "hardenedToolCount": 3,
                        "needsHardeningCount": 2,
                        "toolHardeningGaps": [{"name": "risk_policy", "count": 2}],
                        "sendToolCount": 2,
                        "sendApprovalGate": {
                            "required": True,
                            "ready": False,
                            "approvalRequiredTools": ["smtp.send_email"],
                            "uncoveredSendTools": ["gmail.send_email"],
                            "unknownSendToolCount": 0,
                        },
                        "toolProductionGate": {
                            "state": "needs_hardening",
                            "totalTools": 5,
                            "hardenedTools": 3,
                            "needsHardening": 2,
                            "checks": {
                                "typedTools": True,
                                "hardenedContracts": False,
                                "schemasPoliciesScopesEntities": False,
                            },
                        },
                        "factoryPipelineGate": {"state": "blocked", "ready": False},
                        "candidateTasksReady": 1,
                        "ingestionBlocked": 1,
                        "gaps": [{"key": "entity_mapping", "label": "ERP needs business entity mapping."}],
                    },
                    "factoryEvalGate": {
                        "state": "blocked",
                        "factoryConnectors": 3,
                        "coveredConnectors": 1,
                        "missingConnectorRefs": 2,
                    },
                },
                "capabilityMap": {
                    "taskContracts": {"ready": 2, "total": 5, "reproducibility": {"readyForReplay": 3, "total": 5}},
                    "entityMap": {
                        "total": 4,
                        "ready": 2,
                        "toolBindingReady": 1,
                        "withRelationships": 2,
                        "bindingBlockers": [{"name": "read_access", "count": 2}],
                    },
                    "skills": {
                        "hardened": 1,
                        "total": 4,
                        "packages": {
                            "publishable": 1,
                            "total": 4,
                            "ioContracts": 2,
                            "regressionSuites": 1,
                            "assets": 1,
                            "resources": 1,
                            "scripts": 1,
                            "versioned": 3,
                            "releaseReadiness": {"published": 1, "readyForPublish": 2, "draft": 1, "withVersionHistory": 2},
                            "releaseGate": {"state": "needs_hardening", "ready": False},
                        },
                    },
                    "evalGate": {"passing": 1, "blockedByRegression": 1, "missing": 2},
                    "evalCoverage": {
                        "connectors": {"covered": 2, "total": 3},
                        "entities": {"covered": 1, "total": 4},
                        "skills": {"covered": 2, "total": 5},
                    },
                    "benchmarkPortfolio": {
                        "benchmarks": 2,
                        "tasks": 7,
                        "promotionGate": {"state": "blocked"},
                        "evalCenterGate": {"state": "blocked", "taskCoverage": {"replayReady": 3, "total": 7}},
                        "regressionGate": {"state": "needs_regression", "gatedCapabilities": 3, "totalCapabilities": 5},
                        "judgeStrategyGate": {
                            "state": "needs_hardening",
                            "total": 7,
                            "deterministic": 4,
                            "stateful": 6,
                            "llmOnly": 2,
                            "hardeningPlaybook": [
                                {
                                    "gap": "llm_only_judge",
                                    "action": "Add deterministic checks or stateful replay so LLM judges remain complementary.",
                                }
                            ],
                        },
                    },
                    "promotionPipeline": {
                        "ready": False,
                        "tasks": {"total": 7, "withTrajectory": 4},
                        "trajectories": {"total": 5, "approved": 3, "legacyPendingRows": 1},
                        "skills": {"total": 4, "withApprovedTrajectory": 2},
                        "skillPromotionGate": {
                            "state": "blocked",
                            "blockers": ["approvedTrajectoryLinked", "reusablePackages"],
                        },
                        "gaps": [{"key": "skill_hardening", "label": "Some promoted skills are missing reusable package hardening."}],
                    },
                    "verticalDemos": {
                        "ready": 1,
                        "total": 2,
                        "enterpriseReady": 1,
                        "smokeReady": 1,
                        "proofReady": 1,
                        "proofBlocked": 1,
                        "replayContractReady": 1,
                        "replayContractBlocked": 1,
                        "businessOutputContractReady": 1,
                        "businessOutputContractBlocked": 1,
                        "demos": [
                            {
                                "insuranceFlowProofGate": {
                                    "ready": False,
                                    "state": "needs_hardening",
                                    "readySteps": 7,
                                    "totalSteps": 9,
                                    "missing": ["runtime_replay", "smoke_gate"],
                                    "steps": [{"key": "runtime_replay", "label": "Runtime replay"}],
                                    "runtimeReplayContract": {
                                        "state": "needs_hardening",
                                        "ready": False,
                                        "missing": ["agentRuntimeReplay"],
                                        "missingEvidence": ["passing AgentRuntime replay"],
                                        "evidenceFound": {
                                            "promotedSkillIds": ["skill-claims"],
                                            "artifacts": ["draft_email"],
                                            "approvalBoundaries": ["draft_only_before_send"],
                                        },
                                    },
                                    "businessOutputContract": {
                                        "state": "needs_hardening",
                                        "ready": False,
                                        "outputArtifact": "draft_email",
                                        "deliveryPolicy": "human_approval_before_send",
                                        "missing": ["passingReplayAssertsOutput"],
                                        "missingEvidence": [
                                            "passing replay asserting artifact and approval boundary"
                                        ],
                                        "evidenceFound": {
                                            "artifacts": ["draft_email"],
                                            "approvalBoundaries": ["draft_only_before_send"],
                                        },
                                    },
                                    "hardeningPlaybook": [
                                        {
                                            "gap": "runtime_replay",
                                            "action": "Replay the approved insurance skill in AgentRuntime before declaring the demo production-ready.",
                                        }
                                    ],
                                }
                            }
                        ],
                    },
                    "verticalDemoGaps": [{"group": "factory", "label": "Capability factory"}],
                },
                "resourceMap": {
                    "total": 3,
                    "indexed": 2,
                    "citable": 1,
                    "acl": {"withAcl": 1},
                    "readTools": ["knowledge.claims.search", "knowledge.claims.read_document"],
                    "grounding": {"requirements": {"readTools": 2, "current": 2}},
                    "runtimeGate": {"ready": 1, "blocked": 2, "blockers": [{"name": "acl", "count": 2}]},
                },
                "runtime": {
                    "runtimePolicyMap": {
                        "defaultBrowserUse": "exception",
                        "runtimeClasses": {"browserSessions": 1},
                        "runtimeTaxonomy": {
                            "defaultMode": "api_runtime",
                            "browserDefault": "exception",
                            "apiFirst": True,
                            "browserExceptionDiscipline": {
                                "state": "ready",
                                "browserOnlySessions": 0,
                                "apiFirstSessions": 2,
                            },
                            "modes": [
                                {"runtimeType": "api_runtime", "capabilities": 2, "observedSessions": 1},
                                {"runtimeType": "browser_runtime", "capabilities": 1, "observedSessions": 0},
                                {"runtimeType": "hybrid_runtime", "capabilities": 1, "observedSessions": 1},
                            ],
                        },
                        "runtimeClassGate": {
                            "state": "needs_hardening",
                            "blockers": [{"name": "browserDomainGoverned", "count": 1}],
                        },
                        "humanApproval": {"writesProtected": True, "sendsProtected": True},
                        "approvalBoundaries": {"sideEffectsProtected": False, "missingObservedApproval": ["write"]},
                        "browserDomainGovernance": {
                            "allowedDomains": ["erp.example.com"],
                            "observedDomains": ["erp.example.com", "unknown.example.net"],
                            "coveredDomains": ["erp.example.com"],
                            "uncoveredDomains": ["unknown.example.net"],
                        },
                    },
                    "sessionContracts": {
                        "creditsSpent": 2.5,
                        "durationSeconds": 8.25,
                        "timeline": {"steps": 6, "toolSteps": 3, "skillSteps": 1, "replayReadySessions": 1},
                        "replayContracts": {"ready": 1, "blocked": 1},
                    },
                    "artifactOutputs": {
                        "total": 3,
                        "separatedFromTrace": 3,
                        "runtimeLinked": 2,
                        "capabilityLinked": 2,
                        "workLinked": 1,
                        "knowledgeReady": 2,
                        "reusableAsKnowledge": 1,
                        "reviewRequired": 1,
                        "blockedForReuse": 1,
                        "businessOutputDeliveryGate": {
                            "state": "blocked",
                            "total": 3,
                            "readyOutputs": 1,
                        },
                    },
                },
                "workOrchestration": {
                    "sla": {"needsAttention": 3},
                    "triggers": {"due": 2},
                    "budgets": {"exhaustedItems": 1},
                    "retries": {"totalRetryCount": 4},
                    "contracts": {
                        "withContract": 2,
                        "total": 4,
                        "slaTracked": 3,
                        "auditTrails": 2,
                        "approvalGates": 2,
                        "browserAllowlists": 1,
                        "runAttempts": 5,
                        "unattendedReady": 1,
                        "unattendedBlocked": 2,
                        "workOperationsGate": {"state": "blocked"},
                        "automationBlockers": [{"name": "pending_approval", "count": 2}],
                    },
                },
                "recommendedNextActions": [{"area": "benchmarks", "action": "Create benchmark tasks for the top insurance workflows."}],
                "automataGuidance": {
                    "primaryNextAction": {"area": "evals", "action": "Inspect failed traces before publishing."},
                    "riskAlerts": [{"area": "evals", "severity": "high", "message": "1 failing eval."}],
                    "explainFailurePrompts": [
                        "Why did the latest eval fail and which trace/tool call should I inspect?",
                        "Which skills are blocked from publishing?",
                    ],
                    "surfacePlaybook": [
                        {
                            "surface": "Capability Factory",
                            "status": "needs_work",
                            "evidence": {
                                "connectors": 3,
                                "typedTools": 2,
                                "entities": 4,
                                "benchmarkTasks": 7,
                                "approvedTrajectories": 3,
                                "skills": 4,
                                "proofReady": 1,
                                "proofBlocked": 1,
                                "replayContractReady": 1,
                                "replayContractBlocked": 1,
                            },
                        }
                    ],
                },
            },
        }
    )

    assert "Readiness is 60%" in reply
    assert "Studio OS gate: blocked, 2/5 surface(s) ready." in reply
    assert "First surface blocker: Capability Factory." in reply
    assert "Surface evidence: 3 connector(s), 2 typed tool(s), 4 entity record(s), 7 benchmark task(s), 3 approved trajectories, 4 skill(s), 1 proof-ready, 1 proof-blocked." in reply
    assert "Company Setup gate: partial, 2 system(s), 1 secret(s), 2 allowed domain(s)." in reply
    assert "First setup blocker: resource_acl." in reply
    assert "Factory pipeline: 1/3 connector(s) entity-mapped, 2 with typed tools, 1 with candidate tasks." in reply
    assert "Tool hardening: 3 hardened, 2 need policy/entity/risk hardening." in reply
    assert "First tool hardening gap: risk_policy." in reply
    assert "Send approval gate: blocked, 1/2 send tool(s) approval-covered." in reply
    assert "First uncovered send tool: gmail.send_email." in reply
    assert "Tool production gate: needs_hardening, 3/5 tool(s) hardened." in reply
    assert "Tool production checks: typed ready, contracts need hardening, policy/entity coverage blocked." in reply
    assert "Capability factory gate: blocked." in reply
    assert "Factory eval gate: blocked, 1/3 connector(s) regression-covered." in reply
    assert "Missing benchmark connector refs: 2." in reply
    assert "Factory blockers: 1 entity pending, 1 tool synthesis pending, 1 ingestion blocked." in reply
    assert "First factory blocker: ERP needs business entity mapping." in reply
    assert "Capability coverage: 2/5 task contracts ready, 1/4 skills hardened." in reply
    assert "Task replayability: 3/5 replay-ready." in reply
    assert "Entity mapping: 2/4 ready, 1 runtime-bindable, 2 with relationships." in reply
    assert "First entity blocker: read_access." in reply
    assert "Skill packages: 1/4 publishable, 2 with IO contracts, 1 with regressions, 1 with assets (1 resources, 1 scripts)." in reply
    assert "Skill releases: 1 published, 2 ready for publish, 1 draft." in reply
    assert "Skill lifecycle: 3/4 versioned, 2 with version history." in reply
    assert "Skill release gate: needs_hardening." in reply
    assert "Eval gates: 1 passing, 1 blocked, 2 missing regression." in reply
    assert "Eval coverage: connectors 2/3, entities 1/4, skills 2/5." in reply
    assert "First eval coverage blocker: 1 connector, 3 entities, 3 skills." in reply
    assert "Benchmark portfolio: 2 benchmark(s), 7 task(s), promotion gate blocked." in reply
    assert "Eval center gate: blocked, 3/7 replay-ready task(s)." in reply
    assert "Regression gate: 3/5 capabilities gated, state needs_regression." in reply
    assert "Judge strategy gate: needs_hardening, 4/7 deterministic, 6 stateful, 2 LLM-only." in reply
    assert "First judge hardening: Add deterministic checks or stateful replay so LLM judges remain complementary." in reply
    assert "Promotion pipeline: 4/7 tasks with trajectories, 3/5 trajectories approved, 2/4 skills trajectory-linked." in reply
    assert "Skill promotion gate: blocked." in reply
    assert "First skill promotion blocker: approvedTrajectoryLinked." in reply
    assert "Promotion data hygiene: 1 legacy pending trajectory row(s) should move to benchmark tasks." in reply
    assert "First promotion blocker: Some promoted skills are missing reusable package hardening." in reply
    assert "Vertical demos: 1/2 ready, 1 enterprise-ready, 1 smoke-ready, 1 proof-ready, 1 proof-blocked." in reply
    assert "Replay contracts: 1 ready, 1 blocked." in reply
    assert "Business output contracts: 1 ready, 1 blocked." in reply
    assert "First demo blocker: Capability factory." in reply
    assert "Insurance proof gate: needs_hardening, 7/9 proof step(s) ready." in reply
    assert "Runtime replay contract: needs_hardening, missing passing AgentRuntime replay." in reply
    assert "Replay evidence: 0 passing run(s), 1 promoted skill(s), 1 artifact(s), 1 approval boundary marker(s)." in reply
    assert "Business output contract: needs_hardening, artifact draft_email, delivery human_approval_before_send, missing passing replay asserting artifact and approval boundary." in reply
    assert "Business output evidence: 1 artifact(s), 1 approval boundary marker(s), 0 passing run(s)." in reply
    assert "First proof hardening: Replay the approved insurance skill in AgentRuntime before declaring the demo production-ready." in reply
    assert "First proof blocker: Runtime replay." in reply
    assert "Resource grounding: 2/3 indexed, 1/3 citable." in reply
    assert "Resource governance: 1/3 ACL-scoped, 2 read-tool-ready, 2 current." in reply
    assert "First resource read tool: knowledge.claims.search." in reply
    assert "Resource runtime gate: 1/3 ready, 2 blocked." in reply
    assert "First resource blocker: acl." in reply
    assert "Runtime policy: browser default exception, 1 browser sessions, write/send protected." in reply
    assert "Runtime taxonomy: default api_runtime, API-first yes, browser default exception." in reply
    assert "Runtime modes: api_runtime 2 cap/1 session(s), browser_runtime 1 cap/0 session(s), hybrid_runtime 1 cap/1 session(s)." in reply
    assert "Browser exception discipline: ready, 0 browser-only session(s), 2 API-first session(s)." in reply
    assert "Runtime class gate: needs_hardening." in reply
    assert "First runtime class blocker: browserDomainGoverned." in reply
    assert "Side-effect approvals: incomplete." in reply
    assert "Missing approval boundary: write." in reply
    assert "Browser domain governance: 1/2 observed domain(s) covered, 1 allowed." in reply
    assert "First uncovered browser domain: unknown.example.net." in reply
    assert "Runtime cost: 2.5 credits, 8.25s duration." in reply
    assert "Runtime timeline: 6 steps, 3 tool, 1 skill, 1 replay-ready sessions." in reply
    assert "Replay contracts: 1 ready, 1 blocked." in reply
    assert "Artifact outputs: 3 business output(s), 2 runtime-linked, 1 pending review." in reply
    assert "Artifact traceability: 3 separated from trace, 2 capability-linked, 1 work-linked, 1/2 reusable as knowledge." in reply
    assert "Business output delivery gate: blocked, 1/3 output(s) delivery-ready." in reply
    assert "Artifact reuse blocked: 1." in reply
    assert "Work attention items: 3." in reply
    assert "Work operations: 2 due trigger(s), 1 budget-exhausted item(s), 4 retry attempt(s)." in reply
    assert "Work contracts: 2/4 normalized, 3 SLA-tracked, 2 with audit trails." in reply
    assert "Work controls: 2 approval-gated, 1 browser-allowlisted, 5 run attempt(s)." in reply
    assert "Automation gate: 1 unattended-ready, 2 blocked." in reply
    assert "Work operations gate: blocked." in reply
    assert "First automation blocker: pending_approval." in reply
    assert "Automata sees 1 risk alert(s)." in reply
    assert "Ask Automata: Why did the latest eval fail and which trace/tool call should I inspect?" in reply
    assert "Next: Inspect failed traces before publishing." in reply


@pytest.mark.asyncio
async def test_assistant_executes_memory_rebuild_tool(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    rebuilds = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-memory",
                            "name": "studio_rebuild_assistant_memory",
                            "arguments": '{"limit": 100}',
                        }
                    ]
                )
            return _FakeResponse([], "Queued memory rebuild.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def get_assistant_memory(self):
            return {"exists": False, "summary": ""}

        async def rebuild_assistant_memory(self, limit=200):
            rebuilds.append(limit)
            return {"queued": True, "jobId": "job-1", "status": "queued", "limit": limit}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("summarize all conversations and give Automata past context")

    assert draft is None
    assert reply == "Queued memory rebuild."
    assert rebuilds == [100]
    assert any(event.get("toolName") == "studio_rebuild_assistant_memory" for event in events)


@pytest.mark.asyncio
async def test_assistant_executes_connector_action_tool(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []
    created = []

    class _FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _FakeResponse(
                    [
                        {
                            "type": "function_call",
                            "call_id": "call-create-connector",
                            "name": "studio_create_connector",
                            "arguments": '{"name":"BOPA","type":"api","config":{"docsUrl":"https://example.com/docs"}}',
                        }
                    ]
                )
            return _FakeResponse([], "Created connector BOPA.")

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def create_connector(self, **kwargs):
            created.append(kwargs)
            return {"success": True, "connector": {"connectorId": "connector-1", "name": kwargs["name"]}}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("create a BOPA API connector")

    assert draft is None
    assert reply == "Created connector BOPA."
    assert created == [
        {
            "name": "BOPA",
            "connector_type": "api",
            "category": "software",
            "description": "",
            "status": "not_connected",
            "config": {"docsUrl": "https://example.com/docs"},
            "provider": "",
            "auth_required": None,
        }
    ]
    assert any(event.get("toolName") == "studio_create_connector" for event in events)


@pytest.mark.asyncio
async def test_assistant_answers_active_company_name_without_llm(monkeypatch):
    from app.assistant import service as assistant_service

    class _FailOpenAI:
        def __init__(self, api_key):
            raise AssertionError("quick company lookup should not call OpenAI")

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_companies(self, limit=20):
            return [
                {"companyId": "company-1", "name": "Celeris"},
                {"companyId": "company-2", "name": "Amazon"},
            ][:limit]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FailOpenAI)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("which is current company name")

    assert draft is None
    assert 'Your active company is "Celeris".' in reply
    assert any(event.get("toolName") == "studio_list_companies" for event in events)


@pytest.mark.asyncio
async def test_assistant_routes_greetings_through_llm(monkeypatch):
    from app.assistant import service as assistant_service

    calls = []

    class _FakeResponse:
        output = []
        output_text = "Hello from the model."

    class _FakeResponses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return _FakeResponse()

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = _FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_service, "AsyncOpenAI", _FakeOpenAI)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("hello")

    assert draft is None
    assert reply == "Hello from the model."
    assert calls
    assert any(event.get("content") == "Thinking with Studio tools." for event in events)


@pytest.mark.asyncio
async def test_assistant_keeps_rule_fallback_without_openai_key(monkeypatch):
    from app.assistant import service as assistant_service

    class _Tools:
        def __init__(self, context):
            self.context = context

        async def list_connectors(self, limit=20):
            return [{"name": "Gmail", "status": "needs_auth"}]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    reply, events, draft = await service.respond("list my connectors")

    assert draft is None
    assert "Gmail" in reply
    assert any(event.get("toolName") == "studio.list_connectors" for event in events)


@pytest.mark.asyncio
async def test_assistant_message_inherits_conversation_company_scope(monkeypatch):
    from app.assistant import service as assistant_service

    seen_company_ids = []

    class _Tools:
        def __init__(self, context):
            seen_company_ids.append(context.company_id)

        async def studio_snapshot(self):
            return {
                "companies": [{"companyId": "company-1"}],
                "activeCompanyId": "company-1",
                "counts": {
                    "companies": 1,
                    "agents": 0,
                    "connectors": 0,
                    "credentials": 0,
                    "knowledgeDocuments": 0,
                    "skills": 0,
                    "tools": 0,
                    "benchmarkTasks": 0,
                    "workItems": 0,
                },
            }

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "mode": "studio_global",
            "companyId": "company-1",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)
    monkeypatch.setattr(assistant_service, "AutomataAssistantTools", _Tools)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com"))
    await service.send_message("conv-1", "summary")

    assert seen_company_ids == ["", "company-1"]
    assert collection.last_update["$set"]["companyId"] == "company-1"


@pytest.mark.asyncio
async def test_assistant_company_scoped_load_rejects_unscoped_conversation(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "mode": "studio_global",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))

    with pytest.raises(HTTPException) as exc:
        await service.get_conversation("conv-1")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assistant_company_scoped_load_rejects_other_company(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationCollection(
        {
            "conversationId": "conv-1",
            "email": "owner@example.com",
            "companyId": "company-2",
            "mode": "studio_global",
            "messages": [],
        }
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))

    with pytest.raises(HTTPException) as exc:
        await service.send_message("conv-1", "summary")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assistant_history_is_scoped_by_email_and_company(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationListCollection(
        [
            {
                "conversationId": "owned-1",
                "email": "owner@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Owned question"}],
                "updatedAt": "2026-01-01T00:00:00+00:00",
            },
            {
                "conversationId": "foreign-company",
                "email": "owner@example.com",
                "companyId": "company-2",
                "messages": [{"role": "user", "content": "Other company"}],
            },
            {
                "conversationId": "foreign-user",
                "email": "other@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Other user"}],
            },
        ]
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com", company_id="company-1"))
    history = await service.list_conversations()

    assert collection.last_find_query == {"email": "owner@example.com", "companyId": "company-1"}
    assert [item["conversationId"] for item in history] == ["owned-1"]
    assert history[0]["title"] == "Owned question"


@pytest.mark.asyncio
async def test_assistant_history_without_company_does_not_return_company_chats(monkeypatch):
    from app.assistant import service as assistant_service

    collection = _ConversationListCollection(
        [
            {
                "conversationId": "global-1",
                "email": "owner@example.com",
                "companyId": "",
                "messages": [{"role": "user", "content": "Global question"}],
                "updatedAt": "2026-01-01T00:00:00+00:00",
            },
            {
                "conversationId": "company-1",
                "email": "owner@example.com",
                "companyId": "company-1",
                "messages": [{"role": "user", "content": "Company question"}],
            },
        ]
    )
    monkeypatch.setattr(assistant_service, "assistant_conversations_collection", collection)

    service = AutomataAssistantService(AssistantContext(email="owner@example.com"))
    history = await service.list_conversations()

    assert collection.last_find_query == {"email": "owner@example.com", "companyId": ""}
    assert [item["conversationId"] for item in history] == ["global-1"]
