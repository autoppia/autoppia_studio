from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.database import agents_collection, benchmark_tasks_collection, capabilities_collection, connectors_collection, tools_collection, trajectories_collection
from app.harvester.claude_cli import HarvestResult, harvest_pending_trajectories, run_claude_harvest
from app.services.iwa_modeling import canonical_tool_trajectory, internal_actions_from_trajectory, iwa_task_payload


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_") or "tool"


@dataclass(frozen=True)
class HarvestTask:
    """Task candidate to harvest into a reusable trajectory.

    Persisted records currently live in trajectories_collection because they become
    trajectories after harvest; the harvester API should treat the input as a task.
    """

    data: dict[str, Any]

    @property
    def task_id(self) -> str:
        return str(self.data.get("taskId") or self.data.get("trajectoryId") or "")

    @property
    def legacy_trajectory_id(self) -> str:
        return str(self.data.get("trajectoryId") or "")

    @property
    def task_name(self) -> str:
        return str(self.data.get("taskName") or self.data.get("name") or "")

    @property
    def prompt(self) -> str:
        return str(self.data.get("prompt") or "")

    @property
    def success_criteria(self) -> str:
        return str(self.data.get("successCriteria") or "")

    @property
    def is_legacy_trajectory_record(self) -> bool:
        return bool(self.legacy_trajectory_id and not self.data.get("taskId"))


async def _trajectory_dependencies(company_id: str, trajectory: list[dict[str, Any]]) -> dict[str, list[str]]:
    names = {str(item.get("name") or "") for item in trajectory if isinstance(item, dict)}
    tool_docs = []
    if names and company_id:
        tool_docs = await tools_collection.find({"companyId": company_id, "name": {"$in": list(names)}}, {"_id": 0}).to_list(length=100)

    connector_ids = {str(tool.get("connectorId") or "") for tool in tool_docs if tool.get("connectorId")}
    tool_ids = {str(tool.get("toolId") or "") for tool in tool_docs if tool.get("toolId")}
    requirements = {
        str(req)
        for tool in tool_docs
        for req in (tool.get("runtimeRequirements") or [])
        if req
    }

    if any(name.startswith("browser.") or name in {"navigate", "click", "input", "select_dropdown", "send_keys", "wait"} for name in names):
        requirements.add("browser")
    if any(name.startswith("bopa.") for name in names) and company_id:
        connector = await connectors_collection.find_one(
            {"companyId": company_id, "$or": [{"type": "bopa"}, {"name": {"$regex": "^BOPA$", "$options": "i"}}]},
            {"_id": 0},
        )
        if connector:
            connector_ids.add(str(connector.get("connectorId") or ""))
        requirements.add("network")

    return {
        "connectorIds": sorted(item for item in connector_ids if item),
        "toolIds": sorted(item for item in tool_ids if item),
        "runtimeRequirements": sorted(requirements),
    }


