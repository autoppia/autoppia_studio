from __future__ import annotations

import json
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
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name=material.name or "Company Web",
                    type="web",
                    surface="webapp",
                    authRequired=bool(material.metadata.get("authRequired")),
                    runtimeRequirements=["browser", "network"],
                    metadata={"material": material.model_dump(mode="json")},
                )
                tool_id = f"{connector_id}:explore_workflows"
                tool_name = f"{_slug(request.companyName or request.companyId)}.web.explore_workflows"
                tools[tool_name] = CompanyToolPlan(
                    toolId=tool_id,
                    name=tool_name,
                    connectorId=connector_id,
                    executionType="browser_automation",
                    policyBoundary="read",
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
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name=material.name or "Company API",
                    type="api",
                    surface="api",
                    authRequired=bool(material.metadata.get("authRequired")),
                    runtimeRequirements=["network", "api_docs_or_openapi"],
                    metadata={"material": material.model_dump(mode="json")},
                )
                material_operations = _openapi_operations(material)
                if not material_operations:
                    material_operations = ["discover_operations"]
                operations.extend(material_operations)
                for operation in material_operations:
                    tool_name = f"{tool_namespace}.api.{_slug(operation)}"
                    tools[tool_name] = CompanyToolPlan(
                        toolId=f"{connector_id}:{_slug(operation)}",
                        name=tool_name,
                        connectorId=connector_id,
                        executionType="api_call",
                        policyBoundary="write" if any(term in operation.lower() for term in ("post", "add", "set", "update", "delete", "decision")) else "read",
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
                connectors[connector_id] = CompanyConnectorPlan(
                    connectorId=connector_id,
                    name="Company Knowledge",
                    type="knowledge",
                    surface="knowledge",
                    runtimeRequirements=["vectorstore", "embedding_model"],
                )
                tools["knowledge.company_docs.search"] = CompanyToolPlan(
                    toolId=f"{connector_id}:search",
                    name="knowledge.company_docs.search",
                    connectorId=connector_id,
                    executionType="knowledge_search",
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
        ]
        if not selected_connectors:
            selected_connectors = connectors[:1]
        connector_ids = {connector.connectorId for connector in selected_connectors}
        selected_tools = [tool for tool in tools if tool.connectorId in connector_ids]
        if not selected_tools:
            selected_tools = tools[:1]
        trajectory_id = f"{proposal.taskId}:trajectory"
        return CompanyTaskSolution(
            taskId=proposal.taskId,
            connectors=selected_connectors,
            tools=selected_tools,
            trajectories=[
                CompanyTrajectoryPlan(
                    trajectoryId=trajectory_id,
                    description=f"Use discovered tools to solve: {proposal.name}",
                    toolCalls=[{"toolName": tool.name, "arguments": {}} for tool in selected_tools[:4]],
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


# Compatibility alias for older imports and CLI aliases. Do not expose this as a
# public miner/harvester name.
LocalHeuristicCompanyHarvester = AgenticDiscoveryCore
