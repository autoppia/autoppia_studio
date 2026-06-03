from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.database import benchmark_tasks_collection, capabilities_collection, trajectories_collection
from app.harvester.claude_cli import HarvestResult, harvest_pending_trajectories, run_claude_harvest
from app.services.iwa_modeling import canonical_tool_trajectory, internal_actions_from_trajectory, iwa_task_payload


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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
            trajectory_update = {
                "trajectoryId": trajectory_id,
                "taskId": task.task_id,
                "agentId": task_doc.get("agentId") or agent_config.get("agentId", ""),
                "companyId": task_doc.get("companyId") or agent_config.get("companyId", ""),
                "email": task_doc.get("email") or agent_config.get("email", ""),
                "webId": task_doc.get("webId", ""),
                "benchmarkId": task_doc.get("benchmarkId", ""),
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
        or agent_config.get("harvesterEndpoint")
        or os.getenv("AUTOMATA_TOP_MINER_HARVESTER_ENDPOINT")
        or ""
    ).strip()
    if not base_url:
        raise RuntimeError("Top miner harvester endpoint is not configured.")
    endpoint = base_url.rstrip("/") + "/find_trayectory"
    timeout = float(os.getenv("AUTOMATA_TOP_MINER_HARVESTER_TIMEOUT_SECONDS", os.getenv("AUTOMATA_HARVESTER_TIMEOUT_SECONDS", "600")))
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
class NoopAgentHarvester:
    name: str = "noop"

    async def harvest(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        return {"count": 0, "harvested": 0, "errors": ["Noop harvester selected."]}

    async def harvest_task(self, agent_config: dict[str, Any], task: HarvestTask) -> dict[str, Any]:
        return {"trajectoryId": task.task_id, "taskId": task.task_id, "status": "harvest_failed", "error": "Noop harvester selected."}

    async def harvest_one(self, agent_config: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
        return await self.harvest_task(agent_config, HarvestTask(trajectory))


HARVESTERS: dict[str, AgentHarvester] = {
    "claude_cli": ClaudeCliAgentHarvester(),
    "top_miner": TopMinerAgentHarvester(),
    "noop": NoopAgentHarvester(),
}


def default_harvester_name() -> str:
    return (os.getenv("AUTOMATA_AGENT_HARVESTER") or "claude_cli").strip() or "claude_cli"


def get_agent_harvester(name: str | None = None) -> AgentHarvester:
    key = (name or default_harvester_name()).strip()
    return HARVESTERS.get(key) or HARVESTERS["claude_cli"]


def list_agent_harvesters() -> list[dict[str, str]]:
    return [{"name": key, "status": "available"} for key in sorted(HARVESTERS)]
