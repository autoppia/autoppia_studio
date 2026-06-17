from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.database import harvester_runs_collection, tools_collection, trajectories_collection
from app.harvesters.toolkit import ToolkitHarvester
from app.services.skills import approve_trajectory_as_skill


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_") or "tool"


@dataclass(frozen=True)
class CapabilityDiscoveryContext:
    agent_config: dict[str, Any]
    connectors: list[dict[str, Any]]
    mode: str = "task_scoped"
    target_tasks: list[dict[str, Any]] | None = None

    @property
    def broad(self) -> bool:
        return self.mode == "broad_autodiscovery"

    @property
    def tasks(self) -> list[dict[str, Any]]:
        if self.target_tasks is not None:
            return self.target_tasks
        tasks = self.agent_config.get("tasks") if isinstance(self.agent_config.get("tasks"), list) else []
        return [task for task in tasks if isinstance(task, dict)]


class CapabilityDiscoverer(Protocol):
    name: str
    version: str

    async def discover(self, context: CapabilityDiscoveryContext) -> dict[str, Any]:
        ...


def _input_has_required_fields(tool: dict[str, Any]) -> bool:
    schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    required = schema.get("required")
    return bool(required)


def _is_safe_atomic_skill(tool: dict[str, Any]) -> bool:
    side_effects = str(tool.get("sideEffects") or "reads").lower()
    status = str(tool.get("status") or "").lower()
    risk = str(tool.get("riskLevel") or "low").lower()
    execution_type = str(tool.get("executionType") or "").lower()
    name = str(tool.get("name") or "")
    return (
        status == "ready"
        and side_effects == "reads"
        and risk in {"low", ""}
        and not _input_has_required_fields(tool)
        and execution_type not in {"browser_action"}
        and not name.startswith(("browser.", "web."))
        and bool(name)
    )


