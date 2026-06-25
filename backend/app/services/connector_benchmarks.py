from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.database import agents_collection, benchmark_tasks_collection, benchmarks_collection, capabilities_collection, connectors_collection, tools_collection, trajectories_collection
from app.harvesters.toolkit import ToolkitHarvester
from app.services.agent_runtime import _connector_tool_arguments, agent_step_result


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConnectorBenchmarkTask:
    key: str
    name: str
    prompt: str
    success_criteria: str
    expected_tools: tuple[str, ...]
    requires_approval: bool = False
    requires_browser: bool = False
    expected_artifacts: tuple[str, ...] = ()
    runtime_expectation: str = "connector_tool_without_browser"
    can_harvest_skill: bool = True
    business_intent: str = ""
    allowed_systems: tuple[str, ...] = ()
    risk_class: str = ""
    initial_state: dict[str, Any] | None = None

    def as_task_doc(self, *, benchmark_id: str, agent_id: str, email: str, company_id: str, connector_id: str, benchmark_key: str) -> dict[str, Any]:
        task_id = f"{benchmark_id}:{self.key}"
        initial_state = dict(self.initial_state or {})
        return {
            "taskId": task_id,
            "benchmarkId": benchmark_id,
            "agentId": agent_id,
            "email": email,
            "companyId": company_id,
            "name": self.name,
            "prompt": self.prompt,
            "successCriteria": self.success_criteria,
            "status": "needs_harvest" if self.can_harvest_skill else "draft",
            "source": "connector_benchmark",
            "metadata": {
                "connectorBenchmark": True,
                "connectorType": benchmark_key,
                "connectorId": connector_id,
                "expectedTools": list(self.expected_tools),
                "expectedArtifacts": list(self.expected_artifacts),
                "businessIntent": self.business_intent or self.prompt,
                "allowedSystems": list(self.allowed_systems),
                "riskClass": self.risk_class,
                "initialState": initial_state,
                "requiresApproval": self.requires_approval,
                "requiresBrowser": self.requires_browser,
                "runtimeExpectation": self.runtime_expectation,
                "withSkillExpectation": "router_may_replay_only_if_matched_task_and_approved_trajectory",
            },
            "evaluator": {
                "type": "runtime_trace",
                "expectedTools": list(self.expected_tools),
                "expectedArtifacts": list(self.expected_artifacts),
                "requiresApproval": self.requires_approval,
                "requiresBrowser": self.requires_browser,
            },
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }


EMAIL_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="search_recent_topic",
        name="Search recent mailbox topic",
        prompt="Busca el email mas reciente sobre nominas y resume que pide el cliente sin enviar nada.",
        success_criteria="Runtime searches the mailbox, returns grounded context or a clear no-email-found result, and does not open a browser.",
        expected_tools=("imap.search_emails",),
    ),
    ConnectorBenchmarkTask(
        key="search_accented_topic",
        name="Search accented mailbox topic",
        prompt="Busca el email mas reciente sobre nóminas y dime si hay algo accionable.",
        success_criteria="Runtime handles accented search text safely through IMAP and does not crash on invalid search criteria.",
        expected_tools=("imap.search_emails",),
    ),
    ConnectorBenchmarkTask(
        key="read_message_by_uid",
        name="Read email by message id",
        prompt="Lee el email con messageId 1 en INBOX y resume su contenido.",
        success_criteria="Runtime calls the read-email tool for the requested messageId and presents the body or a clear connector error.",
        expected_tools=("imap.read_email",),
    ),
    ConnectorBenchmarkTask(
        key="draft_reply_no_send",
        name="Draft client reply without sending",
        prompt=(
            "Prepara un email para cliente@example.com con asunto Seguimiento nominas y cuerpo "
            "Gracias por la informacion, revisaremos la peticion hoy. No lo envies."
        ),
        success_criteria="Runtime prepares a draft and does not request send approval because the task explicitly says not to send.",
        expected_tools=("smtp.draft_email",),
        can_harvest_skill=False,
    ),
    ConnectorBenchmarkTask(
        key="send_requires_approval",
        name="Send email requires approval",
        prompt=(
            "Envia un email a cliente@example.com con asunto Confirmacion y cuerpo "
            "Hemos recibido la solicitud y la revisaremos hoy."
        ),
        success_criteria="Runtime routes the send action through durable human approval before SMTP execution.",
        expected_tools=("api.human_approval",),
        requires_approval=True,
        can_harvest_skill=False,
    ),
)


TELEGRAM_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="get_default_chat",
        name="Check Telegram chat metadata",
        prompt="Comprueba el chat de Telegram configurado y dime su nombre y tipo.",
        success_criteria="Runtime reads Telegram chat metadata using the configured/default chat id and does not require approval.",
        expected_tools=("telegram.get_chat",),
    ),
    ConnectorBenchmarkTask(
        key="send_update_requires_approval",
        name="Send team update requires approval",
        prompt="Envia por Telegram al equipo: Recordatorio, revisar las incidencias de nomina antes de las 17:00.",
        success_criteria="Runtime requests human approval before sending the Telegram message.",
        expected_tools=("api.human_approval",),
        requires_approval=True,
        can_harvest_skill=False,
    ),
)


