import pytest

from app.services import connector_benchmarks
from app.services import agent_runtime


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, field, direction):
        reverse = direction < 0
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    async def to_list(self, length=100):
        return [dict(doc) for doc in self.docs[:length]]


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
                return
        if upsert:
            next_doc = dict(query)
            next_doc.update(update.get("$setOnInsert", {}))
            next_doc.update(update.get("$set", {}))
            self.docs.append(next_doc)

    async def update_many(self, query, update):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))


def _matches(doc, query):
    for key, value in query.items():
        current = doc
        for part in key.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if isinstance(value, dict) and "$in" in value:
            if current not in value["$in"]:
                return False
            continue
        if current != value:
            return False
    return True


def test_connector_benchmark_catalog_includes_email_business_flows():
    catalog = connector_benchmarks.connector_benchmark_catalog()
    email = next(item for item in catalog if item["key"] == "email")
    keys = {item["key"] for item in catalog}

    assert {"email", "telegram", "holded", "bopa", "knowledge", "web"} <= keys
    assert email["runtimeType"] == "local_email_agent"
    assert {"smtp", "gmail"} <= set(email["connectorTypes"])
    task_keys = {task["key"] for task in email["tasks"]}
    insurance = next(item for item in catalog if item["key"] == "insurance_claims")
    assert {
        "search_recent_topic",
        "search_accented_topic",
        "read_message_by_uid",
        "draft_reply_no_send",
        "send_requires_approval",
    } <= task_keys
    assert insurance["auditEnabled"] is False
    assert insurance["vertical"] == "insurance"
    assert insurance["tasks"][0]["allowedSystems"] == ["email", "insurance_erp", "knowledge"]
    assert insurance["tasks"][0]["riskClass"] == "draft"


@pytest.mark.asyncio
async def test_seed_connector_benchmark_creates_agent_benchmark_tasks_and_tools(monkeypatch):
    connectors = _Collection(
        [
            {
                "connectorId": "smtp-1",
                "companyId": "co-1",
                "email": "user@example.com",
                "name": "SMTP",
                "type": "smtp",
                "status": "connected",
                "config": {"email": "from@example.com"},
            }
        ]
    )
    agents = _Collection()
    benchmarks = _Collection()
    tasks = _Collection()
    tools = _Collection()
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)
    monkeypatch.setattr(connector_benchmarks, "agents_collection", agents)
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", benchmarks)
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(connector_benchmarks, "tools_collection", tools)

    result = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="email",
        email="user@example.com",
        company_id="co-1",
        connector_id="smtp-1",
    )

    assert result["benchmark"]["benchmarkId"] == "connector-email-smtp-1"
    assert result["agent"]["runtimeType"] == "local_email_agent"
    assert len(result["tasks"]) == 5
    assert {task["metadata"]["connectorType"] for task in result["tasks"]} == {"email"}
    assert {task["metadata"]["expectedTools"][0] for task in result["tasks"]} >= {"imap.search_emails", "smtp.draft_email", "api.human_approval"}
    assert {tool["name"] for tool in tools.docs} >= {"imap.search_emails", "imap.read_email", "smtp.draft_email", "smtp.send_email"}