async def _upsert_discovered_tools(company_id: str, email: str, discovered_tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not company_id or not discovered_tools:
        return []
    connectors = await connectors_collection.find({"companyId": company_id}, {"_id": 0}).to_list(length=500)
    upserted: list[dict[str, Any]] = []
    for raw in discovered_tools:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        prefix = name.split(".", 1)[0].lower()
        connector = next((item for item in connectors if str(item.get("type") or "").lower() == prefix), None)
        if not connector:
            connector = next((item for item in connectors if prefix in str(item.get("name") or "").lower()), None)
        if not connector and connectors:
            connector = connectors[0]
        connector_id = str((connector or {}).get("connectorId") or "")
        tool_id = f"{connector_id}:{_slug(name)}" if connector_id else f"{company_id}:{_slug(name)}"
        doc = {
            "toolId": tool_id,
            "email": email,
            "companyId": company_id,
            "connectorId": connector_id,
            "connectorName": (connector or {}).get("name", ""),
            "name": name,
            "displayName": name.split(".")[-1].replace("_", " ").title(),
            "description": str(raw.get("description") or ""),
            "inputSchema": raw.get("inputSchema") if isinstance(raw.get("inputSchema"), dict) else {"type": "object", "properties": {}},
            "outputSchema": raw.get("outputSchema") if isinstance(raw.get("outputSchema"), dict) else {"type": "object", "additionalProperties": True},
            "executionType": str(raw.get("executionType") or "api_call"),
            "surface": str(raw.get("surface") or "api"),
            "runtimeRequirements": [str(item) for item in raw.get("runtimeRequirements") or ["network"] if item],
            "sideEffects": str(raw.get("sideEffects") or "reads"),
            "permissions": {"connectorId": connector_id, "requiresApproval": "write" in str(raw.get("sideEffects") or "").lower()},
            "riskLevel": str(raw.get("riskLevel") or "low"),
            "status": "ready",
            "source": "harvester_discovered_tool",
            "discovererName": str(raw.get("discovererName") or "task_harvester"),
            "discovererVersion": str(raw.get("discovererVersion") or ""),
            "discoveryScope": str(raw.get("discoveryScope") or "task_scoped"),
            "discoveryRelevance": raw.get("discoveryRelevance") if isinstance(raw.get("discoveryRelevance"), dict) else {},
            "discoveryEvidence": raw.get("discoveryEvidence") if isinstance(raw.get("discoveryEvidence"), list) else [],
            "updatedAt": now_iso(),
        }
        existing = await tools_collection.find_one({"toolId": tool_id}, {"_id": 0})
        if existing:
            doc["createdAt"] = existing.get("createdAt")
        else:
            doc["createdAt"] = now_iso()
        await tools_collection.update_one({"toolId": tool_id}, {"$set": doc}, upsert=True)
        upserted.append(doc)
    return upserted


class AgentHarvester(Protocol):
    name: str

    async def harvest(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        ...

    async def harvest_task(self, agent_config: dict[str, Any], task: HarvestTask) -> dict[str, Any]:
        ...

    async def harvest_one(self, agent_config: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ClaudeCliAgentHarvester:
    name: str = "claude_cli"

    async def harvest(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        return await harvest_pending_trajectories(agent_config)

    async def run_harvest(self, agent_config: dict[str, Any], task_doc: dict[str, Any]) -> HarvestResult:
        return await run_claude_harvest(agent_config, task_doc)

    async def harvest_task(self, agent_config: dict[str, Any], task: HarvestTask) -> dict[str, Any]:
        task_doc = task.data
        now = now_iso()
        if task.is_legacy_trajectory_record:
            trajectory_id = task.legacy_trajectory_id
            await trajectories_collection.update_one(
                {"trajectoryId": trajectory_id},
                {"$set": {"status": "harvesting", "source": "automata_harvester", "updatedAt": now}},
            )
        else:
            trajectory_id = str(task_doc.get("candidateTrajectoryId") or uuid.uuid4())
            await benchmark_tasks_collection.update_one(
                {"taskId": task.task_id},
                {"$set": {"status": "harvesting", "updatedAt": now}},
            )
        try:
            result = await self.run_harvest(agent_config, task_doc)
            trajectory = result.trajectory or canonical_tool_trajectory(result.actions, task_url=str(iwa_task_payload(task_doc, agent_config).get("url") or ""))
            actions = internal_actions_from_trajectory(trajectory)
            status = "harvested" if result.success and trajectory else "harvest_failed"
            company_id = str(task_doc.get("companyId") or agent_config.get("companyId", ""))
            email = str(task_doc.get("email") or agent_config.get("email", ""))
            await _upsert_discovered_tools(company_id, email, result.discovered_tools)
            dependencies = await _trajectory_dependencies(company_id, trajectory)
            trajectory_update = {
                "trajectoryId": trajectory_id,
                "taskId": task.task_id,
                "agentId": task_doc.get("agentId") or agent_config.get("agentId", ""),
                "companyId": company_id,
                "email": email,
                "webId": task_doc.get("webId", ""),
                "benchmarkId": task_doc.get("benchmarkId", ""),
                "connectorIds": dependencies["connectorIds"],
                "toolIds": dependencies["toolIds"],
                "runtimeRequirements": dependencies["runtimeRequirements"],
                "taskName": task.task_name,
                "prompt": task.prompt,
                "successCriteria": task.success_criteria,
                "source": "automata_harvester",
                "status": status,
                "actions": actions,
                "trajectory": trajectory,
                "finalUrl": result.final_url,
                "finalHtml": result.final_html,
                "screenshots": [],
                "metadata": {
                    **(task_doc.get("metadata") if isinstance(task_doc.get("metadata"), dict) else {}),
                    **({"execution_history": result.execution_history} if result.execution_history else {}),
                },
                "harvester": {
                    "adapter": self.name,
                    "status": "success" if status == "harvested" else "failed",
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "failureReason": result.failure_reason,
                    "evidence": result.evidence,
                    "notes": result.notes,
                },
                "updatedAt": now_iso(),
            }
            if task.is_legacy_trajectory_record:
                await trajectories_collection.update_one({"trajectoryId": trajectory_id}, {"$set": trajectory_update})
            else:
                await trajectories_collection.update_one(
                    {"trajectoryId": trajectory_id},
                    {"$set": trajectory_update, "$setOnInsert": {"createdAt": now_iso()}},
                    upsert=True,
                )
                await benchmark_tasks_collection.update_one(
                    {"taskId": task.task_id},
                    {"$set": {"status": status, "trajectoryId": trajectory_id, "updatedAt": now_iso()}},
                )
                await agents_collection.update_one(
                    {"agentId": task_doc.get("agentId") or agent_config.get("agentId", ""), "tasks.name": task.task_name},
                    {"$set": {"tasks.$.trajectoryId": trajectory_id, "tasks.$.status": status, "updatedAt": now_iso()}},
                )
                await agents_collection.update_one(
                    {"agentId": task_doc.get("agentId") or agent_config.get("agentId", ""), "tasks.prompt": task.prompt},
                    {"$set": {"tasks.$.trajectoryId": trajectory_id, "tasks.$.status": status, "updatedAt": now_iso()}},
                )
            await capabilities_collection.update_many(
                {"trajectoryIds": trajectory_id},
                {"$set": {"status": "harvested" if status == "harvested" else "harvest_failed", "updatedAt": now_iso()}},
            )
            return {"trajectoryId": trajectory_id, "taskId": task.task_id, "status": status, "summary": result.summary}
        except Exception as exc:
            if task.is_legacy_trajectory_record:
                await trajectories_collection.update_one(
                    {"trajectoryId": trajectory_id},
                    {"$set": {"status": "harvest_failed", "harvester": {"adapter": self.name, "status": "error", "failureReason": str(exc)}, "updatedAt": now_iso()}},
                )
            else:
                await benchmark_tasks_collection.update_one(
                    {"taskId": task.task_id},
                    {"$set": {"status": "harvest_failed", "updatedAt": now_iso()}},
                )
                await trajectories_collection.update_one(
                    {"trajectoryId": trajectory_id},
                    {
                        "$set": {
                            "trajectoryId": trajectory_id,
                            "taskId": task.task_id,
                            "agentId": task_doc.get("agentId") or agent_config.get("agentId", ""),
                            "companyId": task_doc.get("companyId") or agent_config.get("companyId", ""),
                            "email": task_doc.get("email") or agent_config.get("email", ""),
                            "benchmarkId": task_doc.get("benchmarkId", ""),
                            "taskName": task.task_name,
                            "prompt": task.prompt,
                            "successCriteria": task.success_criteria,
                            "source": "automata_harvester",
                            "status": "harvest_failed",
                            "actions": [],
                            "trajectory": [],
                            "metadata": task_doc.get("metadata") if isinstance(task_doc.get("metadata"), dict) else {},
                            "harvester": {"adapter": self.name, "status": "error", "failureReason": str(exc)},
                            "updatedAt": now_iso(),
                        },
                        "$setOnInsert": {"createdAt": now_iso()},
                    },
                    upsert=True,
                )
            await capabilities_collection.update_many(
                {"trajectoryIds": trajectory_id},
                {"$set": {"status": "harvest_failed", "updatedAt": now_iso()}},
            )
            return {"trajectoryId": trajectory_id, "taskId": task.task_id, "status": "harvest_failed", "error": str(exc)}

    async def harvest_one(self, agent_config: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
        return await self.harvest_task(agent_config, HarvestTask(trajectory))


def _post_json_sync(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Harvester response must be a JSON object.")
            return data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Top miner harvester returned HTTP {exc.code}: {body}") from exc


async def _run_top_miner_harvest(agent_config: dict[str, Any], task_doc: dict[str, Any]) -> HarvestResult:
    base_url = str(
        agent_config.get("topMinerHarvesterEndpoint")
        or agent_config.get("autoppiaHarvesterEndpoint")
        or agent_config.get("harvesterEndpoint")
        or os.getenv("AUTOMATA_AUTOPPIA_HARVESTER_ENDPOINT")
        or os.getenv("AUTOMATA_TOP_MINER_HARVESTER_ENDPOINT")
        or ""
    ).strip()
    if not base_url:
        raise RuntimeError("External IWA harvester endpoint is not configured.")
    endpoint = base_url.rstrip("/") + "/find_trayectory"
    timeout = float(
        os.getenv(
            "AUTOMATA_AUTOPPIA_HARVESTER_TIMEOUT_SECONDS",
            os.getenv("AUTOMATA_TOP_MINER_HARVESTER_TIMEOUT_SECONDS", os.getenv("AUTOMATA_HARVESTER_TIMEOUT_SECONDS", "600")),
        )
    )
    payload = iwa_task_payload(task_doc, agent_config)
    response = await asyncio.to_thread(_post_json_sync, endpoint, payload, timeout)
    raw_trajectory = response.get("trajectory") or response.get("tool_calls") or response.get("actions") or []
    if not isinstance(raw_trajectory, list):
        raw_trajectory = []
    task_url = str(payload.get("url") or "")
    trajectory = canonical_tool_trajectory([item for item in raw_trajectory if isinstance(item, dict)], task_url=task_url)
    actions = internal_actions_from_trajectory(trajectory)
    success = bool(response.get("success", bool(trajectory)))
    return HarvestResult(
        success=success,
        confidence=float(response.get("confidence") or (1.0 if trajectory else 0.0)),
        summary=str(response.get("summary") or f"Top miner returned {len(trajectory)} trajectory tool calls."),
        failure_reason=str(response.get("failureReason") or response.get("failure_reason") or ""),
        actions=actions,
        trajectory=trajectory,
        evidence=[str(item) for item in response.get("evidence", []) if item] if isinstance(response.get("evidence"), list) else [],
        notes=str(response.get("notes") or ""),
        raw_output=json.dumps(response, ensure_ascii=True),
    )


@dataclass(frozen=True)
class TopMinerAgentHarvester(ClaudeCliAgentHarvester):
    name: str = "top_miner"

    async def harvest(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(agent_config.get("agentId") or "")
        task_cursor = benchmark_tasks_collection.find(
            {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}},
            {"_id": 0},
        ).sort("createdAt", 1)
        tasks = await task_cursor.to_list(length=100)
        if tasks:
            results = [await self.harvest_task(agent_config, HarvestTask(task)) for task in tasks]
            return {"count": len(results), "results": results}
        cursor = trajectories_collection.find(
            {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}},
            {"_id": 0},
        ).sort("createdAt", 1)
        legacy = await cursor.to_list(length=100)
        results = [await self.harvest_task(agent_config, HarvestTask(item)) for item in legacy]
        return {"count": len(results), "results": results}

    async def run_harvest(self, agent_config: dict[str, Any], task_doc: dict[str, Any]) -> HarvestResult:
        return await _run_top_miner_harvest(agent_config, task_doc)


@dataclass(frozen=True)
class AutoppiaExternalAgentHarvester(TopMinerAgentHarvester):
    name: str = "autoppia_harvester"


@dataclass(frozen=True)
class NoopAgentHarvester:
    name: str = "noop"

    async def harvest(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        return {"count": 0, "harvested": 0, "errors": ["Noop harvester selected."]}

    async def harvest_task(self, agent_config: dict[str, Any], task: HarvestTask) -> dict[str, Any]:
        return {"trajectoryId": task.task_id, "taskId": task.task_id, "status": "harvest_failed", "error": "Noop harvester selected."}

    async def harvest_one(self, agent_config: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
        return await self.harvest_task(agent_config, HarvestTask(trajectory))


HARVESTERS: dict[str, AgentHarvester] = {
    "autoppia_harvester": AutoppiaExternalAgentHarvester(),
    "claude_cli": ClaudeCliAgentHarvester(),
    "top_miner": TopMinerAgentHarvester(),
    "noop": NoopAgentHarvester(),
}


def default_harvester_name() -> str:
    return (os.getenv("AUTOMATA_AGENT_HARVESTER") or "autoppia_harvester").strip() or "autoppia_harvester"


def get_agent_harvester(name: str | None = None) -> AgentHarvester:
    key = (name or default_harvester_name()).strip()
    return HARVESTERS.get(key) or HARVESTERS.get(default_harvester_name()) or HARVESTERS["autoppia_harvester"]


def list_agent_harvesters() -> list[dict[str, str]]:
    return [{"name": key, "status": "available"} for key in sorted(HARVESTERS)]
