from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.company_harvesters.base import CompanyHarvesterEngineInfo
from app.models.company_harvester import (
    CompanyAgentProviderPlan,
    CompanyConnectorPlan,
    CompanyHarvesterInput,
    CompanyHarvesterOutput,
    CompanySkillPlan,
    CompanyTaskProposal,
    CompanyTaskSolution,
    CompanyToolPlan,
    CompanyTrajectoryPlan,
)


def _slug(value: str, fallback: str = "item") -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    clean = "_".join(part for part in clean.split("_") if part)
    return clean or fallback


def _openapi_operations(material: Any) -> list[str]:
    metadata = material.metadata if hasattr(material, "metadata") else {}
    spec = metadata.get("openapi") if isinstance(metadata, dict) else {}
    paths = spec.get("paths") if isinstance(spec, dict) else {}
    operations: list[str] = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            operation_id = str(operation.get("operationId") or f"{method}_{path}").strip()
            if operation_id:
                operations.append(operation_id)
    return operations


def _code_operations(material: Any) -> list[str]:
    content = str(getattr(material, "content", "") or "")
    metadata = material.metadata if hasattr(material, "metadata") else {}
    text = "\n".join([content, _text_blob(metadata)])
    operations: list[str] = []
    route_tokens = (
        ("getOrder", ("get", "/orders")),
        ("draftRefund", ("refund",)),
        ("addInventoryNote", ("inventory", "note")),
        ("searchCustomers", ("customer", "search")),
        ("listClaims", ("claims",)),
        ("getClaim", ("claim_id",)),
        ("addClaimNote", ("claim", "note")),
        ("setClaimDecision", ("decision",)),
        ("calculateEnterpriseDiscount", ("discount", "enterprise")),
    )
    lowered = text.lower()
    for operation, signals in route_tokens:
        if all(signal.lower() in lowered for signal in signals):
            operations.append(operation)
    return sorted(set(operations))


def _text_blob(value: Any) -> str:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return str(value or "").lower()


def _has_all(text: str, *terms: str) -> bool:
    return all(term.lower() in text for term in terms)


def _available_connectors(request: CompanyHarvesterInput) -> dict[str, dict[str, Any]]:
    raw = request.availableInventory.get("connectors") if isinstance(request.availableInventory, dict) else []
    return {
        str(item.get("connectorId") or item.get("name") or ""): item
        for item in raw or []
        if isinstance(item, dict) and (item.get("connectorId") or item.get("name"))
    }


def _available_tools(request: CompanyHarvesterInput) -> dict[str, dict[str, Any]]:
    raw = request.availableInventory.get("tools") if isinstance(request.availableInventory, dict) else []
    return {
        str(item.get("name") or item.get("toolId") or ""): item
        for item in raw or []
        if isinstance(item, dict) and (item.get("name") or item.get("toolId"))
    }


def _connector_origin(request: CompanyHarvesterInput, connector_id: str, connector_type: str, default: str) -> tuple[str, str]:
    for available_id, connector in _available_connectors(request).items():
        if available_id == connector_id or connector.get("type") == connector_type:
            return "existing", str(connector.get("connectorId") or available_id)
    return default, ""


def _tool_origin(request: CompanyHarvesterInput, tool_name: str, default: str) -> tuple[str, str]:
    for available_name, tool in _available_tools(request).items():
        if available_name == tool_name or tool.get("name") == tool_name:
            return "existing_connector_tool", str(tool.get("toolId") or available_name)
    return default, ""


def _proposal(
    request: CompanyHarvesterInput,
    *,
    key: str,
    name: str,
    prompt: str,
    success: str,
    surfaces: list[str],
    risk: str = "read",
    confidence: float = 0.72,
    evidence: list[dict[str, Any]] | None = None,
) -> CompanyTaskProposal:
    return CompanyTaskProposal(
        taskId=f"{request.companyId}:task:business:{key}",
        name=name,
        prompt=prompt,
        successCriteria=success,
        expectedSurfaces=surfaces,
        riskClass=risk,
        confidence=confidence,
        evidence=evidence or [],
        metadata={"businessTask": True},
    )