@pytest.mark.asyncio
async def test_seed_non_email_connector_benchmark_uses_connector_type_metadata(monkeypatch):
    connectors = _Collection(
        [
            {
                "connectorId": "bopa-1",
                "companyId": "co-1",
                "email": "user@example.com",
                "name": "BOPA",
                "type": "bopa",
                "status": "connected",
                "config": {},
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)
    monkeypatch.setattr(connector_benchmarks, "agents_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "tools_collection", _Collection())

    result = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="bopa",
        email="user@example.com",
        company_id="co-1",
        connector_id="bopa-1",
    )

    assert result["benchmark"]["connectorType"] == "bopa"
    assert {task["metadata"]["connectorType"] for task in result["tasks"]} == {"bopa"}
    assert any(task["metadata"]["expectedArtifacts"] == ["pdf"] for task in result["tasks"])


@pytest.mark.asyncio
async def test_seed_connector_benchmark_rejects_connector_that_needs_auth(monkeypatch):
    connectors = _Collection(
        [
            {
                "connectorId": "holded-1",
                "companyId": "co-1",
                "email": "user@example.com",
                "name": "Holded",
                "type": "holded",
                "status": "needs_auth",
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)

    with pytest.raises(RuntimeError) as exc:
        await connector_benchmarks.seed_connector_benchmark(
            benchmark_key="holded",
            email="user@example.com",
            company_id="co-1",
            connector_id="holded-1",
        )

    assert "needs authentication" in str(exc.value)


@pytest.mark.asyncio
async def test_audit_connector_benchmark_matrix_reports_blocked_auth_and_pass(monkeypatch):
    connectors = _Collection(
        [
            {"connectorId": "smtp-1", "companyId": "co-1", "email": "user@example.com", "name": "SMTP", "type": "smtp", "status": "connected"},
            {"connectorId": "telegram-1", "companyId": "co-1", "email": "user@example.com", "name": "Telegram", "type": "telegram", "status": "needs_auth"},
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)

    async def fake_seed_connector_benchmark(**kwargs):
        return {"benchmark": {"benchmarkId": "bench-email"}, "agent": {"agentId": "agent-email"}, "tasks": []}

    async def fake_harvest_and_smoke_connector_benchmark(**kwargs):
        return {
            "success": True,
            "runtimeWithoutSkill": {"passed": 1, "total": 1, "failed": 0, "results": [{"success": True}]},
            "runtimeWithSkill": {"passed": 1, "total": 1, "failed": 0, "results": [{"success": True}]},
            "harvest": {"harvested": 1, "approvedSkills": 1},
        }

    monkeypatch.setattr(connector_benchmarks, "seed_connector_benchmark", fake_seed_connector_benchmark)
    monkeypatch.setattr(connector_benchmarks, "harvest_and_smoke_connector_benchmark", fake_harvest_and_smoke_connector_benchmark)

    report = await connector_benchmarks.audit_connector_benchmark_matrix(
        email="user@example.com",
        company_id="co-1",
    )

    email_row = next(row for row in report["rows"] if row["benchmark"] == "email")
    telegram_row = next(row for row in report["rows"] if row["benchmark"] == "telegram")
    assert email_row["status"] == "pass"
    assert telegram_row["status"] == "blocked_auth"
    assert report["summary"]["pass"] == 1
    assert report["summary"]["blocked"] == 1
    assert "insurance_claims" not in {row["benchmark"] for row in report["rows"]}


@pytest.mark.asyncio
async def test_seed_insurance_claims_vertical_benchmark_creates_full_task_contract(monkeypatch):
    connectors = _Collection(
        [
            {
                "connectorId": "smtp-1",
                "companyId": "co-1",
                "email": "user@example.com",
                "name": "SMTP",
                "type": "smtp",
                "status": "connected",
                "config": {"email": "claims@example.com"},
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)
    monkeypatch.setattr(connector_benchmarks, "agents_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "tools_collection", _Collection())

    result = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="insurance_claims",
        email="user@example.com",
        company_id="co-1",
        connector_id="smtp-1",
        publish_tools=False,
    )

    first_task = result["tasks"][0]
    assert result["benchmark"]["metadata"]["vertical"] == "insurance"
    assert result["benchmark"]["metadata"]["auditEnabled"] is False
    assert result["agent"]["runtimeType"] == "hybrid_runtime"
    assert first_task["metadata"]["businessIntent"].startswith("Responder a un cliente")
    assert first_task["metadata"]["allowedSystems"] == ["email", "insurance_erp", "knowledge"]
    assert first_task["metadata"]["expectedArtifacts"] == ["draft_email", "claim_summary"]
    assert first_task["metadata"]["riskClass"] == "draft"
    assert first_task["metadata"]["initialState"]["approvalBoundary"] == "send_requires_human_approval"
    assert first_task["metadata"]["expectedTools"] == ["imap.search_emails", "erp.search_claims", "knowledge.search", "smtp.draft_email"]


@pytest.mark.asyncio
async def test_connector_benchmark_agents_are_scoped_by_benchmark_key(monkeypatch):
    connectors = _Collection(
        [
            {"connectorId": "bopa-1", "companyId": "co-1", "email": "user@example.com", "name": "BOPA", "type": "bopa", "status": "connected"},
            {"connectorId": "web-1", "companyId": "co-1", "email": "user@example.com", "name": "Web", "type": "web", "status": "connected"},
        ]
    )
    agents = _Collection()
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)
    monkeypatch.setattr(connector_benchmarks, "agents_collection", agents)
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "tools_collection", _Collection())

    bopa = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="bopa",
        email="user@example.com",
        company_id="co-1",
        connector_id="bopa-1",
    )
    web = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="web",
        email="user@example.com",
        company_id="co-1",
        connector_id="web-1",
    )

    assert bopa["agent"]["agentId"] != web["agent"]["agentId"]
    assert bopa["agent"]["runtimeCapabilities"]["browser"] is False
    assert web["agent"]["runtimeCapabilities"]["browser"] is True


@pytest.mark.asyncio
async def test_knowledge_connector_benchmark_agent_enables_knowledge_runtime(monkeypatch):
    connectors = _Collection(
        [
            {
                "connectorId": "knowledge-1",
                "companyId": "co-1",
                "email": "user@example.com",
                "name": "Knowledge",
                "type": "knowledge",
                "status": "connected",
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", connectors)
    monkeypatch.setattr(connector_benchmarks, "agents_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", _Collection())
    monkeypatch.setattr(connector_benchmarks, "tools_collection", _Collection())

    result = await connector_benchmarks.seed_connector_benchmark(
        benchmark_key="knowledge",
        email="user@example.com",
        company_id="co-1",
        connector_id="knowledge-1",
    )

    assert result["agent"]["runtimeCapabilities"]["knowledge"] is True
    assert result["agent"]["runtimeSpec"]["tools"]["knowledge"] is True


def test_validate_runtime_step_rejects_unexpected_browser_and_missing_tool():
    task = {
        "taskId": "task-1",
        "name": "Email search",
        "metadata": {"expectedTools": ["imap.search_emails"], "expectedArtifacts": ["pdf"], "requiresBrowser": False},
    }
    result = {"tool_calls": [{"name": "browser.navigate", "arguments": {}}], "tool_results": []}

    validation = connector_benchmarks.validate_runtime_step(task, result)

    assert validation["success"] is False
    assert any("Missing expected tool" in failure for failure in validation["failures"])
    assert any("Unexpected browser" in failure for failure in validation["failures"])
    assert any("Missing expected artifact" in failure for failure in validation["failures"])


def test_validate_runtime_step_accepts_artifact_evidence_from_tool_output():
    task = {
        "taskId": "task-1",
        "name": "BOPA PDF",
        "metadata": {"expectedTools": ["bopa.latest_bulletin_pdf"], "expectedArtifacts": ["pdf"], "requiresBrowser": False},
    }
    result = {
        "tool_calls": [],
        "tool_results": [
            {
                "tool": "bopa.latest_bulletin_pdf",
                "success": True,
                "output": {
                    "pdfUrl": "https://bopadocuments.blob.core.windows.net/bopa-documents/sumaris/038/038058.pdf",
                    "contentType": "application/pdf",
                },
            }
        ],
        "content": "Núm. 58 any 2026",
    }

    validation = connector_benchmarks.validate_runtime_step(task, result)

    assert validation["success"] is True
    assert validation["artifactCount"] == 0


def test_validate_runtime_step_can_require_or_forbid_skill_replay():
    approved_task = {
        "taskId": "task-1",
        "name": "BOPA PDF",
        "status": "approved",
        "metadata": {"expectedTools": ["bopa.latest_bulletin_pdf"], "requiresBrowser": False},
    }
    live_result = {
        "router_trace": {"decision": "no_safe_match"},
        "tool_results": [{"tool": "bopa.latest_bulletin_pdf", "success": True, "output": {}}],
    }
    skill_result = {
        "router_trace": {"decision": "matched_skill"},
        "tool_results": [{"tool": "bopa.latest_bulletin_pdf", "success": True, "output": {}}],
    }

    require_validation = connector_benchmarks.validate_runtime_step(
        approved_task,
        live_result,
        require_skill_match=True,
    )
    forbid_validation = connector_benchmarks.validate_runtime_step(
        approved_task,
        skill_result,
        forbid_skill_match=True,
    )
    matched_validation = connector_benchmarks.validate_runtime_step(
        approved_task,
        skill_result,
        require_skill_match=True,
    )

    assert require_validation["success"] is False
    assert require_validation["skillReplayExpected"] is True
    assert any("Expected approved skill trajectory replay" in failure for failure in require_validation["failures"])
    assert forbid_validation["success"] is False
    assert any("Unexpected skill trajectory replay" in failure for failure in forbid_validation["failures"])
    assert matched_validation["success"] is True


def test_email_runtime_plans_spanish_read_message_id_as_imap_read():
    result = agent_runtime._email_agent_response("Lee el email con messageId 1 en INBOX y resume su contenido.", {})

    assert result["tool_calls"][0]["name"] == "imap.read_email"
    assert result["tool_calls"][0]["arguments"]["messageId"] == "1"


@pytest.mark.asyncio
async def test_local_connector_runtime_can_smoke_insurance_claims_blueprint(monkeypatch):
    task = connector_benchmarks.INSURANCE_CLAIMS_BENCHMARK_TASKS[0].as_task_doc(
        benchmark_id="connector-insurance_claims-smtp-1",
        agent_id="agent-1",
        email="user@example.com",
        company_id="co-1",
        connector_id="smtp-1",
        benchmark_key="insurance_claims",
    )
    monkeypatch.setattr(agent_runtime, "benchmark_tasks_collection", _Collection([task]))
    monkeypatch.setattr(agent_runtime, "tools_collection", _Collection())
    monkeypatch.setattr(agent_runtime, "connectors_collection", _Collection([{"connectorId": "smtp-1", "companyId": "co-1", "type": "smtp"}]))

    result = await agent_runtime._local_connector_agent_response(
        {"companyId": "co-1"},
        task["prompt"],
        {},
        {"context": {"taskId": task["taskId"]}},
    )
    validation = connector_benchmarks.validate_runtime_step(task, result)

    assert [call["name"] for call in result["tool_calls"]] == ["imap.search_emails", "erp.search_claims", "knowledge.search", "smtp.draft_email"]
    assert result["artifacts"][0]["artifactType"] == "draft_email"
    assert validation["success"] is True


@pytest.mark.asyncio
async def test_local_connector_runtime_requests_approval_for_insurance_send(monkeypatch):
    task = connector_benchmarks.INSURANCE_CLAIMS_BENCHMARK_TASKS[1].as_task_doc(
        benchmark_id="connector-insurance_claims-smtp-1",
        agent_id="agent-1",
        email="user@example.com",
        company_id="co-1",
        connector_id="smtp-1",
        benchmark_key="insurance_claims",
    )
    monkeypatch.setattr(agent_runtime, "benchmark_tasks_collection", _Collection([task]))
    monkeypatch.setattr(agent_runtime, "tools_collection", _Collection())
    monkeypatch.setattr(agent_runtime, "connectors_collection", _Collection([{"connectorId": "smtp-1", "companyId": "co-1", "type": "smtp"}]))

    result = await agent_runtime._local_connector_agent_response(
        {"companyId": "co-1"},
        task["prompt"],
        {},
        {"context": {"taskId": task["taskId"]}},
    )
    validation = connector_benchmarks.validate_runtime_step(task, result)

    assert result["tool_calls"][0]["name"] == "api.human_approval"
    assert result["state_out"]["pendingConnectorApproval"]
    assert validation["success"] is True


def test_connector_harvester_builds_email_tool_arguments():
    search_args = agent_runtime._connector_tool_arguments("imap.search_emails", "Busca el email mas reciente sobre nominas.", {}, {})
    read_args = agent_runtime._connector_tool_arguments("imap.read_email", "Lee el email con messageId 1 en INBOX y resume su contenido.", {}, {})
    draft_args = agent_runtime._connector_tool_arguments(
        "smtp.draft_email",
        "Prepara un email para cliente@example.com con asunto Seguimiento y cuerpo Gracias, revisaremos la peticion hoy.",
        {},
        {},
    )

    assert search_args["query"] == "nominas"
    assert search_args["folder"] == "INBOX"
    assert read_args == {"messageId": "1", "folder": "INBOX"}
    assert draft_args["to"] == "cliente@example.com"
    assert draft_args["subject"] == "Seguimiento"


@pytest.mark.asyncio
async def test_local_connector_runtime_resolves_benchmark_expected_tool(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "benchmark_tasks_collection",
        _Collection(
            [
                {
                    "taskId": "task-1",
                    "metadata": {"expectedTools": ["bopa.latest_bulletin_pdf"], "connectorId": "bopa-1"},
                }
            ]
        ),
    )
    monkeypatch.setattr(agent_runtime, "tools_collection", _Collection([{"companyId": "co-1", "name": "bopa.latest_bulletin_pdf", "connectorId": "bopa-1"}]))
    monkeypatch.setattr(agent_runtime, "connectors_collection", _Collection([{"connectorId": "bopa-1", "companyId": "co-1", "type": "bopa"}]))

    result = await agent_runtime._local_connector_agent_response(
        {"companyId": "co-1"},
        "Consigue el PDF del ultimo BOPA",
        {},
        {"context": {"taskId": "task-1"}},
    )

    assert result["tool_calls"][0]["name"] == "bopa.latest_bulletin_pdf"


@pytest.mark.asyncio
async def test_local_connector_runtime_resolves_dynamic_knowledge_tool(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "benchmark_tasks_collection",
        _Collection(
            [
                {
                    "taskId": "task-1",
                    "metadata": {"expectedTools": ["knowledge.search"], "connectorId": "knowledge-1"},
                }
            ]
        ),
    )
    monkeypatch.setattr(agent_runtime, "tools_collection", _Collection([{"companyId": "co-1", "name": "knowledge.company_docs.search", "connectorId": "knowledge-1"}]))
    monkeypatch.setattr(agent_runtime, "connectors_collection", _Collection([{"connectorId": "knowledge-1", "companyId": "co-1", "type": "knowledge"}]))

    result = await agent_runtime._local_connector_agent_response(
        {"companyId": "co-1"},
        "Busca en documentos internos politicas de nomina",
        {},
        {"context": {"taskId": "task-1"}},
    )

    assert result["tool_calls"][0]["name"] == "knowledge.company_docs.search"
    assert result["tool_calls"][0]["arguments"]["query"].startswith("Busca en documentos")


@pytest.mark.asyncio
async def test_harvest_connector_benchmark_tasks_promotes_approved_skill(monkeypatch):
    benchmark_id = "connector-bopa-bopa-1"
    agent_id = "agent-1"
    monkeypatch.setattr(connector_benchmarks, "benchmarks_collection", _Collection([{"benchmarkId": benchmark_id, "agentId": agent_id, "companyId": "co-1", "connectorId": "bopa-1", "email": "user@example.com"}]))
    monkeypatch.setattr(connector_benchmarks, "agents_collection", _Collection([{"agentId": agent_id, "companyId": "co-1", "email": "user@example.com"}]))
    monkeypatch.setattr(connector_benchmarks, "connectors_collection", _Collection([{"connectorId": "bopa-1", "companyId": "co-1", "type": "bopa"}]))
    monkeypatch.setattr(connector_benchmarks, "tools_collection", _Collection([{"toolId": "tool-bopa", "companyId": "co-1", "name": "bopa.latest_bulletin_pdf", "connectorId": "bopa-1"}]))
    trajectories = _Collection()
    capabilities = _Collection()
    tasks = _Collection(
        [
            {
                "taskId": f"{benchmark_id}:latest_pdf_artifact",
                "benchmarkId": benchmark_id,
                "agentId": agent_id,
                "email": "user@example.com",
                "companyId": "co-1",
                "name": "Fetch latest BOPA PDF artifact",
                "prompt": "Consigue el PDF del ultimo BOPA y dejalo como artifact para revisarlo.",
                "successCriteria": "PDF URL is returned.",
                "status": "needs_harvest",
                "metadata": {"expectedTools": ["bopa.latest_bulletin_pdf"], "expectedArtifacts": ["pdf"], "connectorId": "bopa-1"},
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", tasks)
    monkeypatch.setattr(connector_benchmarks, "trajectories_collection", trajectories)
    monkeypatch.setattr(connector_benchmarks, "capabilities_collection", capabilities)

    report = await connector_benchmarks.harvest_connector_benchmark_tasks(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=["latest_pdf_artifact"],
        approve_skills=True,
    )

    assert report["harvested"] == 1
    assert report["approvedSkills"] == 1
    assert trajectories.docs[0]["status"] == "approved"
    assert trajectories.docs[0]["trajectory"] == [{"name": "bopa.latest_bulletin_pdf", "arguments": {}}]
    assert capabilities.docs[0]["status"] == "approved"
    assert capabilities.docs[0]["tasks"][0]["prompt"].startswith("Consigue el PDF")


@pytest.mark.asyncio
async def test_harvest_and_smoke_reports_without_and_with_skill(monkeypatch):
    calls = []

    async def fake_run_connector_runtime_smoke(**kwargs):
        calls.append(("runtime", kwargs))
        decision = "matched_skill" if len([call for call in calls if call[0] == "runtime"]) == 2 else "no_safe_match"
        return {"benchmarkId": kwargs["benchmark_id"], "agentId": kwargs["agent_id"], "total": 1, "passed": 1, "failed": 0, "results": [{"routerDecision": decision, "success": True}]}

    async def fake_harvest_connector_benchmark_tasks(**kwargs):
        calls.append(("harvest", kwargs))
        return {"benchmarkId": kwargs["benchmark_id"], "agentId": kwargs["agent_id"], "total": 1, "harvested": 1, "approvedSkills": 1, "results": []}

    monkeypatch.setattr(connector_benchmarks, "run_connector_runtime_smoke", fake_run_connector_runtime_smoke)
    monkeypatch.setattr(connector_benchmarks, "harvest_connector_benchmark_tasks", fake_harvest_connector_benchmark_tasks)
    monkeypatch.setattr(connector_benchmarks, "capabilities_collection", _Collection())

    report = await connector_benchmarks.harvest_and_smoke_connector_benchmark(
        benchmark_id="bench-1",
        agent_id="agent-1",
        task_keys=["latest_pdf_artifact"],
        approve_skills=True,
    )

    assert report["success"] is True
    assert report["runtimeWithoutSkill"]["results"][0]["routerDecision"] == "no_safe_match"
    assert report["runtimeWithSkill"]["results"][0]["routerDecision"] == "matched_skill"
    assert calls[0][1]["forbid_skill_match"] is True
    assert calls[2][1]["require_skill_match"] is True
    assert calls[1][0] == "harvest"


@pytest.mark.asyncio
async def test_skill_router_matches_only_concrete_approved_task_route(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-approved",
                    "status": "approved",
                    "trajectory": [{"name": "bopa.latest_bulletin_pdf", "arguments": {}}],
                }
            ]
        ),
    )
    skills = [
        {
            "capabilityId": "skill-bopa",
            "name": "Download latest BOPA PDF",
            "status": "approved",
            "trajectoryIds": ["traj-approved"],
            "tasks": [
                {
                    "name": "Download latest BOPA PDF",
                    "prompt": "Descargar documento oficial boletin BOPA Andorra",
                    "successCriteria": "Return the latest BOPA PDF URL.",
                }
            ],
        }
    ]

    route = await agent_runtime._route_skill_match("Descargar documento oficial boletin BOPA Andorra", skills)

    assert route["decision"] == "matched_skill"
    assert route["matchedSkillId"] == "skill-bopa"
    assert route["matchedTaskName"] == "Download latest BOPA PDF"
    assert route["thresholds"]["requiresApprovedExecutableTrajectory"] is True


@pytest.mark.asyncio
async def test_skill_router_allows_short_exact_concrete_task_route(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-approved",
                    "status": "approved",
                    "trajectory": [{"name": "imap.read_email", "arguments": {"messageId": "1", "folder": "INBOX"}}],
                }
            ]
        ),
    )
    skills = [
        {
            "capabilityId": "skill-email-read",
            "name": "Read email by message id Skill",
            "status": "approved",
            "trajectoryIds": ["traj-approved"],
            "tasks": [
                {
                    "name": "Read email by message id",
                    "prompt": "Lee el email con messageId 1 en INBOX y resume su contenido.",
                }
            ],
        }
    ]

    route = await agent_runtime._route_skill_match(
        "Lee el email con messageId 1 en INBOX y resume su contenido.",
        skills,
    )

    assert route["decision"] == "matched_skill"
    assert route["matchedSkillId"] == "skill-email-read"
    assert route["candidates"][0]["overlapCount"] == 3


@pytest.mark.asyncio
async def test_skill_router_rejects_harvested_or_skill_only_routes(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "trajectories_collection",
        _Collection(
            [
                {
                    "trajectoryId": "traj-harvested",
                    "status": "harvested",
                    "trajectory": [{"name": "bopa.latest_bulletin_pdf", "arguments": {}}],
                }
            ]
        ),
    )
    harvested_skill = {
        "capabilityId": "skill-harvested",
        "name": "Download latest BOPA PDF",
        "status": "approved",
        "trajectoryIds": ["traj-harvested"],
        "tasks": [{"name": "Download latest BOPA PDF", "prompt": "Descargar documento oficial boletin BOPA Andorra"}],
    }
    skill_only = {
        "capabilityId": "skill-only",
        "name": "Descargar documento oficial boletin BOPA Andorra",
        "status": "approved",
        "trajectoryIds": ["traj-harvested"],
        "description": "Descargar documento oficial boletin BOPA Andorra",
    }

    harvested_route = await agent_runtime._route_skill_match("Descargar documento oficial boletin BOPA Andorra", [harvested_skill])
    skill_only_route = await agent_runtime._route_skill_match("Descargar documento oficial boletin BOPA Andorra", [skill_only])

    assert harvested_route["decision"] == "no_safe_match"
    assert "not approved" in harvested_route["reason"]
    assert skill_only_route["decision"] == "no_safe_match"
    assert "concrete source task" in skill_only_route["reason"]


@pytest.mark.asyncio
async def test_run_connector_runtime_smoke_validates_agent_step(monkeypatch):
    tasks = _Collection(
        [
            {
                "taskId": "connector-email-smtp-1:search_recent_topic",
                "benchmarkId": "connector-email-smtp-1",
                "agentId": "agent-1",
                "prompt": "Busca email",
                "name": "Search",
                "metadata": {"expectedTools": ["imap.search_emails"], "requiresBrowser": False},
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", tasks)

    async def fake_agent_step_result(agent_id, payload):
        assert payload["disableSkillRouting"] is False
        return {
            "executionMode": "connector_tool",
            "router_trace": {"decision": "no_safe_match"},
            "tool_results": [{"tool": "imap.search_emails", "success": True, "output": {"messages": []}}],
            "state_out": {},
        }

    monkeypatch.setattr(connector_benchmarks, "agent_step_result", fake_agent_step_result)

    report = await connector_benchmarks.run_connector_runtime_smoke(
        benchmark_id="connector-email-smtp-1",
        agent_id="agent-1",
    )

    assert report["passed"] == 1
    assert report["failed"] == 0
    assert report["results"][0]["routerDecision"] == "no_safe_match"


@pytest.mark.asyncio
async def test_run_connector_runtime_smoke_can_disable_skill_routing(monkeypatch):
    tasks = _Collection(
        [
            {
                "taskId": "connector-bopa-1:latest_pdf_artifact",
                "benchmarkId": "connector-bopa-1",
                "agentId": "agent-1",
                "prompt": "Consigue el PDF del ultimo BOPA",
                "name": "BOPA PDF",
                "metadata": {"expectedTools": ["bopa.latest_bulletin_pdf"], "requiresBrowser": False},
            }
        ]
    )
    monkeypatch.setattr(connector_benchmarks, "benchmark_tasks_collection", tasks)

    async def fake_agent_step_result(agent_id, payload):
        assert payload["disableSkillRouting"] is True
        assert payload["context"]["disableSkillRouting"] is True
        return {
            "executionMode": "connector_tool",
            "router_trace": {"decision": "skill_routing_disabled"},
            "tool_results": [{"tool": "bopa.latest_bulletin_pdf", "success": True, "output": {}}],
            "state_out": {},
        }

    monkeypatch.setattr(connector_benchmarks, "agent_step_result", fake_agent_step_result)

    report = await connector_benchmarks.run_connector_runtime_smoke(
        benchmark_id="connector-bopa-1",
        agent_id="agent-1",
        forbid_skill_match=True,
    )

    assert report["passed"] == 1
    assert report["results"][0]["routerDecision"] == "skill_routing_disabled"