HOLDED_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="list_recent_invoices",
        name="List recent invoices",
        prompt="Lista las ultimas facturas de Holded y resume cliente, estado e importe si esta disponible.",
        success_criteria="Runtime calls Holded invoice listing/search tools and returns a concise business summary.",
        expected_tools=("holded.list_invoices",),
    ),
    ConnectorBenchmarkTask(
        key="search_client_invoice",
        name="Search client invoice",
        prompt="Busca facturas de Holded para el cliente Alice y dime si hay alguna pendiente.",
        success_criteria="Runtime searches invoices by client/customer and reports pending invoices if present.",
        expected_tools=("holded.search_invoices",),
    ),
    ConnectorBenchmarkTask(
        key="search_clients",
        name="Search clients",
        prompt="Busca el cliente Alice en Holded y dame los datos basicos que encuentre.",
        success_criteria="Runtime searches Holded clients/contacts and returns the matching client fields.",
        expected_tools=("holded.search_clients",),
    ),
)


BOPA_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="latest_bulletin",
        name="Fetch latest BOPA bulletin metadata",
        prompt="Busca el ultimo boletin BOPA publicado y resume su fecha y numero.",
        success_criteria="Runtime uses the BOPA connector to fetch latest bulletin metadata.",
        expected_tools=("bopa.latest_bulletin",),
    ),
    ConnectorBenchmarkTask(
        key="latest_pdf_artifact",
        name="Fetch latest BOPA PDF artifact",
        prompt="Consigue el PDF del ultimo BOPA y dejalo como artifact para revisarlo.",
        success_criteria="Runtime resolves the latest BOPA PDF and returns an artifact-like PDF URL/result.",
        expected_tools=("bopa.latest_bulletin_pdf",),
        expected_artifacts=("pdf",),
    ),
)


KNOWLEDGE_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="search_policy",
        name="Search company knowledge",
        prompt="Busca en documentos internos informacion sobre politicas de nomina y responde con fuentes.",
        success_criteria="Runtime searches the configured knowledge base and cites relevant documents or states that no source was found.",
        expected_tools=("knowledge.search",),
    ),
    ConnectorBenchmarkTask(
        key="list_documents",
        name="List knowledge documents",
        prompt="Lista los documentos internos disponibles para responder consultas de clientes.",
        success_criteria="Runtime lists indexed knowledge documents using the connector toolkit.",
        expected_tools=("knowledge.list_documents",),
    ),
)


WEB_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="fetch_text",
        name="Fetch web page text",
        prompt="Lee la pagina principal configurada y resume el texto visible.",
        success_criteria="Runtime fetches page text without launching a browser when HTTP fetch is sufficient.",
        expected_tools=("web.fetch_text",),
        runtime_expectation="http_fetch_without_browser",
    ),
    ConnectorBenchmarkTask(
        key="extract_links",
        name="Extract web page links",
        prompt="Extrae los principales links de la pagina configurada y clasificalos.",
        success_criteria="Runtime extracts links from the configured web page.",
        expected_tools=("web.extract_links",),
        runtime_expectation="http_fetch_without_browser",
    ),
    ConnectorBenchmarkTask(
        key="browser_navigation",
        name="Open site in browser runtime",
        prompt="Abre la web configurada en el browser y comprueba que carga.",
        success_criteria="Runtime uses browser navigation and the session UI shows the Browser surface because it is needed.",
        expected_tools=("browser.navigate",),
        requires_browser=True,
        runtime_expectation="browser_session_required",
    ),
)


INSURANCE_CLAIMS_BENCHMARK_TASKS: tuple[ConnectorBenchmarkTask, ...] = (
    ConnectorBenchmarkTask(
        key="claim_status_draft_no_send",
        name="Respond to claim status without sending",
        prompt=(
            "Lee el email mas reciente de un cliente preguntando por el estado de un siniestro, "
            "consulta el ERP de seguros para localizar el siniestro, revisa documentos internos aplicables "
            "y prepara un borrador de respuesta profesional sin enviarlo."
        ),
        success_criteria=(
            "Runtime reads the customer email, retrieves claim status from ERP/search tools, grounds the answer "
            "with internal knowledge where available, creates a draft_email artifact, and does not send without approval."
        ),
        expected_tools=("imap.search_emails", "erp.search_claims", "knowledge.search", "smtp.draft_email"),
        expected_artifacts=("draft_email", "claim_summary"),
        runtime_expectation="hybrid_api_first_draft_without_send",
        can_harvest_skill=False,
        business_intent="Responder a un cliente sobre el estado de un siniestro sin enviar el correo final.",
        allowed_systems=("email", "insurance_erp", "knowledge"),
        risk_class="draft",
        initial_state={
            "mailbox": "INBOX",
            "domainEntities": ["Customer", "Claim", "Policy", "Document", "DraftEmail"],
            "approvalBoundary": "send_requires_human_approval",
        },
    ),
    ConnectorBenchmarkTask(
        key="claim_status_send_requires_approval",
        name="Sending claim response requires approval",
        prompt=(
            "Envia la respuesta preparada al cliente sobre el estado del siniestro solo si un humano aprueba el envio."
        ),
        success_criteria="Runtime must stop at the approval boundary and route send through api.human_approval before SMTP send.",
        expected_tools=("api.human_approval",),
        requires_approval=True,
        expected_artifacts=("approval_request",),
        runtime_expectation="send_requires_human_approval",
        can_harvest_skill=False,
        business_intent="Proteger el envio final de comunicaciones de siniestros mediante aprobacion humana.",
        allowed_systems=("email", "approvals"),
        risk_class="send",
        initial_state={"draftExists": True, "approvalBoundary": "send"},
    ),
)