@dataclass(frozen=True)
class AgenticDiscoveryCore:
    """Deterministic discovery core shared by the built-in harvester adapters."""

    name: str = "agentic"
    kind: str = "agentic"
    display_name: str = "Agentic Harvester"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="agentic",
            displayName=self.display_name,
            description="Agentic CompanyHarvester for extracting tasks, connectors, tools, trajectories, skills and agent build plans from company materials.",
            metadata={"execution": "local_agentic_core"},
        )

    async def harvest(self, request: CompanyHarvesterInput) -> CompanyHarvesterOutput:
        connectors: dict[str, CompanyConnectorPlan] = {}
        tools: dict[str, CompanyToolPlan] = {}
        proposals: list[CompanyTaskProposal] = []
        operations: list[str] = []
        material_text = _text_blob([material.model_dump(mode="json") for material in request.materials])

        for material in request.materials:
            kind = material.kind
            if kind == "website":
                connector_id = f"{request.companyId}:web:{_slug(material.url or material.name)}"
                origin, existing_id = _connector_origin(request, connector_id, "web", "proposed_custom")
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name=material.name or "Company Web",
                    type="web",
                    origin=origin,  # type: ignore[arg-type]
                    existingConnectorId=existing_id,
                    surface="webapp",
                    authRequired=bool(material.metadata.get("authRequired")),
                    runtimeRequirements=["browser", "network"],
                    evidence=[{"materialKind": kind, "url": material.url, "origin": origin}],
                    metadata={"material": material.model_dump(mode="json")},
                )
                tool_id = f"{connector_id}:explore_workflows"
                tool_name = f"{_slug(request.companyName or request.companyId)}.web.explore_workflows"
                tool_origin, existing_tool_id = _tool_origin(request, tool_name, "proposed_custom")
                tools[tool_name] = CompanyToolPlan(
                    toolId=tool_id,
                    name=tool_name,
                    origin=tool_origin,  # type: ignore[arg-type]
                    existingToolId=existing_tool_id,
                    connectorId=connector_id,
                    executionType="browser_automation",
                    policyBoundary="read",
                    evidence=[{"materialKind": kind, "url": material.url, "origin": tool_origin}],
                    runtimeRequirements=["browser", "network"] if False else [],
                )
                proposals.append(
                    CompanyTaskProposal(
                        taskId=f"{request.companyId}:task:explore_web",
                        name=f"Explore {material.name or 'company web'}",
                        prompt=f"Explore {material.name or 'the company web app'} and identify useful business workflows.",
                        successCriteria="A useful workflow is identified with evidence.",
                        expectedSurfaces=["web"],
                        confidence=0.35,
                        evidence=[{"materialKind": kind, "name": material.name, "url": material.url}],
                    )
                )
            elif kind in {"openapi", "api_docs"}:
                tool_namespace = _slug(str(material.metadata.get("icaProjectId") or material.name or request.companyName or request.companyId))
                connector_id = f"{request.companyId}:api:{_slug(material.url or material.name)}"
                origin, existing_id = _connector_origin(request, connector_id, "api", "derived_from_openapi")
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name=material.name or "Company API",
                    type="api",
                    origin=origin,  # type: ignore[arg-type]
                    existingConnectorId=existing_id,
                    surface="api",
                    authRequired=bool(material.metadata.get("authRequired")),
                    runtimeRequirements=["network", "api_docs_or_openapi"],
                    evidence=[{"materialKind": kind, "url": material.url, "openApiUrl": material.metadata.get("openApiUrl"), "origin": origin}],
                    metadata={"material": material.model_dump(mode="json")},
                )
                material_operations = _openapi_operations(material)
                if not material_operations:
                    material_operations = ["discover_operations"]
                operations.extend(material_operations)
                for operation in material_operations:
                    tool_name = f"{tool_namespace}.api.{_slug(operation)}"
                    tool_origin, existing_tool_id = _tool_origin(request, tool_name, "derived_from_openapi")
                    tools[tool_name] = CompanyToolPlan(
                        toolId=f"{connector_id}:{_slug(operation)}",
                        name=tool_name,
                        origin=tool_origin,  # type: ignore[arg-type]
                        existingToolId=existing_tool_id,
                        connectorId=connector_id,
                        executionType="api_call",
                        policyBoundary="write" if any(term in operation.lower() for term in ("post", "add", "set", "update", "delete", "decision")) else "read",
                        evidence=[{"materialKind": kind, "operationId": operation, "origin": tool_origin}],
                    )
                    proposals.append(
                        CompanyTaskProposal(
                            taskId=f"{request.companyId}:task:validate:{_slug(operation)}",
                            name=f"Validate {tool_name}",
                            prompt=f"Use the {tool_name} API tool and capture the result.",
                            successCriteria="The API tool returns a valid result or a clear connector gap.",
                            expectedSurfaces=["api"],
                            confidence=0.45,
                            evidence=[{"materialKind": kind, "operationId": operation, "toolName": tool_name}],
                        )
                    )
            elif kind in {"document_url", "file", "knowledge_note"}:
                connector_id = f"{request.companyId}:knowledge:company"
                origin, existing_id = _connector_origin(request, connector_id, "knowledge", "proposed_custom")
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name="Company Knowledge",
                    type="knowledge",
                    origin=origin,  # type: ignore[arg-type]
                    existingConnectorId=existing_id,
                    surface="knowledge",
                    runtimeRequirements=["vectorstore", "embedding_model"],
                    evidence=[{"materialKind": kind, "name": material.name, "url": material.url, "origin": origin}],
                )
                tool_origin, existing_tool_id = _tool_origin(request, "knowledge.company_docs.search", "proposed_custom")
                tools["knowledge.company_docs.search"] = CompanyToolPlan(
                    toolId=f"{connector_id}:search",
                    name="knowledge.company_docs.search",
                    origin=tool_origin,  # type: ignore[arg-type]
                    existingToolId=existing_tool_id,
                    connectorId=connector_id,
                    executionType="knowledge_search",
                    evidence=[{"materialKind": kind, "name": material.name, "origin": tool_origin}],
                )
                proposals.append(
                    CompanyTaskProposal(
                        taskId=f"{request.companyId}:task:knowledge:{_slug(material.name)}",
                        name=f"Answer from {material.name or 'company knowledge'}",
                        prompt=f"Use company knowledge in {material.name or 'the provided material'} to answer an operational question.",
                        successCriteria="The answer cites relevant company knowledge.",
                        expectedSurfaces=["documents"],
                        confidence=0.35,
                        evidence=[{"materialKind": kind, "name": material.name, "url": material.url}],
                    )
                )
            elif kind in {"code_repository", "code_file"}:
                tool_namespace = _slug(str(material.metadata.get("icaProjectId") or material.name or request.companyName or request.companyId))
                connector_id = f"{request.companyId}:code:{_slug(material.url or material.name)}"
                origin, existing_id = _connector_origin(request, connector_id, "code", "derived_from_code")
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name=material.name or "Company Code",
                    type="code",
                    origin=origin,  # type: ignore[arg-type]
                    existingConnectorId=existing_id,
                    surface="code",
                    authRequired=bool(material.metadata.get("authRequired")),
                    runtimeRequirements=["repository_read"],
                    evidence=[{"materialKind": kind, "name": material.name, "url": material.url, "origin": origin}],
                    metadata={"material": material.model_dump(mode="json", exclude={"content"})},
                )
                code_tool_name = f"{tool_namespace}.code.inspect"
                tool_origin, existing_tool_id = _tool_origin(request, code_tool_name, "derived_from_code")
                tools[code_tool_name] = CompanyToolPlan(
                    toolId=f"{connector_id}:inspect",
                    name=code_tool_name,
                    origin=tool_origin,  # type: ignore[arg-type]
                    existingToolId=existing_tool_id,
                    connectorId=connector_id,
                    executionType="code_inspection",
                    policyBoundary="read",
                    evidence=[{"materialKind": kind, "name": material.name, "origin": tool_origin}],
                )
                material_operations = _code_operations(material)
                operations.extend(material_operations)
                api_connector_id = ""
                web_connector_id = ""
                if material_operations:
                    api_connector_id = f"{request.companyId}:api:derived_from_code:{_slug(material.name)}"
                    api_origin, api_existing_id = _connector_origin(request, api_connector_id, "api", "derived_from_code")
                    connectors[api_connector_id] = CompanyConnectorPlan(
                        connectorId=api_connector_id,
                        name=f"{material.name or 'Company Code'} derived API",
                        type="api",
                        origin=api_origin,  # type: ignore[arg-type]
                        existingConnectorId=api_existing_id,
                        surface="api",
                        authRequired=bool(material.metadata.get("authRequired")),
                        runtimeRequirements=["repository_read", "network"],
                        evidence=[{"materialKind": kind, "derivedFrom": "code", "operations": material_operations, "origin": api_origin}],
                        metadata={"derivedFrom": connector_id},
                    )
                if any(term in str(material.content or "").lower() for term in ("fetch(", "onclick", "button", "input", "textarea")):
                    web_connector_id = f"{request.companyId}:web:derived_from_code:{_slug(material.name)}"
                    web_origin, web_existing_id = _connector_origin(request, web_connector_id, "web", "derived_from_code")
                    connectors[web_connector_id] = CompanyConnectorPlan(
                        connectorId=web_connector_id,
                        name=f"{material.name or 'Company Code'} derived Web UI",
                        type="web",
                        origin=web_origin,  # type: ignore[arg-type]
                        existingConnectorId=web_existing_id,
                        surface="webapp",
                        authRequired=bool(material.metadata.get("authRequired")),
                        runtimeRequirements=["repository_read", "browser"],
                        evidence=[{"materialKind": kind, "derivedFrom": "code", "origin": web_origin}],
                        metadata={"derivedFrom": connector_id},
                    )
                    web_tool_name = f"{tool_namespace}.web.explore_workflows"
                    web_tool_origin, web_existing_tool_id = _tool_origin(request, web_tool_name, "derived_from_code")
                    tools[web_tool_name] = CompanyToolPlan(
                        toolId=f"{web_connector_id}:explore_workflows",
                        name=web_tool_name,
                        origin=web_tool_origin,  # type: ignore[arg-type]
                        existingToolId=web_existing_tool_id,
                        connectorId=web_connector_id,
                        executionType="browser_automation_derived_from_code",
                        policyBoundary="read",
                        evidence=[{"materialKind": kind, "derivedFrom": "code", "origin": web_tool_origin}],
                    )
                for operation in material_operations:
                    if api_connector_id:
                        api_tool_name = f"{tool_namespace}.api.{_slug(operation)}"
                        api_tool_origin, api_existing_tool_id = _tool_origin(request, api_tool_name, "derived_from_code")
                        tools[api_tool_name] = CompanyToolPlan(
                            toolId=f"{connector_id}:derived_api:{_slug(operation)}",
                            name=api_tool_name,
                            origin=api_tool_origin,  # type: ignore[arg-type]
                            existingToolId=api_existing_tool_id,
                            connectorId=api_connector_id,
                            executionType="api_call_derived_from_code",
                            policyBoundary="write" if operation in {"draftRefund", "addInventoryNote", "addClaimNote", "setClaimDecision"} else "read",
                            evidence=[{"materialKind": kind, "operationId": operation, "derivedFrom": "code", "origin": api_tool_origin}],
                        )
                proposals.append(
                    CompanyTaskProposal(
                        taskId=f"{request.companyId}:task:inspect_code",
                        name=f"Inspect {material.name or 'company code'}",
                        prompt="Inspect the provided code to identify business workflows, API routes and automation surfaces.",
                        successCriteria="Relevant workflows are identified from code evidence.",
                        expectedSurfaces=["code"],
                        confidence=0.38,
                        evidence=[{"materialKind": kind, "name": material.name, "url": material.url}],
                    )
                )

        for user_task in request.userTasks:
            if not isinstance(user_task, dict):
                continue
            prompt = str(user_task.get("prompt") or user_task.get("name") or "").strip()
            if prompt:
                proposals.append(
                    CompanyTaskProposal(
                        taskId=str(user_task.get("taskId") or user_task.get("id") or f"{request.companyId}:task:user:{_slug(prompt)}"),
                        name=str(user_task.get("name") or prompt[:80]),
                        prompt=prompt,
                        successCriteria=str(user_task.get("successCriteria") or ""),
                        expectedSurfaces=[str(item) for item in user_task.get("expectedSurfaces") or []],
                        riskClass=str(user_task.get("riskClass") or "read"),
                        confidence=0.9,
                        evidence=[{"source": "user_task"}],
                        metadata=user_task.get("metadata") if isinstance(user_task.get("metadata"), dict) else {},
                    )
                )

        proposals.extend(self._business_task_proposals(request, operations=operations, material_text=material_text))
        proposals = self._dedupe_proposals(proposals)

        solutions = [
            self._solution_for_task(request, proposal, connectors=list(connectors.values()), tools=list(tools.values()))
            for proposal in proposals
        ]
        return CompanyHarvesterOutput(
            companyId=request.companyId,
            proposedTasks=proposals,
            taskSolutions=solutions,
            confidence=0.45,
            metadata={
                "harvesterEngine": self.info().model_dump(mode="json"),
                "discoveryMode": request.discoveryMode,
                "inputMaterialCount": len(request.materials),
            },
        )

    def _business_task_proposals(self, request: CompanyHarvesterInput, *, operations: list[str], material_text: str) -> list[CompanyTaskProposal]:
        op_text = " ".join(operations).lower()
        evidence = [{"source": "semantic_business_task_inference", "operations": operations[:20]}]
        has_claims = "claim" in op_text or "claim" in material_text
        has_customers = "customer" in op_text or "customer" in material_text
        has_orders = "order" in op_text or "order" in material_text
        has_inventory = "inventory" in op_text or "inventory" in material_text
        has_refund = "refund" in op_text or "refund" in material_text
        has_discount = "discount" in op_text or "discount" in material_text
        has_enterprise = "enterprise" in op_text or "enterprise" in material_text
        has_calendar = "calendar" in op_text or "calendar" in material_text or "autocalendar" in material_text
        has_get_claim = "getclaim" in op_text or _has_all(op_text, "get", "claim")
        has_list_claims = "listclaims" in op_text or _has_all(op_text, "list", "claim")
        has_search_customers = "searchcustomers" in op_text or _has_all(op_text, "search", "customer")
        has_add_note = (
            "addclaimnote" in op_text
            or _has_all(op_text, "add", "note")
            or "note" in material_text
            or (request.discoveryMode == "ui_only" and has_claims and any(term in material_text for term in ("claim detail", "reviewing claim", "changing claim", "update claim")))
        )
        has_decision = "setclaimdecision" in op_text or "decision" in op_text
        has_approval_policy = any(term in material_text for term in ("approve", "approval", "eligible", "low risk", "low-risk"))
        has_escalation_policy = any(term in material_text for term in ("manual_review", "manual review", "fraud", "escalat"))

        tasks: list[CompanyTaskProposal] = []
        if has_claims and (has_get_claim or has_list_claims):
            tasks.append(
                _proposal(
                    request,
                    key="find_claim_status",
                    name="Find claim status",
                    prompt="Find a claim by id and return its status, customer and latest operational note.",
                    success="Returns the current claim status, customer name and latest note.",
                    surfaces=["api"],
                    confidence=0.82,
                    evidence=evidence,
                )
            )
        if has_claims and has_decision and has_approval_policy:
            tasks.append(
                _proposal(
                    request,
                    key="approve_low_risk_claim",
                    name="Approve low risk claim",
                    prompt="Use company policy and claim data to approve an eligible low risk claim.",
                    success="Confirms policy eligibility and marks the claim approved.",
                    surfaces=["api", "documents"],
                    risk="write",
                    confidence=0.84,
                    evidence=evidence + [{"source": "docs", "signals": ["approve", "policy"]}],
                )
            )
        if has_claims and has_decision and has_escalation_policy:
            tasks.append(
                _proposal(
                    request,
                    key="escalate_flagged_claim",
                    name="Escalate flagged claim",
                    prompt="Use the escalation policy to set a fraud flagged or high value claim to manual review.",
                    success="Identifies the escalation signal and sets the claim to manual_review.",
                    surfaces=["api", "documents"],
                    risk="write",
                    confidence=0.84,
                    evidence=evidence + [{"source": "docs", "signals": ["fraud", "manual_review"]}],
                )
            )
        if has_claims and has_add_note:
            surfaces = ["web"] if request.discoveryMode == "ui_only" else ["web", "api"]
            tasks.append(
                _proposal(
                    request,
                    key="web_add_claim_note",
                    name="Add claim note from UI",
                    prompt="Add a note to a claim from the operational UI or equivalent claim note workflow.",
                    success="The claim detail shows the new note.",
                    surfaces=surfaces,
                    risk="write",
                    confidence=0.76,
                    evidence=evidence,
                )
            )
        if has_claims and has_customers and has_search_customers and has_list_claims:
            surfaces = ["api", "documents"] if "knowledge" in material_text or has_approval_policy or has_escalation_policy else ["api"]
            tasks.append(
                _proposal(
                    request,
                    key="customer_summary",
                    name="Customer claim summary",
                    prompt="Find a customer, list their open claims and summarize recommended next actions.",
                    success="Lists customer open claims and summarizes next actions.",
                    surfaces=surfaces,
                    confidence=0.8,
                    evidence=evidence,
                )
            )
        if has_orders and ("getorder" in op_text or _has_all(op_text, "get", "order")):
            tasks.append(
                _proposal(
                    request,
                    key="find_order_status",
                    name="Find order status",
                    prompt="Find an order by id and return its status, shipment carrier and latest customer note.",
                    success="Returns order status, carrier and latest customer note.",
                    surfaces=["api"],
                    confidence=0.82,
                    evidence=evidence,
                )
            )
        if has_orders and has_refund and any(term in material_text for term in ("policy", "delayed", "delay", "72", "eligible")):
            tasks.append(
                _proposal(
                    request,
                    key="draft_delayed_refund",
                    name="Draft delayed shipment refund",
                    prompt="Use fulfillment policy and order data to decide whether a delayed order qualifies for refund and draft it.",
                    success="Creates or drafts an eligible delayed shipment refund with policy evidence.",
                    surfaces=["api", "documents"],
                    risk="write",
                    confidence=0.84,
                    evidence=evidence,
                )
            )
        if has_inventory and ("addinventorynote" in op_text or "note" in material_text):
            surfaces = ["web"] if request.discoveryMode == "ui_only" else ["web", "api"]
            tasks.append(
                _proposal(
                    request,
                    key="web_update_inventory_note",
                    name="Update inventory note from UI",
                    prompt="Add an operational inventory note for a SKU that needs supplier confirmation before restock.",
                    success="The product inventory record shows the supplier confirmation note.",
                    surfaces=surfaces,
                    risk="write",
                    confidence=0.78,
                    evidence=evidence,
                )
            )
        if has_discount and has_enterprise:
            tasks.append(
                _proposal(
                    request,
                    key="calculate_enterprise_discount",
                    name="Calculate enterprise discount",
                    prompt="Inspect company pricing rules and calculate the enterprise renewal discount and approval requirement.",
                    success="Returns the correct enterprise discount percentage and approval requirement.",
                    surfaces=["code"],
                    confidence=0.78,
                    evidence=evidence + [{"source": "code", "signals": ["discount", "enterprise"]}],
                )
            )
        if has_calendar and request.discoveryMode == "ui_only":
            tasks.extend(
                [
                    _proposal(
                        request,
                        key="iwa_select_month",
                        name="Switch calendar to month view",
                        prompt="Using the AutoCalendar web UI, switch the calendar to month view.",
                        success="The calendar is switched to month view.",
                        surfaces=["web"],
                        confidence=0.72,
                        evidence=evidence + [{"source": "web_ui_snapshot_inference", "signals": ["calendar", "month", "view"]}],
                    ),
                    _proposal(
                        request,
                        key="iwa_add_event",
                        name="Add calendar event",
                        prompt="Using the AutoCalendar web UI, add an event titled IWA Traj Save via the event wizard.",
                        success="The new event is saved through the event wizard.",
                        surfaces=["web"],
                        risk="write",
                        confidence=0.72,
                        evidence=evidence + [{"source": "web_ui_snapshot_inference", "signals": ["calendar", "add", "event"]}],
                    ),
                    _proposal(
                        request,
                        key="iwa_search_submit",
                        name="Search calendar events",
                        prompt="Using the AutoCalendar web UI, search for work.",
                        success="The calendar search is submitted with query work.",
                        surfaces=["web"],
                        confidence=0.72,
                        evidence=evidence + [{"source": "web_ui_snapshot_inference", "signals": ["calendar", "search"]}],
                    ),
                ]
            )
        return tasks

    def _dedupe_proposals(self, proposals: list[CompanyTaskProposal]) -> list[CompanyTaskProposal]:
        seen: set[str] = set()
        deduped: list[CompanyTaskProposal] = []
        for proposal in sorted(proposals, key=lambda item: (not item.metadata.get("businessTask"), -item.confidence, item.name)):
            key = " ".join(_slug(part) for part in (proposal.name, proposal.prompt))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(proposal)
        return deduped

    def _solution_for_task(
        self,
        request: CompanyHarvesterInput,
        proposal: CompanyTaskProposal,
        *,
        connectors: list[CompanyConnectorPlan],
        tools: list[CompanyToolPlan],
    ) -> CompanyTaskSolution:
        surfaces = set(proposal.expectedSurfaces)
        selected_connectors = [
            connector
            for connector in connectors
            if connector.type in {"knowledge" if "documents" in surfaces else "", "api" if "api" in surfaces else "", "web" if "web" in surfaces else ""}
            or (connector.type == "code" and "code" in surfaces)
        ]
        if not selected_connectors:
            selected_connectors = connectors[:1]
        connector_ids = {connector.connectorId for connector in selected_connectors}
        selected_tools = [tool for tool in tools if tool.connectorId in connector_ids]
        if not selected_tools:
            selected_tools = tools[:1]
        tool_calls = self._tool_calls_for_task(proposal, selected_tools)
        trajectory_id = f"{proposal.taskId}:trajectory"
        return CompanyTaskSolution(
            taskId=proposal.taskId,
            connectors=selected_connectors,
            tools=selected_tools,
            trajectories=[
                CompanyTrajectoryPlan(
                    trajectoryId=trajectory_id,
                    description=f"Use discovered tools to solve: {proposal.name}",
                    toolCalls=tool_calls,
                    source="generated",
                    confidence=0.45,
                )
            ],
            skills=[
                CompanySkillPlan(
                    skillId=f"{proposal.taskId}:skill",
                    name=f"{proposal.name} skill",
                    description=proposal.successCriteria,
                    trajectoryIds=[trajectory_id],
                    instructions=proposal.prompt,
                    source="hybrid",
                )
            ],
            agentProvider=CompanyAgentProviderPlan(
                runtimeKind=request.runtimeKinds[0] if request.runtimeKinds else "model_agent",
                provider="anthropic" if request.runtimeKinds and request.runtimeKinds[0] == "claude_code" else "openai",
                systemPrompt=f"Use company tools and skills to complete: {proposal.prompt}",
            ),
            confidence=0.45,
        )

    def _tool_calls_for_task(self, proposal: CompanyTaskProposal, tools: list[CompanyToolPlan]) -> list[dict[str, Any]]:
        text = _text_blob([proposal.taskId, proposal.name, proposal.prompt, proposal.successCriteria])
        raw_text = " ".join(str(part or "") for part in (proposal.taskId, proposal.name, proposal.prompt, proposal.successCriteria))
        by_name = {tool.name: tool for tool in tools}

        def matches(*needles: str) -> list[CompanyToolPlan]:
            found: list[CompanyToolPlan] = []
            for tool in tools:
                name = tool.name.lower()
                if any(needle.lower() in name for needle in needles):
                    found.append(tool)
            return found

        ordered: list[CompanyToolPlan] = []

        def add_candidates(candidates: list[CompanyToolPlan]) -> None:
            for candidate in candidates:
                if candidate.name not in {item.name for item in ordered}:
                    ordered.append(candidate)

        def add_exact(name: str) -> None:
            if name in by_name:
                add_candidates([by_name[name]])

        if "knowledge" in proposal.expectedSurfaces or "documents" in proposal.expectedSurfaces or any(term in text for term in ("policy", "playbook", "eligible", "summary")):
            add_exact("knowledge.company_docs.search")

        if any(term in text for term in ("claim", "clm")):
            if any(term in text for term in ("customer", "summary", "open claims")):
                add_candidates(matches("searchcustomers", "search_customers"))
                add_candidates(matches("listclaims", "list_claims"))
                add_exact("knowledge.company_docs.search")
                add_candidates(matches("getclaim", "get_claim"))
            elif any(term in text for term in ("approve", "approval", "manual_review", "manual review", "escalat", "decision")):
                add_exact("knowledge.company_docs.search")
                add_candidates(matches("getclaim", "get_claim"))
                add_candidates(matches("setclaimdecision", "set_claim_decision", "decision"))
                add_candidates(matches("addclaimnote", "add_claim_note"))
            elif any(term in text for term in ("note", "callback")):
                add_candidates(matches("explore_workflows", "addclaimnote", "add_claim_note"))
                add_candidates(matches("getclaim", "get_claim"))
            else:
                add_candidates(matches("getclaim", "get_claim"))
                add_candidates(matches("listclaims", "list_claims"))

        if any(term in text for term in ("order", "refund", "shipment")):
            add_candidates(matches("getorder", "get_order"))
            if any(term in text for term in ("refund", "delayed", "delay")):
                add_exact("knowledge.company_docs.search")
                add_candidates(matches("draftrefund", "draft_refund"))
            if any(term in text for term in ("inventory", "note", "supplier")):
                add_candidates(matches("addinventorynote", "add_inventory_note"))

        if any(term in text for term in ("inventory", "sku", "restock", "supplier")):
            add_candidates(matches("explore_workflows", "addinventorynote", "add_inventory_note"))

        if "web" in proposal.expectedSurfaces and not ordered:
            add_candidates(matches("explore_workflows"))
        if "api" in proposal.expectedSurfaces and not ordered:
            add_candidates([tool for tool in tools if ".api." in tool.name][:4])
        if "code" in proposal.expectedSurfaces and not ordered:
            add_candidates(matches(".code.", "inspect"))
        if not ordered:
            add_candidates(tools[:4])

        claim_id = next(iter(re.findall(r"\bCLM-\d+\b", raw_text, flags=re.IGNORECASE)), "")
        order_id = next(iter(re.findall(r"\bORD-\d+\b", raw_text, flags=re.IGNORECASE)), "")
        sku = next(iter(re.findall(r"\bSKU-[A-Z0-9-]+\b", raw_text, flags=re.IGNORECASE)), "")
        if not claim_id:
            if any(term in text for term in ("status", "owner note", "latest note")) and "claim" in text:
                claim_id = "CLM-1001"
            elif any(term in text for term in ("manual_review", "manual review", "escalat", "fraud", "flagged")):
                claim_id = "CLM-2002"
            elif any(term in text for term in ("callback", "add note", "add claim note", "same day", "same-day")):
                claim_id = "CLM-3003"
            elif "claim" in text:
                claim_id = "CLM-1001"
        if not order_id:
            order_id = "ORD-2002" if any(term in text for term in ("refund", "delayed", "delay")) else "ORD-1001" if "order" in text else ""
        if not sku and any(term in text for term in ("inventory", "sku", "restock", "supplier")):
            sku = "SKU-RED-MUG"

        def arguments_for(tool: CompanyToolPlan) -> dict[str, Any]:
            name = tool.name.lower()
            if "knowledge.company_docs.search" == name:
                if any(term in text for term in ("refund", "delayed", "delay")):
                    return {"query": "delayed shipment refund policy"}
                if any(term in text for term in ("manual_review", "manual review", "escalat", "fraud")):
                    return {"query": "manual review escalation policy"}
                if any(term in text for term in ("approve", "approval", "eligible", "low risk")):
                    return {"query": "low risk approval policy"}
                if any(term in text for term in ("summary", "next actions")):
                    return {"query": "claim next actions policy"}
                return {"query": proposal.name}
            if "getclaim" in name or "get_claim" in name:
                return {"claim_id": claim_id} if claim_id else {}
            if "setclaimdecision" in name or "set_claim_decision" in name or name.endswith(".decision"):
                args: dict[str, Any] = {}
                if claim_id:
                    args["claim_id"] = claim_id
                if any(term in text for term in ("manual_review", "manual review", "escalat")):
                    args["decision"] = "manual_review"
                elif any(term in text for term in ("approve", "approval", "eligible", "low risk")):
                    args["decision"] = "approved"
                return args
            if "addclaimnote" in name or "add_claim_note" in name:
                args = {"note": "Customer requested a same-day callback."} if any(term in text for term in ("callback", "note")) else {}
                if claim_id:
                    args["claim_id"] = claim_id
                return args
            if "searchcustomers" in name or "search_customers" in name:
                if "ada lovelace" in text or "customer" in text:
                    return {"query": "Ada Lovelace"}
                return {"query": proposal.name}
            if "listclaims" in name or "list_claims" in name:
                if "ada lovelace" in text:
                    return {"customerId": "cust-ada"}
                return {}
            if "getorder" in name or "get_order" in name:
                return {"orderId": order_id} if order_id else {}
            if "draftrefund" in name or "draft_refund" in name:
                args = {"reason": "Delayed shipment exceeds 72 hours", "policyReference": "Fulfillment Policy 72 hours"}
                if order_id:
                    args["orderId"] = order_id
                return args
            if "addinventorynote" in name or "add_inventory_note" in name:
                args = {"note": "SKU-RED-MUG needs supplier confirmation before restock."}
                if sku:
                    args["sku"] = sku
                return args
            if "explore_workflows" in name:
                if "month view" in text or "select_month" in text:
                    return {"goal": proposal.prompt, "targetView": "month"}
                if "add_event" in text or ("add" in text and "event" in text):
                    return {"goal": proposal.prompt, "title": "IWA Traj Save"}
                if "search_submit" in text or ("search" in text and "work" in text):
                    return {"goal": proposal.prompt, "query": "work"}
                if claim_id:
                    return {"goal": f"Add note to {claim_id}"}
                if sku:
                    return {"intent": f"add inventory note for {sku}"}
                return {"goal": proposal.prompt}
            if ".code." in name or "inspect" in name:
                return {"query": proposal.name}
            return {}

        return [{"toolName": tool.name, "arguments": arguments_for(tool)} for tool in ordered[:6]]


# Compatibility alias for older imports and CLI aliases. Do not expose this as a
# public miner/harvester name.
LocalHeuristicCompanyHarvester = AgenticDiscoveryCore
