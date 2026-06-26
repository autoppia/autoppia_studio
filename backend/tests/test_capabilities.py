import pytest
from fastapi import HTTPException

from app.routes import capabilities


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, field, direction):
        reverse = direction < 0
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    async def to_list(self, length=500):
        return [dict(doc) for doc in self.docs[:length]]

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return _Result()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
        return _Result(matched_count=0)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in value):
                return False
            continue
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


@pytest.mark.asyncio
async def test_publish_official_connector_publishes_default_tools(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Cloudflare",
                    "type": "cloudflare",
                    "status": "connected",
                    "provider": "official",
                    "config": {},
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.publish_connector_tools("conn-1")

    assert result["success"] is True
    assert result["run"]["status"] == "completed"
    assert result["run"]["runKind"] == "tool_publication"
    assert result["run"]["harvesterType"] == "default_toolkit_publisher"
    assert {tool["name"] for tool in result["tools"]} >= {"cloudflare.search", "cloudflare.get"}
    assert {tool["source"] for tool in result["tools"]} == {"default_toolkit"}

    listed = await capabilities.list_company_capabilities("co-1")
    assert [item["capabilityKind"] for item in listed["capabilities"]] == ["tool", "tool", "tool", "tool"]


@pytest.mark.asyncio
async def test_update_tool_and_skill_approval_modes(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "tools_collection",
        _Collection(
            [
                {
                    "toolId": "tool-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "crm.update",
                    "permissions": {"connectorId": "conn-1"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Update CRM",
                    "permissions": {"connectorId": "conn-1"},
                }
            ]
        ),
    )

    tool = await capabilities.update_tool_approval(
        "tool-1",
        capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="never"),
    )
    skill = await capabilities.update_skill_approval(
        "skill-1",
        capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="always"),
    )

    assert tool["tool"]["permissions"]["approval"] == "never"
    assert skill["skill"]["permissions"]["approval"] == "always"


@pytest.mark.asyncio
async def test_tool_synthesis_contract_exposes_governed_action_readiness(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "ERP",
                    "type": "api",
                    "config": {},
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())

    result = await capabilities.create_company_tool(
        "co-1",
        capabilities.ToolCreateRequest(
            email="user@example.com",
            connectorId="conn-1",
            name="erp.update_claim",
            inputSchema={"type": "object", "properties": {"claimId": {"type": "string"}}},
            outputSchema={"type": "object", "properties": {"status": {"type": "string"}}},
            sideEffects="writes",
            permissions={"approval": "always", "scopes": ["claims:write"]},
            riskLevel="high",
            inputEntities=["Claim"],
            outputEntity="Claim",
        ),
    )

    synthesis = result["tool"]["toolSynthesis"]
    assert synthesis["atomic"] is True
    assert synthesis["typedInput"] is True
    assert synthesis["typedOutput"] is True
    assert synthesis["riskClassification"]["requiresApproval"] is True
    assert synthesis["permissions"]["scopes"] == ["claims:write"]
    assert synthesis["entityBindings"]["declared"] is True
    assert synthesis["readiness"]["status"] == "ready"
    assert synthesis["readiness"]["gaps"] == []