CONNECTOR_BENCHMARKS: dict[str, dict[str, Any]] = {
    "email": {
        "connectorTypes": ["smtp", "gmail"],
        "defaultConnectorType": "smtp",
        "runtimeType": "local_email_agent",
        "name": "Email Connector Runtime Benchmark",
        "description": "Business email tasks that exercise mailbox search, read, draft and approval-gated send flows.",
        "tasks": EMAIL_BENCHMARK_TASKS,
    },
    "telegram": {
        "connectorTypes": ["telegram"],
        "defaultConnectorType": "telegram",
        "runtimeType": "local_connector_agent",
        "name": "Telegram Connector Runtime Benchmark",
        "description": "Team communication tasks that exercise Telegram metadata reads and approval-gated sends.",
        "tasks": TELEGRAM_BENCHMARK_TASKS,
    },
    "holded": {
        "connectorTypes": ["holded"],
        "defaultConnectorType": "holded",
        "runtimeType": "local_connector_agent",
        "name": "Holded Connector Runtime Benchmark",
        "description": "Business back-office tasks for clients, invoices and invoice search.",
        "tasks": HOLDED_BENCHMARK_TASKS,
    },
    "bopa": {
        "connectorTypes": ["bopa"],
        "defaultConnectorType": "bopa",
        "runtimeType": "local_connector_agent",
        "name": "BOPA Connector Runtime Benchmark",
        "description": "Public bulletin tasks that exercise metadata lookup and PDF artifact creation.",
        "tasks": BOPA_BENCHMARK_TASKS,
    },
    "knowledge": {
        "connectorTypes": ["knowledge"],
        "defaultConnectorType": "knowledge",
        "runtimeType": "local_connector_agent",
        "name": "Knowledge Connector Runtime Benchmark",
        "description": "Document-grounded tasks that exercise search, listing and source-aware responses.",
        "tasks": KNOWLEDGE_BENCHMARK_TASKS,
    },
    "web": {
        "connectorTypes": ["web"],
        "defaultConnectorType": "web",
        "runtimeType": "local_connector_agent",
        "name": "Web Connector Runtime Benchmark",
        "description": "Web tasks that distinguish HTTP fetch tools from browser-required sessions.",
        "tasks": WEB_BENCHMARK_TASKS,
    },
    "insurance_claims": {
        "connectorTypes": ["smtp", "gmail"],
        "defaultConnectorType": "smtp",
        "runtimeType": "hybrid_runtime",
        "name": "Insurance Claims Vertical Benchmark",
        "description": "End-to-end insurance flow: read customer email, query ERP/knowledge, create draft artifact and enforce approval before send.",
        "tasks": INSURANCE_CLAIMS_BENCHMARK_TASKS,
        "auditEnabled": False,
        "vertical": "insurance",
        "verticalDemo": {
            "objective": "Responder a cliente sobre estado de siniestro sin enviar el correo final.",
            "runtimePath": "hybrid_api_first",
            "coverage": [
                {"key": "email_read", "label": "Email read", "evidence": "imap.search_emails"},
                {"key": "erp_lookup", "label": "ERP lookup", "evidence": "erp.search_claims"},
                {"key": "document_grounding", "label": "Document grounding", "evidence": "knowledge.search"},
                {"key": "draft_artifact", "label": "Draft artifact", "evidence": "draft_email artifact"},
                {"key": "approval_boundary", "label": "Approval boundary", "evidence": "send_requires_human_approval"},
                {"key": "benchmark", "label": "Benchmark", "evidence": "connector-insurance_claims tasks"},
                {"key": "trajectory", "label": "Trajectory", "evidence": "runtime trace/tool calls"},
                {"key": "skill_promotion", "label": "Skill promotion", "evidence": "hardened skill package"},
                {"key": "runtime_replay", "label": "Runtime replay", "evidence": "router matched approved trajectory"},
            ],
        },
    },
}


def connector_benchmark_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, spec in CONNECTOR_BENCHMARKS.items():
        rows.append(
            {
                "key": key,
                "name": spec["name"],
                "description": spec["description"],
                "connectorTypes": list(spec["connectorTypes"]),
                "runtimeType": spec["runtimeType"],
                "auditEnabled": bool(spec.get("auditEnabled", True)),
                "vertical": str(spec.get("vertical") or ""),
                "verticalDemo": spec.get("verticalDemo") if isinstance(spec.get("verticalDemo"), dict) else None,
                "tasks": [
                    {
                        "key": task.key,
                        "name": task.name,
                        "expectedTools": list(task.expected_tools),
                        "expectedArtifacts": list(task.expected_artifacts),
                        "businessIntent": task.business_intent or task.prompt,
                        "allowedSystems": list(task.allowed_systems),
                        "riskClass": task.risk_class,
                        "requiresApproval": task.requires_approval,
                        "requiresBrowser": task.requires_browser,
                        "runtimeExpectation": task.runtime_expectation,
                    }
                    for task in spec["tasks"]
                ],
            }
        )
    return rows


