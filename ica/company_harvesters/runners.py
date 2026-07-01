from __future__ import annotations

from typing import Any, Protocol

from app.company_harvesters import get_company_harvester
from app.services import company_harvester
from ica.company_harvesters.schemas import CompanyHarvesterInput, CompanyHarvesterOutput, CompanyMaterial
from ica.demo_companies.materializer import materialize_project
from ica.schemas import IcaBenchmarkModeKind, IcaDemoProject, IcaMaterializedProject


class IcaCompanyHarvestRunner(Protocol):
    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
        include_ground_truth_tasks: bool = False,
    ) -> dict[str, Any]:
        ...


async def _cursor_to_list(cursor: Any, length: int = 1000) -> list[dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return [dict(item) for item in await cursor.to_list(length=length)]
    return [dict(item) for item in cursor]


async def _company_harvest_snapshot(company_id: str, intake_id: str) -> dict[str, list[dict[str, Any]]]:
    connectors = await _cursor_to_list(company_harvester.connectors_collection.find({"companyId": company_id}))
    connector_ids = [str(item.get("connectorId") or "") for item in connectors if item.get("connectorId")]
    tools = await _cursor_to_list(company_harvester.tools_collection.find({"connectorId": {"$in": connector_ids}})) if connector_ids else []
    connectors = [_normalize_connector_origin(connector) for connector in connectors]
    connector_type_by_id = {str(connector.get("connectorId") or ""): str(connector.get("type") or "") for connector in connectors}
    tools = [_normalize_tool_origin(tool, connector_type_by_id.get(str(tool.get("connectorId") or ""), "")) for tool in tools]
    benchmarks = await _cursor_to_list(company_harvester.benchmarks_collection.find({"companyId": company_id}))
    benchmark_ids = [str(item.get("benchmarkId") or "") for item in benchmarks if item.get("benchmarkId")]
    tasks = await _cursor_to_list(company_harvester.benchmark_tasks_collection.find({"benchmarkId": {"$in": benchmark_ids}})) if benchmark_ids else []
    return {
        "connectors": connectors,
        "tools": tools,
        "benchmarks": benchmarks,
        "tasks": tasks,
        "intakes": await _cursor_to_list(company_harvester.company_intakes_collection.find({"intakeId": intake_id})),
    }


def _normalize_connector_origin(connector: dict[str, Any]) -> dict[str, Any]:
    if connector.get("origin"):
        return connector
    connector_type = str(connector.get("type") or "")
    generation_status = str(connector.get("generationStatus") or "")
    if connector_type == "api" and "docs" in generation_status:
        origin = "derived_from_openapi"
    elif connector_type == "code":
        origin = "derived_from_code"
    elif connector_type in {"web", "knowledge"}:
        origin = "existing"
    else:
        origin = "proposed_custom"
    return {
        **connector,
        "origin": origin,
        "evidence": connector.get("evidence") or [{"source": connector.get("source") or "company_harvester", "generationStatus": generation_status}],
    }


def _normalize_tool_origin(tool: dict[str, Any], connector_type: str) -> dict[str, Any]:
    if tool.get("origin"):
        return tool
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    if connector_type == "api" or metadata.get("openapiPath"):
        origin = "derived_from_openapi"
    elif connector_type == "code" or ".code." in str(tool.get("name") or ""):
        origin = "derived_from_code"
    elif connector_type in {"web", "knowledge"}:
        origin = "existing_connector_tool"
    else:
        origin = "proposed_custom"
    return {
        **tool,
        "origin": origin,
        "evidence": tool.get("evidence") or [{"source": tool.get("source") or "company_harvester", "connectorType": connector_type, **metadata}],
    }


class CompanyHarvesterIcaRunner:
    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
        include_ground_truth_tasks: bool = False,
    ) -> dict[str, Any]:
        materialized = materialize_project(
            project,
            base_url=base_url,
            mode=mode,
            include_ground_truth_tasks=include_ground_truth_tasks,
            collect_web_snapshots=not include_ground_truth_tasks and mode == "web_only",
        )
        intake = await company_harvester.create_company_intake(
            email=email,
            company_id=company_id,
            company_name=project.name,
            description=project.description,
            materials=materialized.materials,
            user_tasks=materialized.userTasks,
            mode="dev",
        )
        run = await company_harvester.start_company_harvest(intake["intakeId"], email=email, mode="dev")
        if process:
            run = await company_harvester.process_company_harvest_run(run["runId"])
        snapshot = await _company_harvest_snapshot(company_id, intake["intakeId"])
        return {
            "project": project.model_dump(),
            "materialized": materialized.model_dump(),
            "intake": intake,
            "run": run,
            "snapshot": snapshot,
            "expectedHarvest": materialized.expectedHarvest.model_dump(),
        }