@pytest.mark.asyncio
async def test_company_capability_graph_links_factory_assets(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {"connectorId": "conn-1", "companyId": "co-1", "email": "user@example.com", "name": "Claims ERP", "type": "api", "status": "connected"},
                {"connectorId": "knowledge-1", "companyId": "co-1", "email": "user@example.com", "name": "Claims Knowledge", "type": "knowledge", "status": "connected"},
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "entities_collection",
        _Collection([{"entityId": "entity-claim", "companyId": "co-1", "email": "user@example.com", "name": "Claim", "sourceConnectorId": "conn-1"}]),
    )
    monkeypatch.setattr(
        capabilities,
        "tools_collection",
        _Collection(
            [
                {
                    "toolId": "tool-claim",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "connectorId": "conn-1",
                    "name": "claims.get",
                    "status": "ready",
                    "inputSchema": {"type": "object", "properties": {"claimId": {"type": "string"}}},
                    "outputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
                    "sideEffects": "writes",
                    "permissions": {"approval": "always"},
                    "riskLevel": "high",
                    "inputEntities": ["Claim"],
                    "outputEntity": "Claim",
                    "toolContract": {"format": "autoppia.tool_contract"},
                },
                {
                    "toolId": "tool-knowledge",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "connectorId": "knowledge-1",
                    "name": "knowledge.claims.search",
                    "status": "ready",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "outputSchema": {"type": "object", "properties": {"citations": {"type": "array"}}},
                    "sideEffects": "reads",
                    "riskLevel": "low",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "vector_databases_collection",
        _Collection(
            [
                {
                    "vectorDatabaseId": "vector-claims",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Claims Knowledge",
                    "collectionName": "claims-knowledge",
                    "connectorId": "knowledge-1",
                    "status": "ready",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "knowledge_documents_collection",
        _Collection(
            [
                {
                    "documentId": "doc-claims",
                    "resourceId": "resource-claims",
                    "resourceKind": "document",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "filename": "claims-handbook.md",
                    "status": "indexed",
                    "connectorId": "knowledge-1",
                    "vectorDatabaseId": "vector-claims",
                    "resourceContract": {
                        "resourceId": "resource-claims",
                        "resourceKind": "document",
                        "surface": "knowledge_resource",
                        "readOnly": True,
                        "indexing": {"indexed": True, "vectorDatabaseId": "vector-claims", "vectorCollectionName": "claims-knowledge"},
                        "governance": {"citability": {"citable": True, "citationLabel": "claims-handbook.md"}},
                        "readTools": ["knowledge.claims.search"],
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "benchmarks_collection",
        _Collection(
            [
                {
                    "benchmarkId": "bench-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Claims Benchmark",
                    "status": "draft",
                    "metadata": {
                        "vertical": "insurance",
                        "verticalDemo": {
                            "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
                            "runtimePath": "hybrid_api_first",
                            "coverage": [
                                {"key": "email_read", "label": "Email read", "evidence": "imap.search_emails"},
                                {"key": "erp_lookup", "label": "ERP lookup", "evidence": "erp.search_claims"},
                                {"key": "document_grounding", "label": "Document grounding", "evidence": "knowledge.search"},
                                {"key": "draft_artifact", "label": "Draft artifact", "evidence": "draft_email artifact"},
                                {"key": "approval_boundary", "label": "Approval boundary", "evidence": "smtp.send_email approval"},
                                {"key": "benchmark", "label": "Benchmark", "evidence": "tasks"},
                                {"key": "trajectory", "label": "Trajectory", "evidence": "approved trajectory"},
                                {"key": "skill_promotion", "label": "Skill promotion", "evidence": "published skill"},
                                {"key": "runtime_replay", "label": "Runtime replay", "evidence": "passing eval run"},
                            ],
                        },
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "benchmark_tasks_collection",
        _Collection(
            [
                {
                    "taskId": "task-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "name": "Review claim",
                    "status": "harvested",
                    "trajectoryId": "traj-1",
                    "businessIntent": "Review claim status",
                    "allowedSystems": ["email", "insurance_erp", "knowledge"],
                    "expectedArtifacts": ["claim_summary", "draft_email"],
                    "riskClass": "send",
                    "successCriteria": "Claim status is summarized without changing the claim",
                    "metadata": {
                        "expectedTools": ["imap.search_emails", "erp.search_claims", "knowledge.search", "smtp.draft_email", "smtp.send_email"],
                        "taskContract": {
                            "businessIntent": "Review claim status",
                            "allowedSystems": ["email", "insurance_erp", "knowledge"],
                            "expectedArtifacts": ["claim_summary", "draft_email"],
                            "riskClass": "send",
                            "successCriteria": "Claim status is summarized without changing the claim",
                            "initialState": {"approvalBoundary": "send_requires_approval"},
                        }
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "taskId": "task-1",
                    "taskName": "Review claim",
                    "status": "approved",
                    "connectorIds": ["conn-1"],
                    "toolIds": ["tool-claim", "knowledge.claims.search"],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection(
            [
                {
                    "runId": "eval-run-1",
                    "benchmarkRunId": "bench-run-1",
                    "evalId": "task-1",
                    "benchmarkId": "bench-1",
                    "email": "user@example.com",
                    "agentTaskName": "Review claim",
                    "sessionId": "session-1",
                    "label": "pass",
                    "judgeType": "rules",
                    "labelSource": "stateful_evaluator",
                    "createdAt": "2026-06-25T10:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Review claim skill",
                    "status": "published",
                    "promotionStatus": "published",
                    "benchmarkId": "bench-1",
                    "evalId": "task-1",
                    "trajectoryIds": ["traj-1"],
                    "toolIds": ["tool-claim", "knowledge.claims.search"],
                    "inputEntities": ["Claim"],
                    "outputEntity": "Claim",
                    "riskPolicy": "human_approval_for_writes",
                    "whenToUse": "Use when reviewing a claim status request.",
                    "instructions": "Look up claim state and prepare a concise summary.",
                    "expectedArtifacts": ["claim_summary"],
                    "preconditions": ["Customer identity verified"],
                    "version": 2,
                    "versionHistory": [
                        {"version": 1, "promotionStatus": "ready", "reason": "initial", "createdAt": "t-1"},
                        {"version": 2, "promotionStatus": "published", "reason": "promoted", "createdAt": "t-2"},
                    ],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "sessions_collection",
        _Collection(
            [
                {
                    "sessionId": "session-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "prompt": "Review claim status",
                    "runtimeState": {
                        "runtimeKind": "api_runtime",
                        "matchedSkillId": "skill-1",
                        "trajectoryId": "traj-1",
                        "toolIds": ["tool-claim", "tool-knowledge"],
                    },
                    "sessionContract": {
                        "agentRuntime": {"runtimeKind": "api", "sourceKind": "eval", "runId": "run-1"},
                        "selectedSkill": {"matched": True, "skillId": "skill-1", "skillName": "Resolve claim"},
                        "approvalState": {"pending": 1, "requiredFor": ["send"], "hasHumanBoundary": True},
                        "artifactState": {"count": 1, "hasBusinessOutput": True},
                        "costState": {"creditsSpent": 1.75},
                        "traceState": {"traceIds": ["trace-1"], "replayReady": True},
                    },
                    "traceIds": ["trace-1"],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "approvals_collection",
        _Collection(
            [
                {
                    "approvalId": "approval-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "sessionId": "session-1",
                    "status": "pending",
                    "approvalKey": "claim.write",
                    "title": "Confirm claim update",
                    "metadata": {"skillId": "skill-1", "trajectoryId": "traj-1", "toolId": "tool-claim"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "artifacts_collection",
        _Collection(
            [
                {
                    "artifactId": "artifact-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "sessionId": "session-1",
                    "title": "Claim summary",
                    "artifactType": "markdown",
                    "metadata": {"skillId": "skill-1", "trajectoryId": "traj-1", "toolId": "tool-claim"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "work_items_collection",
        _Collection(
            [
                {
                    "workItemId": "work-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "title": "Daily claim review",
                    "status": "REVIEW",
                    "triggerType": "scheduled",
                    "scheduleFrequency": "daily",
                    "browserEnabled": True,
                    "browserRestrictedByDomain": True,
                    "allowedDomains": ["claims.example.com"],
                    "sourceBenchmarkId": "bench-1",
                    "sourceTaskId": "task-1",
                    "currentSessionId": "session-1",
                    "runHistory": [{"runId": "run-1", "status": "WAITING_APPROVAL"}],
                    "operational": {
                        "latestMatchedSkillIds": ["skill-1"],
                        "latestMatchedTrajectoryIds": ["traj-1"],
                        "latestToolIds": ["tool-claim"],
                        "latestSessionIds": ["session-1"],
                        "reviewBlocked": True,
                        "pendingApprovalCount": 1,
                        "orchestration": {
                            "queueState": "REVIEW",
                            "triggerType": "scheduled",
                            "schedule": {"deadlineState": "upcoming", "dueAt": "2026-06-26T12:00:00+00:00"},
                            "budget": {"maxBudgetCredits": 5.0, "latestCreditsSpent": 1.75, "remainingCredits": 3.25, "exhausted": False},
                            "retry": {"runAttempts": 1, "maxSteps": 8},
                            "approval": {"reviewBlocked": True, "pendingApprovalCount": 1},
                            "sla": {"state": "blocked", "deadlineState": "upcoming", "needsAttention": True},
                            "automationGate": {"state": "blocked", "canRunUnattended": False, "blockers": ["pending_approval"]},
                            "browserPolicy": {"state": "restricted", "enabled": True, "allowedDomains": ["claims.example.com"]},
                            "auditTrail": {"uniform": True, "eventCount": 4, "hasApprovalCheckpoint": True, "hasBudgetCheckpoint": True},
                        },
                    },
                }
            ]
        ),
    )

    result = await capabilities.get_company_capability_graph("co-1", email="user@example.com")
    graph = result["graph"]
    node_ids = {node["id"] for node in graph["nodes"]}
    edge_relations = {edge["relation"] for edge in graph["edges"]}
    task_node = next(node for node in graph["nodes"] if node["id"] == "task:task-1")

    assert {"connector:conn-1", "connector:knowledge-1", "entity:entity-claim", "resource:resource-claims", "vector_store:vector-claims", "tool:tool-claim", "tool:tool-knowledge", "policy_boundary:write", "approval_mode:always", "approval_mode:auto", "browser_policy:domain_restricted", "benchmark:bench-1", "vertical_demo:bench-1:vertical_demo", "task:task-1", "trajectory:traj-1", "skill:skill-1"} <= node_ids
    assert {"eval_run:eval-run-1", "session:session-1", "approval:approval-1", "artifact:artifact-1", "work_item:work-1"} <= node_ids
    assert {"exposes_tool", "maps_entity", "contains_task", "produced_trajectory", "used_in_trajectory", "promoted_to", "used_by_skill"} <= edge_relations
    assert {"backs_vector_store", "indexes_resource", "grounds_connector", "read_by_tool", "grounds_task"} <= edge_relations
    assert {"has_regression_run", "evaluated_by_run", "gates_skill", "replayed_session"} <= edge_relations
    assert {"validates_vertical_demo", "covers_demo_step", "implements_demo_capability", "proves_demo_replay"} <= edge_relations
    assert {"governed_by_boundary", "uses_approval_mode", "requires_write_approval", "requires_send_approval", "uses_browser_policy", "requires_browser_sandbox", "restricted_to_domains"} <= edge_relations
    assert {"exercised_skill", "exercised_trajectory", "exercised_tool", "requested_approval", "requires_approval", "created_artifact", "produced_artifact"} <= edge_relations
    assert {"scheduled_from_benchmark", "scheduled_from_task", "opened_session", "orchestrates_skill", "orchestrates_trajectory", "orchestrates_tool"} <= edge_relations
    assert task_node["payload"]["taskContract"]["allowedSystems"] == ["email", "insurance_erp", "knowledge"]
    assert task_node["payload"]["taskContract"]["expectedArtifacts"] == ["claim_summary", "draft_email"]
    assert task_node["payload"]["successCriteria"] == "Claim status is summarized without changing the claim"
    assert graph["coverage"]["tools"]["governed"] == 1
    assert graph["coverage"]["policies"]["writeCapabilities"] >= 1
    assert graph["coverage"]["policies"]["writesProtected"] is True
    assert graph["coverage"]["policies"]["sendProtected"] is True
    assert graph["coverage"]["policies"]["browserCapabilities"] == 1
    assert graph["coverage"]["policies"]["browserSandboxed"] is True
    assert graph["coverage"]["policies"]["domainRestricted"] is True
    assert graph["coverage"]["policies"]["highRiskTools"] == 1
    assert {"always", "auto"} <= set(graph["coverage"]["policies"]["approvalModes"])
    assert graph["coverage"]["resources"]["total"] == 1
    assert graph["coverage"]["resources"]["indexed"] == 1
    assert graph["coverage"]["resources"]["citable"] == 1
    assert graph["coverage"]["resources"]["withResourceContract"] == 1
    assert graph["coverage"]["resources"]["withReadTools"] == 1
    assert graph["coverage"]["resources"]["vectorStores"] == 1
    assert graph["coverage"]["resources"]["linkedVectorStores"] == 1
    assert graph["coverage"]["resources"]["linkedToConnectors"] is True
    assert graph["coverage"]["resources"]["linkedToTools"] is True
    assert graph["coverage"]["resources"]["linkedToTasks"] is True
    assert graph["coverage"]["benchmarks"]["tasksWithContracts"] == 1
    assert graph["coverage"]["verticalDemos"]["total"] == 1
    assert graph["coverage"]["verticalDemos"]["ready"] == 1
    assert graph["coverage"]["verticalDemos"]["runtimeReplayReady"] == 1
    assert graph["coverage"]["verticalDemos"]["linkedToBenchmarks"] is True
    assert graph["coverage"]["evals"]["runs"] == 1
    assert graph["coverage"]["evals"]["pass"] == 1
    assert graph["coverage"]["evals"]["fail"] == 0
    assert graph["coverage"]["evals"]["linkedToTasks"] is True
    assert graph["coverage"]["evals"]["linkedToSkills"] is True
    assert graph["coverage"]["evals"]["linkedToRuntime"] is True
    assert graph["coverage"]["skills"]["ready"] == 1
    assert graph["coverage"]["skills"]["reusable"] == 1
    assert graph["coverage"]["skills"]["packages"]["manifestReady"] == 1
    assert graph["coverage"]["skills"]["packages"]["activation"] == 1
    assert graph["coverage"]["skills"]["packages"]["instructions"] == 1
    assert graph["coverage"]["skills"]["packages"]["ioContracts"] == 1
    assert graph["coverage"]["skills"]["packages"]["expectedArtifacts"] == 1
    assert graph["coverage"]["skills"]["packages"]["riskPolicies"] == 1
    assert graph["coverage"]["skills"]["packages"]["sourceTrajectories"] == 1
    assert graph["coverage"]["skills"]["packages"]["regressionSuites"] == 1
    assert graph["coverage"]["skills"]["packages"]["publishable"] == 1
    assert graph["coverage"]["skills"]["packages"]["versioned"] == 1
    assert graph["coverage"]["skills"]["packages"]["releaseStatus"] == [{"name": "published", "count": 1}]
    assert graph["coverage"]["skills"]["packages"]["releaseReadiness"]["published"] == 1
    assert graph["coverage"]["skills"]["packages"]["releaseReadiness"]["readyForPublish"] == 1
    assert graph["coverage"]["skills"]["packages"]["releaseReadiness"]["withVersionHistory"] == 1
    assert graph["coverage"]["runtime"]["sessions"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["withContract"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["selectedSkill"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["pendingApprovals"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["artifactOutputs"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["traceIds"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["replayReady"] == 1
    assert graph["coverage"]["runtime"]["sessionContracts"]["creditsSpent"] == 1.75
    assert graph["coverage"]["runtime"]["approvals"] == 1
    assert graph["coverage"]["runtime"]["pendingApprovals"] == 1
    assert graph["coverage"]["runtime"]["artifacts"] == 1
    assert graph["coverage"]["runtime"]["linkedSessions"] is True
    assert graph["coverage"]["runtime"]["linkedApprovals"] is True
    assert graph["coverage"]["runtime"]["linkedArtifacts"] is True
    assert graph["coverage"]["work"]["total"] == 1
    assert graph["coverage"]["work"]["scheduled"] == 1
    assert graph["coverage"]["work"]["review"] == 1
    assert graph["coverage"]["work"]["blockedByApproval"] == 1
    assert graph["coverage"]["work"]["orchestration"]["withContract"] == 1
    assert graph["coverage"]["work"]["orchestration"]["scheduled"] == 1
    assert graph["coverage"]["work"]["orchestration"]["budgeted"] == 1
    assert graph["coverage"]["work"]["orchestration"]["budgetExhausted"] == 0
    assert graph["coverage"]["work"]["orchestration"]["retryConfigured"] == 1
    assert graph["coverage"]["work"]["orchestration"]["runAttempts"] == 1
    assert graph["coverage"]["work"]["orchestration"]["slaTracked"] == 1
    assert graph["coverage"]["work"]["orchestration"]["slaNeedsAttention"] == 1
    assert graph["coverage"]["work"]["orchestration"]["approvalGates"] == 1
    assert graph["coverage"]["work"]["orchestration"]["auditTrails"] == 1
    assert graph["coverage"]["work"]["orchestration"]["browserPolicies"] == 1
    assert graph["coverage"]["work"]["orchestration"]["browserAllowlists"] == 1
    assert graph["coverage"]["work"]["orchestration"]["unattendedReady"] == 0
    assert graph["coverage"]["work"]["orchestration"]["unattendedBlocked"] == 1
    assert graph["coverage"]["work"]["orchestration"]["automationBlockers"] == [{"name": "pending_approval", "count": 1}]
    assert graph["coverage"]["work"]["linkedToTasks"] is True
    assert graph["coverage"]["work"]["linkedToRuntime"] is True
    assert graph["coverage"]["work"]["linkedToCapabilities"] is True
    assert graph["coverage"]["promotionPath"]["hasTaskToTrajectory"] is True
    assert graph["coverage"]["promotionPath"]["hasTrajectoryToSkill"] is True


@pytest.mark.asyncio
async def test_update_company_skill_hardening_recomputes_lineage(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection([{"runId": "run-1", "evalId": "eval-2", "label": "pass", "createdAt": "2026-06-25T10:00:00+00:00"}]),
    )
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "benchmark_tasks_collection",
        _Collection(
            [
                {
                    "taskId": "task-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-1",
                    "name": "Find renewal status",
                    "businessIntent": "Confirm policy renewal state",
                    "successCriteria": "Policy renewal state is reflected in the draft",
                    "riskClass": "medium",
                    "metadata": {
                        "taskContract": {
                            "expectedInputs": ["policy_id"],
                            "expectedArtifacts": ["draft_email"],
                            "allowedSystems": ["crm", "erp"],
                        }
                    },
                },
                {
                    "taskId": "task-2",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-2",
                    "name": "Draft renewal email",
                    "successCriteria": "Draft email is prepared but not sent",
                    "metadata": {
                        "taskContract": {
                            "businessIntent": "Prepare customer-facing renewal response",
                            "expectedInputs": ["customer_email", "policy_id"],
                            "expectedArtifacts": ["draft_email", "renewal_summary"],
                            "allowedSystems": ["email", "erp"],
                            "riskClass": "high",
                            "successCriteria": "Draft email is prepared but not sent",
                        }
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                    "taskId": "task-1",
                    "taskName": "Find renewal status",
                    "connectorIds": ["conn-1"],
                    "toolIds": ["crm.search"],
                    "runtimeRequirements": ["network"],
                    "steps": [{"action": "crm.search"}],
                    "judge": {"label": "pass"},
                },
                {
                    "trajectoryId": "traj-2",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-2",
                    "evalId": "eval-2",
                    "taskId": "task-2",
                    "taskName": "Draft renewal email",
                    "connectorIds": ["conn-2"],
                    "toolIds": ["erp.update"],
                    "runtimeRequirements": ["browser"],
                    "steps": [{"action": "erp.update"}, {"action": "smtp.draft_email"}],
                    "judge": {"label": "pass"},
                },
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "description": "Old description",
                    "whenToUse": "Old when-to-use",
                    "riskPolicy": "human_approval_for_writes",
                    "status": "ready",
                    "trajectoryIds": ["traj-1"],
                    "connectorIds": ["conn-1"],
                    "toolIds": ["crm.search"],
                    "runtimeRequirements": ["network"],
                }
            ]
        ),
    )

    result = await capabilities.update_company_skill(
        "skill-1",
        capabilities.SkillUpdateRequest(
            email="user@example.com",
            name="Hardened renewal workflow",
            description="Reusable renewal workflow",
            whenToUse="Use for customer renewal follow-up",
            instructions="Look up the policy, confirm renewal state, draft the response and stop before sending.",
            preconditions=["Customer identity verified", "Policy number available"],
            expectedArtifacts=["draft_email", "renewal_summary"],
            riskPolicy="human_approval_always",
            status="published",
            inputEntities=["Customer", "Policy"],
            outputEntity="Draft email",
            trajectoryIds=["traj-1", "traj-2"],
        ),
    )

    skill = result["skill"]
    assert skill["name"] == "Hardened renewal workflow"
    assert skill["riskPolicy"] == "human_approval_always"
    assert skill["status"] == "published"
    assert skill["promotionStatus"] == "published"
    assert skill["version"] == 2
    assert skill["versionLabel"] == "v2"
    assert skill["publishedAt"]
    assert [event["version"] for event in skill["versionHistory"]] == [1, 2]
    assert skill["versionHistory"][-1]["promotionStatus"] == "published"
    assert skill["versionHistory"][-1]["reason"] == "promotion_status_change"
    assert skill["trajectoryIds"] == ["traj-1", "traj-2"]
    assert skill["connectorIds"] == ["conn-1", "conn-2"]
    assert skill["toolIds"] == ["crm.search", "erp.update"]
    assert skill["runtimeRequirements"] == ["network", "browser"]
    assert skill["runtimePolicy"]["policy"] == "human_approval_always"
    assert skill["runtimePolicy"]["approvalMode"] == "always"
    assert skill["runtimePolicy"]["approvalRequiredFor"] == ["read", "draft", "write", "send"]
    assert skill["runtimePolicy"]["runtimeClass"] == "hybrid"
    assert skill["runtimePolicy"]["runtimeType"] == "hybrid_runtime"
    assert skill["runtimePolicy"]["runtimeTypes"] == ["api_runtime", "browser_runtime", "hybrid_runtime"]
    assert skill["runtimePolicy"]["browserRuntime"] is True
    assert skill["runtimePolicy"]["browserPolicy"]["defaultUse"] == "exception"
    assert skill["runtimePolicy"]["browserPolicy"]["requiresSandbox"] is True
    assert skill["benchmarkId"] == "bench-1"
    assert skill["evalId"] == "eval-1"
    assert skill["instructions"].startswith("Look up the policy")
    assert skill["preconditions"] == ["Customer identity verified", "Policy number available"]
    assert skill["expectedArtifacts"] == ["draft_email", "renewal_summary"]
    assert skill["lineage"]["trajectoryIds"] == ["traj-1", "traj-2"]
    assert skill["lineage"]["benchmarkIds"] == ["bench-1", "bench-2"]
    assert skill["lineage"]["evalIds"] == ["eval-1", "eval-2"]
    assert skill["latestRegression"]["runId"] == "run-1"
    assert skill["latestRegression"]["label"] == "pass"
    assert skill["hardeningStatus"]["checks"]["instructions"] is True
    assert skill["hardeningStatus"]["checks"]["publishableRegression"] is True
    assert skill["hardeningStatus"]["state"] == "hardened"
    assert skill["skillPackage"]["format"] == "autoppia.agent_skill"
    assert skill["skillPackage"]["metadata"]["versionLabel"] == "v2"
    assert skill["skillPackage"]["activation"]["description"] == "Use for customer renewal follow-up"
    assert skill["skillPackage"]["interface"]["expectedArtifacts"] == ["draft_email", "renewal_summary"]
    assert skill["skillPackage"]["ioContract"]["declared"] is True
    assert skill["skillPackage"]["ioContract"]["inputs"]["entities"] == ["Customer", "Policy"]
    assert skill["skillPackage"]["ioContract"]["inputs"]["preconditions"] == ["Customer identity verified", "Policy number available"]
    assert skill["skillPackage"]["ioContract"]["outputs"]["entity"] == "Draft email"
    assert skill["skillPackage"]["ioContract"]["outputs"]["artifacts"] == ["draft_email", "renewal_summary"]
    assert skill["skillPackage"]["interface"]["ioContract"]["declared"] is True
    assert skill["skillPackage"]["execution"]["trajectoryIds"] == ["traj-1", "traj-2"]
    assert skill["skillPackage"]["policies"]["runtimePolicy"]["runtimeClass"] == "hybrid"
    assert skill["skillPackage"]["policies"]["runtimePolicy"]["runtimeType"] == "hybrid_runtime"
    assert skill["skillPackage"]["productionGate"]["state"] == "publishable"
    assert skill["skillPackage"]["productionGate"]["canPublish"] is True
    assert skill["skillPackage"]["productionGate"]["blockers"] == []
    assert skill["skillPackage"]["productionGate"]["checks"]["ioContract"] is True
    assert skill["skillPackage"]["productionGate"]["checks"]["publishableRegression"] is True
    assert skill["skillPackage"]["evidence"]["sourceTrajectories"][0]["trajectoryId"] == "traj-1"
    assert skill["skillPackage"]["evidence"]["sourceTrajectories"][0]["actionCount"] == 1
    assert skill["skillPackage"]["evidence"]["sourceTrajectories"][1]["toolIds"] == ["erp.update"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["publishable"] is True
    assert [case["taskId"] for case in skill["skillPackage"]["evidence"]["regressionSuite"]["cases"]] == ["task-1", "task-2"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["cases"][0]["expectedInputs"] == ["policy_id"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["cases"][1]["expectedInputs"] == ["customer_email", "policy_id"]
    assert skill["skillPackage"]["evidence"]["regressionSuite"]["cases"][1]["expectedArtifacts"] == ["draft_email", "renewal_summary"]
    assert skill["skillPackage"]["evidence"]["versionHistory"][-1]["versionLabel"] == "v2"


@pytest.mark.asyncio
async def test_publish_skill_requires_latest_passing_benchmark(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection([{"runId": "run-1", "evalId": "eval-1", "label": "fail", "createdAt": "2026-06-25T12:00:00+00:00"}]),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_company_skill(
            "skill-1",
            capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
        )

    assert exc.value.status_code == 400
    assert "latest benchmark run is fail" in exc.value.detail


@pytest.mark.asyncio
async def test_publish_skill_requires_any_benchmark_evidence(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "eval_runs_collection", _Collection([]))

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_company_skill(
            "skill-1",
            capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
        )

    assert exc.value.status_code == 400
    assert "without benchmark evidence" in exc.value.detail


@pytest.mark.asyncio
async def test_publish_skill_allows_latest_passing_benchmark(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "whenToUse": "Use for renewal follow-up",
                    "instructions": "Look up the policy, draft a customer response, and stop before sending.",
                    "riskPolicy": "human_approval_for_writes",
                    "preconditions": ["Customer identity verified"],
                    "expectedArtifacts": ["draft_email"],
                    "inputEntities": ["Customer", "Policy"],
                    "outputEntity": "Draft email",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                    "trajectoryIds": ["traj-1"],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                    "connectorIds": ["conn-1"],
                    "toolIds": ["crm.search"],
                    "runtimeRequirements": ["network"],
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection(
            [
                {"runId": "run-older", "evalId": "eval-1", "label": "fail", "createdAt": "2026-06-24T12:00:00+00:00"},
                {"runId": "run-latest", "evalId": "eval-1", "label": "pass", "createdAt": "2026-06-25T12:00:00+00:00"},
            ]
        ),
    )

    result = await capabilities.update_company_skill(
        "skill-1",
        capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
    )

    assert result["skill"]["status"] == "published"
    assert result["skill"]["promotionStatus"] == "published"
    assert result["skill"]["version"] == 2
    assert result["skill"]["versionLabel"] == "v2"
    assert result["skill"]["publishedAt"]
    assert result["skill"]["versionHistory"][-1]["reason"] == "promotion_status_change"
    assert result["skill"]["hardeningStatus"]["state"] == "hardened"


@pytest.mark.asyncio
async def test_publish_skill_requires_hardening_after_passing_regression(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "capabilities_collection",
        _Collection(
            [
                {
                    "capabilityId": "skill-1",
                    "capabilityKind": "skill",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Handle renewal",
                    "status": "ready",
                    "benchmarkId": "bench-1",
                    "evalId": "eval-1",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "eval_runs_collection",
        _Collection([{"runId": "run-1", "evalId": "eval-1", "label": "pass", "createdAt": "2026-06-25T12:00:00+00:00"}]),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_company_skill(
            "skill-1",
            capabilities.SkillUpdateRequest(email="user@example.com", status="published"),
        )

    assert exc.value.status_code == 400
    assert "hardening is complete" in exc.value.detail
    assert "activation" in exc.value.detail
    assert "sourceTrajectory" in exc.value.detail


@pytest.mark.asyncio
async def test_update_approval_rejects_invalid_mode(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "tools_collection",
        _Collection([{"toolId": "tool-1", "email": "user@example.com", "companyId": "co-1", "name": "crm.update"}]),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.update_tool_approval(
            "tool-1",
            capabilities.CapabilityApprovalUpdateRequest(email="user@example.com", approval="sometimes"),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_official_connector_rejects_harvester(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Cloudflare",
                    "type": "cloudflare",
                    "status": "connected",
                    "provider": "official",
                    "config": {},
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.harvest_connector("conn-1")

    assert exc.value.status_code == 400
    assert "default tools" in exc.value.detail


@pytest.mark.asyncio
async def test_custom_api_connector_uses_harvester(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector("conn-1")

    assert result["success"] is True
    assert result["run"]["runKind"] == "harvester"
    assert result["run"]["harvesterType"] == "api_harvester"
    assert all(tool["source"] == "harvested_toolkit" for tool in result["tools"])


@pytest.mark.asyncio
async def test_custom_api_benchmark_harvest_generates_tools_and_skills(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Create a new CRM lead",
                    "successCriteria": "Lead exists",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector_benchmark(
        "conn-1",
        capabilities.ConnectorBenchmarkHarvestRequest(benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["run"]["runKind"] == "benchmark_harvester"
    assert result["run"]["discoveredTools"] > 0
    assert result["run"]["generatedSkills"] == 1
    assert result["skills"][0]["status"] == "draft"
    assert result["skills"][0]["promotionStatus"] == "draft"
    assert result["skills"][0]["version"] == 1
    assert result["skills"][0]["trajectoryIds"] == ["conn-1:ev-1:trajectory"]


@pytest.mark.asyncio
async def test_company_capabilities_harvest_is_canonical_endpoint(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"openApiUrl": "https://example.com/openapi.json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Create a new CRM lead",
                    "successCriteria": "Lead exists",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_company_capabilities(
        "co-1",
        capabilities.CompanyCapabilityHarvestRequest(connectorId="conn-1", benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["run"]["runKind"] == "benchmark_harvester"
    assert result["run"]["generatedSkills"] == 1


@pytest.mark.asyncio
async def test_company_capabilities_harvest_rejects_connector_from_other_company(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-2",
                    "email": "user@example.com",
                    "name": "Private CRM",
                    "type": "api",
                    "status": "connected",
                    "provider": "custom",
                    "config": {},
                }
            ]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await capabilities.harvest_company_capabilities(
            "co-1",
            capabilities.CompanyCapabilityHarvestRequest(connectorId="conn-1", benchmarkId="bench-1"),
        )

    assert exc.value.status_code == 400
    assert "does not belong" in exc.value.detail


@pytest.mark.asyncio
async def test_custom_web_benchmark_harvest_generates_skills_without_tools(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(
        capabilities,
        "connectors_collection",
        _Collection(
            [
                {
                    "connectorId": "conn-1",
                    "companyId": "co-1",
                    "email": "user@example.com",
                    "name": "BOPA Portal",
                    "type": "web",
                    "status": "connected",
                    "provider": "custom",
                    "config": {"startUrl": "https://www.bopa.ad/"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        capabilities,
        "evals_collection",
        _Collection(
            [
                {
                    "evalId": "ev-1",
                    "email": "user@example.com",
                    "benchmarkId": "bench-1",
                    "prompt": "Find the latest BOPA notice",
                    "successCriteria": "Notice is summarized",
                    "createdAt": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "trajectories_collection", _Collection())
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.harvest_connector_benchmark(
        "conn-1",
        capabilities.ConnectorBenchmarkHarvestRequest(benchmarkId="bench-1"),
    )

    assert result["success"] is True
    assert result["tools"] == []
    assert result["run"]["generatedSkills"] == 1
    assert result["skills"][0]["status"] == "needs_harvest"
    assert result["skills"][0]["promotionStatus"] == "draft"
    assert result["skills"][0]["version"] == 1
    assert result["skills"][0]["runtime"] == "web_trajectory_harvester"


@pytest.mark.asyncio
async def test_promote_company_trajectory_to_skill(monkeypatch):
    monkeypatch.setattr(capabilities, "companies_collection", _Collection([{"companyId": "co-1"}]))
    monkeypatch.setattr(capabilities, "tools_collection", _Collection())
    monkeypatch.setattr(capabilities, "harvester_runs_collection", _Collection())
    monkeypatch.setattr(capabilities, "eval_runs_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "evals_collection", _Collection([]))
    monkeypatch.setattr(capabilities, "benchmark_tasks_collection", _Collection([]))
    monkeypatch.setattr(
        capabilities,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-1",
                    "email": "user@example.com",
                    "companyId": "co-1",
                    "name": "Send latest invoice",
                    "intent": "Send the latest invoice to a client",
                    "connectorIds": ["gmail", "holded"],
                    "toolIds": ["holded.get_invoice", "gmail.send_email"],
                    "steps": [],
                    "status": "approved",
                }
            ]
        ),
    )
    monkeypatch.setattr(capabilities, "capabilities_collection", _Collection())

    result = await capabilities.promote_trajectory_to_skill(
        "traj-1",
        capabilities.PromoteTrajectoryRequest(
            email="user@example.com",
            instructions="Fetch the latest invoice, draft the email and stop before sending.",
            preconditions=["Customer email exists"],
            expectedArtifacts=["draft_email"],
        ),
    )

    assert result["success"] is True
    assert result["skill"]["capabilityKind"] == "skill"
    assert result["skill"]["name"] == "Send latest invoice"
    assert result["skill"]["promotionStatus"] == "ready"
    assert result["skill"]["version"] == 1
    assert result["skill"]["versionLabel"] == "v1"
    assert result["skill"]["readyAt"]
    assert result["skill"]["instructions"].startswith("Fetch the latest invoice")
    assert result["skill"]["preconditions"] == ["Customer email exists"]
    assert result["skill"]["expectedArtifacts"] == ["draft_email"]
    assert result["skill"]["runtimePolicy"]["policy"] == "human_approval_for_writes"
    assert result["skill"]["runtimePolicy"]["approvalMode"] == "auto"
    assert result["skill"]["runtimePolicy"]["approvalRequiredFor"] == ["write", "send"]
    assert result["skill"]["runtimePolicy"]["runtimeClass"] == "api"
    assert result["skill"]["lineage"]["trajectoryIds"] == ["traj-1"]
    assert result["skill"]["hardeningStatus"]["checks"]["lineage"] is True
    assert result["skill"]["hardeningStatus"]["checks"]["regression"] is False
    assert result["skill"]["skillPackage"]["manifestVersion"] == 1
    assert result["skill"]["skillPackage"]["metadata"]["promotionStatus"] == "ready"
    assert result["skill"]["skillPackage"]["productionGate"]["state"] == "needs_regression"
    assert result["skill"]["skillPackage"]["productionGate"]["canPublish"] is False
    assert result["skill"]["skillPackage"]["productionGate"]["blockers"] == ["publishableRegression"]
    assert "Run a linked benchmark regression." in result["skill"]["skillPackage"]["productionGate"]["nextActions"]
    assert result["skill"]["skillPackage"]["execution"]["connectorIds"] == ["gmail", "holded"]
    assert result["skill"]["skillPackage"]["evidence"]["regressionSuite"]["publishable"] is False

    listed = await capabilities.list_company_capabilities("co-1")
    assert listed["skills"][0]["trajectoryIds"] == ["traj-1"]