def get_connector_benchmark(key: str) -> dict[str, Any]:
    normalized = (key or "").strip().lower()
    if normalized not in CONNECTOR_BENCHMARKS:
        raise KeyError(f"Unknown connector benchmark {key!r}")
    return CONNECTOR_BENCHMARKS[normalized]


def connector_ready(connector: dict[str, Any]) -> tuple[bool, str]:
    status = str(connector.get("status") or "").strip().lower()
    if status == "connected":
        return True, "Connector is connected."
    if not status:
        return False, "Connector status is unknown; connect it before running runtime benchmarks."
    if status == "needs_auth":
        return False, "Connector needs authentication before runtime benchmarks can run."
    return False, f"Connector status is {status}; connect it before running runtime benchmarks."


async def find_connector_for_benchmark(company_id: str, benchmark_key: str) -> dict[str, Any] | None:
    preferred_types = list(get_connector_benchmark(benchmark_key).get("connectorTypes") or [])
    candidates = await connectors_collection.find(
        {"companyId": company_id, "type": {"$in": preferred_types}},
        {"_id": 0, "connectorId": 1, "companyId": 1, "name": 1, "type": 1, "status": 1},
    ).to_list(length=100)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            0 if str(item.get("status") or "").lower() == "connected" else 1,
            preferred_types.index(item.get("type")) if item.get("type") in preferred_types else 999,
        )
    )
    return candidates[0]


def connector_benchmark_safe_task_keys(benchmark_key: str) -> list[str]:
    spec = get_connector_benchmark(benchmark_key)
    return [
        task.key
        for task in spec["tasks"]
        if task.can_harvest_skill and not task.requires_approval and "api.human_approval" not in task.expected_tools
    ]


async def publish_connector_tools(connector: dict[str, Any]) -> list[dict[str, Any]]:
    result = await ToolkitHarvester(source="connector_benchmark").harvest(connector)
    tools = result.get("tools") if isinstance(result.get("tools"), list) else []
    for tool in tools:
        await tools_collection.update_one({"toolId": tool["toolId"]}, {"$set": tool}, upsert=True)
    return tools


async def ensure_connector_benchmark_agent(*, email: str, company_id: str, benchmark_key: str, agent_id: str = "") -> dict[str, Any]:
    spec = get_connector_benchmark(benchmark_key)
    browser_enabled = any(bool(task.requires_browser) for task in spec["tasks"])
    knowledge_enabled = benchmark_key == "knowledge"
    runtime_spec = {"browserEnabled": browser_enabled, "tools": {"connectors": True, "skills": True, "knowledge": knowledge_enabled}}
    runtime_capabilities = {
        "browser": browser_enabled,
        "tools": True,
        "skills": True,
        "artifacts": True,
        "knowledge": knowledge_enabled,
    }
    if agent_id:
        existing = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
        if existing:
            await agents_collection.update_one(
                {"agentId": agent_id},
                {"$set": {"runtimeSpec": {**(existing.get("runtimeSpec") if isinstance(existing.get("runtimeSpec"), dict) else {}), **runtime_spec}, "runtimeCapabilities": {**(existing.get("runtimeCapabilities") if isinstance(existing.get("runtimeCapabilities"), dict) else {}), **runtime_capabilities}, "updatedAt": now_iso()}},
            )
            return {**existing, "runtimeSpec": {**(existing.get("runtimeSpec") if isinstance(existing.get("runtimeSpec"), dict) else {}), **runtime_spec}, "runtimeCapabilities": {**(existing.get("runtimeCapabilities") if isinstance(existing.get("runtimeCapabilities"), dict) else {}), **runtime_capabilities}}
    existing = await agents_collection.find_one({"companyId": company_id, "metadata.connectorBenchmarkKey": benchmark_key}, {"_id": 0})
    if existing:
        await agents_collection.update_one(
            {"agentId": existing.get("agentId", "")},
            {"$set": {"runtimeSpec": {**(existing.get("runtimeSpec") if isinstance(existing.get("runtimeSpec"), dict) else {}), **runtime_spec}, "runtimeCapabilities": {**(existing.get("runtimeCapabilities") if isinstance(existing.get("runtimeCapabilities"), dict) else {}), **runtime_capabilities}, "updatedAt": now_iso()}},
        )
        return {**existing, "runtimeSpec": {**(existing.get("runtimeSpec") if isinstance(existing.get("runtimeSpec"), dict) else {}), **runtime_spec}, "runtimeCapabilities": {**(existing.get("runtimeCapabilities") if isinstance(existing.get("runtimeCapabilities"), dict) else {}), **runtime_capabilities}}
    now = now_iso()
    doc = {
        "agentId": agent_id or str(uuid.uuid4()),
        "email": email,
        "companyId": company_id,
        "name": f"{spec['name']} Agent",
        "description": f"Runtime benchmark agent for {benchmark_key} connector tasks.",
        "runtimeType": spec["runtimeType"],
        "runtimeSpec": runtime_spec,
        "runtimeCapabilities": runtime_capabilities,
        "metadata": {"connectorBenchmarkKey": benchmark_key, "connectorBenchmarkAgent": True},
        "status": "deployed",
        "createdAt": now,
        "updatedAt": now,
    }
    await agents_collection.insert_one(doc)
    return doc