def _discovery_mode_for(mode: IcaBenchmarkModeKind | None) -> str:
    return {
        "web_only": "ui_only",
        "api_only": "ui_api_docs",
        "code_only": "code_only",
        "web_code": "ui_code",
        "api_code": "api_code",
        "web_api": "ui_api",
        "web_docs": "full_company",
        "api_docs": "ui_api_docs",
        "code_docs": "full_company",
        "web_api_code": "full_company",
        "web_api_docs": "ui_api_docs",
        "web_code_docs": "full_company",
        "api_code_docs": "full_company",
        "all_sources": "full_company",
        "hybrid": "ui_api_docs",
    }.get(str(mode or ""), "full_company")


def _company_harvester_input_from_materialized(
    materialized: IcaMaterializedProject,
    *,
    company_id: str,
    include_ground_truth_tasks: bool = False,
) -> CompanyHarvesterInput:
    available_inventory = _available_inventory_for_materialized(materialized)
    return CompanyHarvesterInput(
        companyId=company_id,
        companyName=materialized.project.name,
        description=materialized.project.description,
        materials=[CompanyMaterial.model_validate(material) for material in materialized.materials],
        discoveryMode=_discovery_mode_for(materialized.mode),  # type: ignore[arg-type]
        userTasks=materialized.userTasks if include_ground_truth_tasks else [],
        availableInventory=available_inventory,
        metadata={
            "icaProjectId": materialized.project.projectId,
            "icaMode": materialized.mode or "",
        },
    )


def _available_inventory_for_materialized(materialized: IcaMaterializedProject) -> dict[str, Any]:
    surface_kinds = {str(material.get("kind") or "") for material in materialized.materials}
    connectors: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    runtimes = [
        {"runtimeKind": "model_agent", "provider": "openai"},
        {"runtimeKind": "claude_code", "provider": "anthropic"},
        {"runtimeKind": "codex", "provider": "openai"},
    ]
    if "website" in surface_kinds:
        connectors.append({"connectorId": "builtin.browser", "name": "Browser", "type": "web", "origin": "existing", "surface": "webapp"})
        tools.append({"toolId": "builtin.browser.explore_workflows", "name": f"{materialized.project.projectId}.web.explore_workflows", "connectorId": "builtin.browser", "origin": "existing_connector_tool"})
    if {"openapi", "api_docs"} & surface_kinds:
        connectors.append({"connectorId": "builtin.openapi", "name": "OpenAPI Connector Factory", "type": "api", "origin": "existing", "surface": "api"})
    if {"document_url", "file", "knowledge_note"} & surface_kinds:
        connectors.append({"connectorId": "builtin.knowledge", "name": "Company Knowledge", "type": "knowledge", "origin": "existing", "surface": "knowledge"})
        tools.append({"toolId": "builtin.knowledge.search", "name": "knowledge.company_docs.search", "connectorId": "builtin.knowledge", "origin": "existing_connector_tool"})
    if {"code_repository", "code_file"} & surface_kinds:
        connectors.append({"connectorId": "builtin.code_reader", "name": "Source Code Reader", "type": "code", "origin": "existing", "surface": "code"})
        tools.append({"toolId": "builtin.code.inspect", "name": f"{materialized.project.projectId}.code.inspect", "connectorId": "builtin.code_reader", "origin": "existing_connector_tool"})
    return {"connectors": connectors, "tools": tools, "runtimes": runtimes}