def _task_text(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    hints = metadata.get("hints") if isinstance(metadata.get("hints"), list) else []
    return "\n".join(
        [
            str(task.get("name") or ""),
            str(task.get("prompt") or ""),
            str(task.get("successCriteria") or ""),
            " ".join(str(item) for item in hints),
            " ".join(str(item) for item in metadata.get("expectedArtifacts") or []),
        ]
    ).lower()


def _tool_relevance(tool: dict[str, Any], tasks: list[dict[str, Any]], *, broad: bool) -> dict[str, Any]:
    name = str(tool.get("name") or "").lower()
    if broad or not tasks:
        return {"relevant": True, "score": 1.0, "reason": "broad_discovery" if broad else "no_target_tasks"}

    text = "\n".join(_task_text(task) for task in tasks)
    if not text.strip():
        return {"relevant": True, "score": 0.5, "reason": "empty_task_text"}
    if name.startswith(("browser.", "web.")):
        return {"relevant": True, "score": 0.6, "reason": "base_web_tool_for_task_scoped_harvest"}
    if "latest_bulletin_pdf" in name and any(token in text for token in ("pdf", "download", "descargar", "descarreg", "baixar", "bolet", "butllet", "bulletin")):
        return {"relevant": True, "score": 0.95, "reason": "matches_latest_pdf_task"}
    if "latest_bulletin" in name and "pdf" not in name and "pdf" in text:
        return {"relevant": False, "score": 0.0, "reason": "pdf_task_prefers_pdf_tool"}
    if "latest_bulletin" in name and any(token in text for token in ("latest", "ultimo", "último", "recent", "bolet", "butllet", "bulletin")):
        return {"relevant": True, "score": 0.8, "reason": "matches_latest_bulletin_task"}
    if "list_bulletins" in name and "pdf" in text and not any(token in text for token in ("listar", "list ", "month", "mes ", "varios", "todos")):
        return {"relevant": False, "score": 0.0, "reason": "pdf_task_prefers_pdf_tool"}
    if "list_bulletins" in name and any(token in text for token in ("listar", "list ", "month", "mes ", "varios", "todos")):
        return {"relevant": True, "score": 0.75, "reason": "matches_list_task"}
    return {"relevant": False, "score": 0.0, "reason": "not_relevant_to_target_tasks"}


def _tool_evidence(*, tool: dict[str, Any], connector: dict[str, Any], discoverer: str, version: str, relevance: dict[str, Any]) -> list[dict[str, Any]]:
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    return [
        {
            "kind": "connector_toolkit",
            "source": "connector_toolkit",
            "connectorId": connector.get("connectorId", ""),
            "connectorName": connector.get("name", ""),
            "connectorType": connector.get("type", ""),
            "baseUrl": config.get("baseUrl") or config.get("startUrl") or "",
            "toolName": tool.get("name", ""),
            "discovererName": discoverer,
            "discovererVersion": version,
            "relevance": relevance,
            "observedAt": now_iso(),
        }
    ]


async def _upsert_tool(tool: dict[str, Any]) -> dict[str, Any]:
    existing = await tools_collection.find_one({"toolId": tool["toolId"]}, {"_id": 0})
    tool["createdAt"] = existing.get("createdAt") if existing else tool.get("createdAt", now_iso())
    tool["updatedAt"] = now_iso()
    await tools_collection.update_one({"toolId": tool["toolId"]}, {"$set": tool}, upsert=True)
    return tool


async def _ensure_atomic_tool_skill(*, agent_config: dict[str, Any], tool: dict[str, Any], discoverer: str, version: str) -> str:
    agent_id = str(agent_config.get("agentId") or "")
    company_id = str(agent_config.get("companyId") or tool.get("companyId") or "")
    email = str(agent_config.get("email") or tool.get("email") or "")
    tool_name = str(tool.get("name") or "")
    trajectory_id = f"{agent_id}:discover:{slug(tool_name)}"
    task_name = str(tool.get("displayName") or tool_name.split(".")[-1].replace("_", " ").title())
    now = now_iso()
    judge = {
        "label": "pass",
        "confidence": 0.95,
        "reason": f"{discoverer}@{version} promoted a deterministic read-only connector tool.",
        "evidence": [tool_name],
    }
    trajectory = {
        "trajectoryId": trajectory_id,
        "agentId": agent_id,
        "companyId": company_id,
        "email": email,
        "connectorIds": [tool.get("connectorId")] if tool.get("connectorId") else [],
        "toolIds": [tool.get("toolId")] if tool.get("toolId") else [],
        "runtimeRequirements": [str(item) for item in tool.get("runtimeRequirements") or [] if item],
        "taskName": task_name,
        "prompt": str(tool.get("description") or f"Use {tool_name}."),
        "successCriteria": "The connector tool executes successfully and returns structured output.",
        "source": "capability_discoverer",
        "status": "approved",
        "actions": [{"tool": tool_name, "args": {}}],
        "trajectory": [{"name": tool_name, "arguments": {}}],
        "steps": [{"name": tool_name, "arguments": {}}],
        "metadata": {
            "discoveredBy": discoverer,
            "discovererVersion": version,
            "discoveryKind": "atomic_read_tool_skill",
        },
        "harvester": {
            "adapter": discoverer,
            "version": version,
            "status": "success",
            "confidence": 0.95,
            "summary": "Deterministic read-only tool promoted as an atomic reusable skill.",
        },
        "judge": judge,
        "needsHumanReview": False,
        "createdAt": now,
        "updatedAt": now,
    }
    existing = await trajectories_collection.find_one({"trajectoryId": trajectory_id}, {"_id": 0})
    if existing:
        trajectory["createdAt"] = existing.get("createdAt", now)
    await trajectories_collection.update_one({"trajectoryId": trajectory_id}, {"$set": trajectory}, upsert=True)
    return await approve_trajectory_as_skill(trajectory, judge=judge)


class DefaultToolkitDiscoverer:
    name = "default_toolkit_discoverer"
    version = "v1"

    async def discover(self, context: CapabilityDiscoveryContext) -> dict[str, Any]:
        now = now_iso()
        run_id = str(uuid.uuid4())
        agent_config = context.agent_config
        await harvester_runs_collection.insert_one(
            {
                "harvesterRunId": run_id,
                "runKind": "capability_discovery",
                "agentId": agent_config.get("agentId", ""),
                "companyId": agent_config.get("companyId", ""),
                "email": agent_config.get("email", ""),
                "harvesterType": self.name,
                "discovererName": self.name,
                "discovererVersion": self.version,
                "mode": context.mode,
                "targetTasks": [
                    {
                        "name": task.get("name", ""),
                        "prompt": task.get("prompt", ""),
                        "successCriteria": task.get("successCriteria", ""),
                        "metadata": task.get("metadata", {}),
                    }
                    for task in context.tasks
                ],
                "status": "running",
                "logs": [f"{self.name}@{self.version} started in {context.mode} mode."],
                "errors": [],
                "createdAt": now,
                "updatedAt": now,
            }
        )
        published_tools: list[dict[str, Any]] = []
        created_skills: list[str] = []
        logs: list[str] = []
        errors: list[str] = []

        for connector in context.connectors:
            try:
                provider = str(connector.get("provider") or "official").lower()
                connector_type = str(connector.get("type") or "").lower()
                if connector_type == "api" and provider == "custom":
                    logs.append(f"Skipped custom API connector {connector.get('name')}: requires specialized API/OpenAPI discovery.")
                    continue
                result = await ToolkitHarvester(f"{self.name}@{self.version}", source="capability_discovery").harvest(connector)
                for tool in result.get("tools", []):
                    relevance = _tool_relevance(tool, context.tasks, broad=context.broad)
                    if not relevance["relevant"]:
                        logs.append(f"Skipped {tool.get('name')}: {relevance['reason']}.")
                        continue
                    tool["discovererName"] = self.name
                    tool["discovererVersion"] = self.version
                    tool["discoveryScope"] = context.mode
                    tool["discoveryRelevance"] = relevance
                    tool["discoveryEvidence"] = _tool_evidence(
                        tool=tool,
                        connector=connector,
                        discoverer=self.name,
                        version=self.version,
                        relevance=relevance,
                    )
                    persisted = await _upsert_tool(tool)
                    published_tools.append(persisted)
                    if context.broad and _is_safe_atomic_skill(persisted):
                        skill_id = await _ensure_atomic_tool_skill(
                            agent_config=agent_config,
                            tool=persisted,
                            discoverer=self.name,
                            version=self.version,
                        )
                        created_skills.append(skill_id)
                logs.extend(result.get("logs") or [])
            except Exception as exc:
                errors.append(f"{connector.get('name') or connector.get('connectorId')}: {exc}")

        status = "completed" if not errors else "completed_with_errors" if published_tools or created_skills else "failed"
        await harvester_runs_collection.update_one(
            {"harvesterRunId": run_id},
            {
                "$set": {
                    "status": status,
                    "completedAt": now_iso(),
                    "updatedAt": now_iso(),
                    "discoveredTools": len(published_tools),
                    "generatedSkills": len(created_skills),
                    "errors": errors,
                },
                "$push": {"logs": {"$each": logs}},
            },
        )
        return {
            "discovererName": self.name,
            "discovererVersion": self.version,
            "mode": context.mode,
            "runId": run_id,
            "status": status,
            "tools": published_tools,
            "skills": created_skills,
            "targetTasks": [
                {
                    "name": task.get("name", ""),
                    "prompt": task.get("prompt", ""),
                    "successCriteria": task.get("successCriteria", ""),
                    "metadata": task.get("metadata", {}),
                }
                for task in context.tasks
            ],
            "logs": logs,
            "errors": errors,
        }


DISCOVERERS: dict[str, CapabilityDiscoverer] = {
    "default_toolkit:v1": DefaultToolkitDiscoverer(),
}


def default_discoverer_name() -> str:
    return "default_toolkit:v1"


def get_capability_discoverer(name: str | None = None) -> CapabilityDiscoverer:
    key = (name or default_discoverer_name()).strip()
    return DISCOVERERS.get(key) or DISCOVERERS[default_discoverer_name()]


def list_capability_discoverers() -> list[dict[str, str]]:
    return [
        {"name": key, "discovererName": value.name, "version": value.version, "status": "available"}
        for key, value in sorted(DISCOVERERS.items())
    ]


async def run_capability_discovery(agent_config: dict[str, Any], connectors: list[dict[str, Any]]) -> dict[str, Any]:
    discovery = agent_config.get("capabilityDiscovery") if isinstance(agent_config.get("capabilityDiscovery"), dict) else {}
    mode = str(discovery.get("mode") or "task_scoped")
    discoverer_name = str(
        discovery.get("discoverer")
        or agent_config.get("capabilityDiscoverer")
        or default_discoverer_name()
    )
    discoverer = get_capability_discoverer(discoverer_name)
    return await discoverer.discover(
        CapabilityDiscoveryContext(
            agent_config=agent_config,
            connectors=connectors,
            mode=mode,
            target_tasks=agent_config.get("tasks") if isinstance(agent_config.get("tasks"), list) else [],
        )
    )