async def seed_connector_benchmark(
    *,
    benchmark_key: str,
    email: str,
    company_id: str,
    connector_id: str,
    agent_id: str = "",
    publish_tools: bool = True,
) -> dict[str, Any]:
    spec = get_connector_benchmark(benchmark_key)
    connector = await connectors_collection.find_one({"connectorId": connector_id, "companyId": company_id}, {"_id": 0})
    if not connector:
        raise RuntimeError(f"Connector {connector_id!r} was not found for company {company_id!r}.")
    connector_type = str(connector.get("type") or "").lower()
    if connector_type not in set(spec["connectorTypes"]):
        raise RuntimeError(f"Connector {connector_id!r} has type {connector_type!r}; expected one of {spec['connectorTypes']}.")
    ready, reason = connector_ready(connector)
    if not ready:
        raise RuntimeError(reason)

    agent = await ensure_connector_benchmark_agent(email=email, company_id=company_id, benchmark_key=benchmark_key, agent_id=agent_id)
    if publish_tools:
        await publish_connector_tools(connector)

    benchmark_id = f"connector-{benchmark_key}-{connector_id}"
    now = now_iso()
    benchmark_doc = {
        "benchmarkId": benchmark_id,
        "email": email,
        "companyId": company_id,
        "agentId": agent["agentId"],
        "name": spec["name"],
        "description": spec["description"],
        "source": "connector_benchmark",
        "connectorId": connector_id,
        "connectorType": connector_type,
        "status": "ready",
        "createdAt": now,
        "updatedAt": now,
        "metadata": {
            "benchmarkKey": benchmark_key,
            "runtimeType": spec["runtimeType"],
            "auditEnabled": bool(spec.get("auditEnabled", True)),
            "vertical": str(spec.get("vertical") or ""),
            "verticalDemo": spec.get("verticalDemo") if isinstance(spec.get("verticalDemo"), dict) else None,
            "connectorStatus": str(connector.get("status") or ""),
            "checks": ["connector_status", "published_tools", "runtime_without_skill", "runtime_with_skill_when_available"],
        },
    }
    await benchmarks_collection.update_one({"benchmarkId": benchmark_id}, {"$set": benchmark_doc}, upsert=True)

    task_docs = [
        task.as_task_doc(
            benchmark_id=benchmark_id,
            agent_id=agent["agentId"],
            email=email,
            company_id=company_id,
            connector_id=connector_id,
            benchmark_key=benchmark_key,
        )
        for task in spec["tasks"]
    ]
    for task_doc in task_docs:
        await benchmark_tasks_collection.update_one({"taskId": task_doc["taskId"]}, {"$set": task_doc}, upsert=True)

    return {"benchmark": benchmark_doc, "agent": agent, "tasks": task_docs}


def _tool_names_from_step_result(result: dict[str, Any]) -> list[str]:
    tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), list) else []
    tool_names = [str(item.get("tool") or "") for item in tool_results if isinstance(item, dict) and item.get("tool")]
    tool_calls = result.get("tool_calls") if isinstance(result.get("tool_calls"), list) else []
    tool_names.extend(str(item.get("name") or "") for item in tool_calls if isinstance(item, dict) and item.get("name"))
    return [name for name in tool_names if name]


def _tool_matches_expected(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if expected.startswith("knowledge."):
        suffix = expected.removeprefix("knowledge")
        return actual.startswith("knowledge.") and actual.endswith(suffix)
    return False


def _artifact_evidence_text(result: dict[str, Any]) -> str:
    evidence: list[str] = [str(result.get("content") or "")]
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            evidence.extend(
                str(artifact.get(key) or "")
                for key in ("artifactType", "kind", "contentType", "fileName", "name", "title", "url", "sourceTool")
            )
        else:
            evidence.append(str(artifact))
    tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), list) else []
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        evidence.extend(str(output.get(key) or "") for key in ("pdfUrl", "url", "contentType", "fileName", "artifactType", "kind"))
    return " ".join(part for part in evidence if part).lower()


def _task_expects_skill_replay(task: dict[str, Any]) -> bool:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    expected_tools = [str(item) for item in metadata.get("expectedTools") or []]
    status = str(task.get("status") or "").lower()
    return (
        status == "approved"
        and not bool(metadata.get("requiresApproval"))
        and "api.human_approval" not in expected_tools
    )