def _snapshot_from_company_harvester_output(output: CompanyHarvesterOutput) -> dict[str, list[dict[str, Any]]]:
    connector_docs = {
        connector.connectorId or connector.name or f"connector:{index}": {
            "connectorId": connector.connectorId or connector.name or f"connector:{index}",
            "name": connector.name,
            "type": connector.type,
            "origin": connector.origin,
            "existingConnectorId": connector.existingConnectorId,
            "surface": connector.surface,
            "authRequired": connector.authRequired,
            "runtimeRequirements": connector.runtimeRequirements,
            "evidence": connector.evidence,
            "customConnectorCode": connector.customConnectorCode.model_dump(mode="json") if connector.customConnectorCode else None,
            "source": "company_harvester_output",
        }
        for index, solution in enumerate(output.taskSolutions, start=1)
        for connector in solution.connectors
    }
    tool_docs = {
        tool.toolId or tool.name: {
            "toolId": tool.toolId or tool.name,
            "name": tool.name,
            "origin": tool.origin,
            "existingToolId": tool.existingToolId,
            "connectorId": tool.connectorId,
            "executionType": tool.executionType,
            "policyBoundary": tool.policyBoundary,
            "riskLevel": tool.riskLevel,
            "evidence": tool.evidence,
            "customToolCode": tool.customToolCode.model_dump(mode="json") if tool.customToolCode else None,
            "source": "company_harvester_output",
        }
        for solution in output.taskSolutions
        for tool in solution.tools
        if tool.name
    }
    tasks = [
        {
            "taskId": proposal.taskId,
            "name": proposal.name,
            "taskName": proposal.name,
            "prompt": proposal.prompt,
            "successCriteria": proposal.successCriteria,
            "riskClass": proposal.riskClass,
            "metadata": {
                **proposal.metadata,
                "expectedSurfaces": proposal.expectedSurfaces,
                "confidence": proposal.confidence,
                "evidence": proposal.evidence,
            },
            "source": "company_harvester_output",
        }
        for proposal in output.proposedTasks
    ]
    benchmarks = [
        {
            "benchmarkId": output.benchmarkId or "company_harvester_output:benchmark",
            "taskCount": len(tasks),
            "source": "company_harvester_output",
        }
    ] if tasks else []
    return {
        "connectors": list(connector_docs.values()),
        "tools": list(tool_docs.values()),
        "tasks": tasks,
        "benchmarks": benchmarks,
    }


class CompanyHarvesterEngineIcaRunner:
    def __init__(self, harvester_name: str = "local_heuristic") -> None:
        self.harvester_name = harvester_name

    async def run(
        self,
        project: IcaDemoProject,
        *,
        email: str,
        company_id: str,
        base_url: str = "",
        mode: IcaBenchmarkModeKind | None = None,
        process: bool = True,
        include_ground_truth_tasks: bool = False,
    ) -> dict[str, Any]:
        materialized = materialize_project(
            project,
            base_url=base_url,
            mode=mode,
            include_ground_truth_tasks=include_ground_truth_tasks,
            collect_web_snapshots=not include_ground_truth_tasks and mode == "web_only",
        )
        request = _company_harvester_input_from_materialized(
            materialized,
            company_id=company_id,
            include_ground_truth_tasks=include_ground_truth_tasks,
        )
        harvester = get_company_harvester(self.harvester_name)
        output = await harvester.harvest(request)
        snapshot = _snapshot_from_company_harvester_output(output)
        return {
            "project": project.model_dump(),
            "materialized": materialized.model_dump(),
            "intake": {"companyId": company_id, "email": email, "source": "company_harvester_engine"},
            "run": {
                "runId": f"{company_id}:{harvester.info().name}:ica",
                "status": "ready",
                "currentStep": "ready",
                "normalSummary": {
                    "companyHarvesterOutput": {
                        "proposedTaskCount": len(output.proposedTasks),
                        "taskSolutionCount": len(output.taskSolutions),
                    }
                },
                "errors": [],
            },
            "snapshot": snapshot,
            "companyHarvesterOutput": output.model_dump(mode="json"),
            "expectedHarvest": materialized.expectedHarvest.model_dump(),
        }