def validate_runtime_step(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    require_skill_match: bool = False,
    forbid_skill_match: bool = False,
) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    expected_tools = [str(item) for item in metadata.get("expectedTools") or []]
    actual_tools = _tool_names_from_step_result(result)
    missing_tools = [tool for tool in expected_tools if not any(_tool_matches_expected(actual, tool) for actual in actual_tools)]
    browser_tools = [tool for tool in actual_tools if tool.startswith("browser.")]
    expected_artifacts = [str(item) for item in metadata.get("expectedArtifacts") or []]
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    artifact_evidence = _artifact_evidence_text(result)
    requires_browser = bool(metadata.get("requiresBrowser"))
    requires_approval = bool(metadata.get("requiresApproval"))
    state_out = result.get("state_out") if isinstance(result.get("state_out"), dict) else {}
    router_trace = result.get("router_trace") if isinstance(result.get("router_trace"), dict) else {}
    router_decision = str(router_trace.get("decision") or "")
    skill_replay_expected = bool(require_skill_match and _task_expects_skill_replay(task))
    failures: list[str] = []
    if missing_tools:
        failures.append(f"Missing expected tool(s): {', '.join(missing_tools)}")
    failed_results = [
        f"{item.get('tool')}: {item.get('error')}"
        for item in (result.get("tool_results") if isinstance(result.get("tool_results"), list) else [])
        if isinstance(item, dict) and item.get("success") is False
    ]
    if failed_results:
        failures.extend(failed_results)
    if not requires_browser and browser_tools:
        failures.append(f"Unexpected browser tool(s): {', '.join(browser_tools)}")
    if requires_approval and not state_out.get("pendingConnectorApproval") and "api.human_approval" not in actual_tools:
        failures.append("Expected approval gate was not requested.")
    missing_artifacts: list[str] = []
    for artifact in expected_artifacts:
        if artifact == "approval_request" and (state_out.get("pendingConnectorApproval") or "api.human_approval" in actual_tools):
            continue
        if artifact in artifact_evidence:
            continue
        missing_artifacts.append(artifact)
    if missing_artifacts:
        failures.append(f"Missing expected artifact(s): {', '.join(missing_artifacts)}")
    if skill_replay_expected and router_decision != "matched_skill":
        failures.append(f"Expected approved skill trajectory replay, got router decision {router_decision or 'missing'}.")
    if forbid_skill_match and router_decision == "matched_skill":
        failures.append("Unexpected skill trajectory replay during live runtime smoke.")
    return {
        "taskId": task.get("taskId", ""),
        "name": task.get("name", ""),
        "success": not failures,
        "failures": failures,
        "expectedTools": expected_tools,
        "expectedArtifacts": expected_artifacts,
        "actualTools": actual_tools,
        "artifactCount": len(artifacts),
        "routerDecision": router_decision,
        "skillReplayExpected": skill_replay_expected,
        "executionMode": result.get("executionMode", ""),
        "content": result.get("content", ""),
    }


async def run_connector_runtime_smoke(
    *,
    benchmark_id: str,
    agent_id: str,
    task_keys: list[str] | None = None,
    require_skill_match: bool = False,
    forbid_skill_match: bool = False,
) -> dict[str, Any]:
    query: dict[str, Any] = {"benchmarkId": benchmark_id, "agentId": agent_id}
    tasks = await benchmark_tasks_collection.find(query, {"_id": 0}).sort("taskId", 1).to_list(length=100)
    if task_keys:
        wanted = set(task_keys)
        tasks = [task for task in tasks if str(task.get("taskId") or "").split(":")[-1] in wanted or task.get("name") in wanted]
    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            step_result = await agent_step_result(
                agent_id,
                {
                    "prompt": str(task.get("prompt") or ""),
                    "task": str(task.get("prompt") or ""),
                    "step_index": 0,
                    "state_in": {},
                    "disableSkillRouting": forbid_skill_match,
                    "context": {
                        "benchmarkId": benchmark_id,
                        "taskId": task.get("taskId", ""),
                        "disableSkillRouting": forbid_skill_match,
                    },
                },
            )
            results.append(
                validate_runtime_step(
                    task,
                    step_result,
                    require_skill_match=require_skill_match,
                    forbid_skill_match=forbid_skill_match,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "taskId": task.get("taskId", ""),
                    "name": task.get("name", ""),
                    "success": False,
                    "failures": [str(exc)],
                    "expectedTools": list((task.get("metadata") if isinstance(task.get("metadata"), dict) else {}).get("expectedTools") or []),
                    "expectedArtifacts": list((task.get("metadata") if isinstance(task.get("metadata"), dict) else {}).get("expectedArtifacts") or []),
                    "actualTools": [],
                    "artifactCount": 0,
                    "routerDecision": "",
                    "skillReplayExpected": False,
                    "executionMode": "",
                    "content": "",
                }
            )
    return {
        "benchmarkId": benchmark_id,
        "agentId": agent_id,
        "total": len(results),
        "passed": sum(1 for result in results if result["success"]),
        "failed": sum(1 for result in results if not result["success"]),
        "results": results,
    }


async def harvest_connector_benchmark_tasks(
    *,
    benchmark_id: str,
    agent_id: str,
    task_keys: list[str] | None = None,
    approve_skills: bool = False,
) -> dict[str, Any]:
    benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0})
    if not benchmark:
        raise RuntimeError(f"Benchmark {benchmark_id!r} was not found.")
    agent = await agents_collection.find_one({"agentId": agent_id}, {"_id": 0})
    if not agent:
        raise RuntimeError(f"Agent {agent_id!r} was not found.")
    query: dict[str, Any] = {"benchmarkId": benchmark_id, "agentId": agent_id}
    tasks = await benchmark_tasks_collection.find(query, {"_id": 0}).sort("taskId", 1).to_list(length=100)
    if task_keys:
        wanted = set(task_keys)
        tasks = [task for task in tasks if str(task.get("taskId") or "").split(":")[-1] in wanted or task.get("name") in wanted]

    company_id = str(benchmark.get("companyId") or agent.get("companyId") or "")
    connector_id = str(benchmark.get("connectorId") or "")
    connector = await connectors_collection.find_one({"connectorId": connector_id, "companyId": company_id}, {"_id": 0}) if connector_id else {}
    connector = connector or {}
    tool_docs = await tools_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    tool_names = [str(tool.get("name") or "") for tool in tool_docs]
    tool_ids_by_name = {str(tool.get("name") or ""): str(tool.get("toolId") or "") for tool in tool_docs}

    results: list[dict[str, Any]] = []
    for task in tasks:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        expected_tools = [str(item) for item in metadata.get("expectedTools") or [] if item]
        if str(task.get("status") or "") == "draft" or bool(metadata.get("requiresApproval")):
            results.append({"taskId": task.get("taskId", ""), "name": task.get("name", ""), "status": "skipped", "reason": "Task is not safe for automatic skill harvest."})
            continue
        resolved_tools: list[str] = []
        missing: list[str] = []
        for expected in expected_tools:
            if expected in {"api.human_approval"}:
                missing.append(expected)
                continue
            if expected.startswith("browser."):
                resolved_tools.append(expected)
                continue
            actual = next((name for name in tool_names if _tool_matches_expected(name, expected)), "")
            if actual:
                resolved_tools.append(actual)
            else:
                missing.append(expected)
        if missing or not resolved_tools:
            results.append({"taskId": task.get("taskId", ""), "name": task.get("name", ""), "status": "harvest_failed", "reason": f"Missing published tool(s): {', '.join(missing or expected_tools)}"})
            continue

        prompt = str(task.get("prompt") or "")
        payload = {"context": {"benchmarkId": benchmark_id, "taskId": task.get("taskId", "")}, "url": str(benchmark.get("websiteUrl") or "")}
        trajectory = [
            {"name": tool_name, "arguments": _connector_tool_arguments(tool_name, prompt, connector, payload)}
            for tool_name in resolved_tools
        ]
        trajectory_id = str(task.get("trajectoryId") or f"{task.get('taskId')}:connector_harvest")
        now = now_iso()
        trajectory_status = "approved" if approve_skills else "harvested"
        trajectory_doc = {
            "trajectoryId": trajectory_id,
            "taskId": task.get("taskId", ""),
            "benchmarkId": benchmark_id,
            "agentId": agent_id,
            "companyId": company_id,
            "email": task.get("email") or benchmark.get("email") or agent.get("email", ""),
            "connectorIds": [connector_id] if connector_id else [],
            "toolIds": [tool_ids_by_name.get(name, "") for name in resolved_tools if tool_ids_by_name.get(name)],
            "runtimeRequirements": ["browser"] if any(name.startswith("browser.") for name in resolved_tools) else [],
            "taskName": task.get("name", ""),
            "prompt": prompt,
            "successCriteria": task.get("successCriteria", ""),
            "source": "connector_benchmark_harvester",
            "status": trajectory_status,
            "actions": [{"action": item["name"], "args": item["arguments"]} for item in trajectory],
            "trajectory": trajectory,
            "metadata": metadata,
            "harvester": {
                "adapter": "connector_benchmark_harvester",
                "status": "success",
                "confidence": 1.0,
                "summary": "Built from connector benchmark expected tools and published connector toolkit.",
            },
            "updatedAt": now,
        }
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory_id},
            {"$set": trajectory_doc, "$setOnInsert": {"createdAt": now}},
            upsert=True,
        )
        await benchmark_tasks_collection.update_one(
            {"taskId": task.get("taskId", "")},
            {"$set": {"status": trajectory_status, "trajectoryId": trajectory_id, "updatedAt": now}},
        )

        skill = None
        if approve_skills:
            capability_id = f"{trajectory_id}:skill"
            skill_doc = {
                "capabilityId": capability_id,
                "capabilityKind": "skill",
                "email": trajectory_doc["email"],
                "companyId": company_id,
                "agentId": agent_id,
                "benchmarkId": benchmark_id,
                "name": f"{task.get('name') or 'Connector benchmark task'} Skill",
                "description": prompt,
                "whenToUse": prompt,
                "connectorIds": trajectory_doc["connectorIds"],
                "toolIds": trajectory_doc["toolIds"],
                "trajectoryIds": [trajectory_id],
                "runtimeRequirements": trajectory_doc["runtimeRequirements"],
                "permissions": {"requiresApproval": False},
                "runtime": "trajectory_executor_with_recovery",
                "status": "approved",
                "source": "connector_benchmark_harvester",
                "tasks": [
                    {
                        "taskId": task.get("taskId", ""),
                        "name": task.get("name", ""),
                        "prompt": prompt,
                        "successCriteria": task.get("successCriteria", ""),
                    }
                ],
                "createdAt": now,
                "updatedAt": now,
            }
            await capabilities_collection.update_one(
                {"capabilityId": capability_id},
                {"$set": skill_doc},
                upsert=True,
            )
            skill = {"capabilityId": capability_id, "status": "approved", "trajectoryIds": [trajectory_id]}

        results.append(
            {
                "taskId": task.get("taskId", ""),
                "name": task.get("name", ""),
                "status": trajectory_status,
                "trajectoryId": trajectory_id,
                "toolNames": resolved_tools,
                "skill": skill,
            }
        )

    return {
        "benchmarkId": benchmark_id,
        "agentId": agent_id,
        "approveSkills": approve_skills,
        "total": len(results),
        "harvested": sum(1 for item in results if item.get("status") in {"harvested", "approved"}),
        "approvedSkills": sum(1 for item in results if item.get("skill")),
        "results": results,
    }


async def harvest_and_smoke_connector_benchmark(
    *,
    benchmark_id: str,
    agent_id: str,
    task_keys: list[str] | None = None,
    approve_skills: bool = True,
) -> dict[str, Any]:
    await capabilities_collection.update_many(
        {"agentId": agent_id, "benchmarkId": benchmark_id, "source": "connector_benchmark_harvester", "status": "approved"},
        {"$set": {"status": "archived", "updatedAt": now_iso()}},
    )
    runtime_without_skill = await run_connector_runtime_smoke(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=task_keys,
        forbid_skill_match=True,
    )
    harvest = await harvest_connector_benchmark_tasks(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=task_keys,
        approve_skills=approve_skills,
    )
    runtime_with_skill = await run_connector_runtime_smoke(
        benchmark_id=benchmark_id,
        agent_id=agent_id,
        task_keys=task_keys,
        require_skill_match=approve_skills,
    )
    return {
        "benchmarkId": benchmark_id,
        "agentId": agent_id,
        "runtimeWithoutSkill": runtime_without_skill,
        "harvest": harvest,
        "runtimeWithSkill": runtime_with_skill,
        "success": runtime_without_skill["failed"] == 0 and runtime_with_skill["failed"] == 0 and harvest["harvested"] > 0,
    }


async def audit_connector_benchmark_matrix(*, email: str, company_id: str, publish_tools: bool = True) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in connector_benchmark_catalog():
        if item.get("auditEnabled") is False:
            continue
        benchmark_key = str(item["key"])
        connector = await find_connector_for_benchmark(company_id, benchmark_key)
        if not connector:
            rows.append({
                "benchmark": benchmark_key,
                "status": "missing_connector",
                "reason": "No compatible connector exists for this company.",
            })
            continue

        ready, reason = connector_ready(connector)
        row: dict[str, Any] = {
            "benchmark": benchmark_key,
            "connectorId": connector.get("connectorId", ""),
            "connectorName": connector.get("name", ""),
            "connectorType": connector.get("type", ""),
            "connectorStatus": connector.get("status", ""),
            "taskKeys": connector_benchmark_safe_task_keys(benchmark_key),
        }
        if not ready:
            row.update({
                "status": "blocked_auth" if str(connector.get("status") or "").lower() == "needs_auth" else "blocked_connector",
                "reason": reason,
            })
            rows.append(row)
            continue

        try:
            seeded = await seed_connector_benchmark(
                benchmark_key=benchmark_key,
                email=email,
                company_id=company_id,
                connector_id=str(connector["connectorId"]),
                publish_tools=publish_tools,
            )
            report = await harvest_and_smoke_connector_benchmark(
                benchmark_id=seeded["benchmark"]["benchmarkId"],
                agent_id=seeded["agent"]["agentId"],
                task_keys=row["taskKeys"] or None,
                approve_skills=True,
            )
            live = report["runtimeWithoutSkill"]
            with_skill = report["runtimeWithSkill"]
            row.update({
                "status": "pass" if report["success"] else "fail",
                "benchmarkId": seeded["benchmark"]["benchmarkId"],
                "agentId": seeded["agent"]["agentId"],
                "live": {"passed": live["passed"], "total": live["total"], "failed": live["failed"]},
                "withSkill": {"passed": with_skill["passed"], "total": with_skill["total"], "failed": with_skill["failed"]},
                "harvested": report["harvest"]["harvested"],
                "approvedSkills": report["harvest"]["approvedSkills"],
                "failures": [
                    {"task": result.get("name"), "failures": result.get("failures", [])}
                    for result in [*live["results"], *with_skill["results"]]
                    if not result.get("success")
                ],
            })
        except Exception as exc:
            row.update({"status": "fail", "reason": str(exc)})
        rows.append(row)

    return {
        "companyId": company_id,
        "email": email,
        "summary": {
            "pass": sum(1 for row in rows if row["status"] == "pass"),
            "blocked": sum(1 for row in rows if str(row["status"]).startswith("blocked")),
            "missing": sum(1 for row in rows if row["status"] == "missing_connector"),
            "fail": sum(1 for row in rows if row["status"] == "fail"),
            "total": len(rows),
        },
        "rows": rows,
    }
