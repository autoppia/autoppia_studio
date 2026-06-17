from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database import benchmark_tasks_collection, capabilities_collection, connectors_collection, trajectories_collection
from app.routes.credentials import resolve_secret_refs
from app.services.bopa import latest_bopa_pdf
from app.services.iwa_modeling import canonical_tool_trajectory, internal_actions_from_trajectory, iwa_task_payload


ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "failureReason": {"type": "string"},
        "trajectory": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["name", "arguments"],
            },
        },
        "discoveredTools": {
            "type": "array",
            "description": "Optional connector tools discovered from public API/docs while harvesting. Prefer this when a deterministic API can solve the task.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                    "runtimeRequirements": {"type": "array", "items": {"type": "string"}},
                    "sideEffects": {"type": "string"},
                    "executionType": {"type": "string"},
                    "discoveryEvidence": {"type": "array", "items": {"type": "object"}},
                    "discoveryRelevance": {"type": "object"},
                },
                "required": ["name", "description"],
            },
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "finalUrl": {"type": "string"},
        "finalHtml": {"type": "string"},
        "execution_history": {
            "type": "array",
            "items": {"type": "object"},
        },
        "notes": {"type": "string"},
    },
    "required": ["success", "confidence", "summary", "trajectory"],
}


@dataclass(frozen=True)
class HarvestResult:
    success: bool
    confidence: float
    summary: str
    actions: list[dict[str, Any]]
    trajectory: list[dict[str, Any]]
    evidence: list[str]
    notes: str = ""
    failure_reason: str = ""
    final_url: str = ""
    final_html: str = ""
    execution_history: list[dict[str, Any]] | None = None
    discovered_tools: list[dict[str, Any]] | None = None
    raw_output: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _harvester_root() -> Path:
    root = Path(os.getenv("AUTOMATA_HARVESTER_WORKDIR", "/tmp/automata_harvester")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_secret_field(field: str) -> bool:
    return bool(re.search(r"password|secret|token|api[_-]?key|refresh|private", field, flags=re.IGNORECASE))


def _safe_config(connector: dict[str, Any], secrets_by_placeholder: dict[str, str]) -> dict[str, Any]:
    connector_id = str(connector.get("connectorId") or "connector")
    safe: dict[str, Any] = {}
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    for field, value in config.items():
        if _is_secret_field(str(field)) and value not in (None, ""):
            placeholder = f"{{{{credential.{connector_id}.config.{field}}}}}"
            secrets_by_placeholder[placeholder] = str(value)
            safe[field] = placeholder
        else:
            safe[field] = value
    return safe


def _compact_connector(connector: dict[str, Any], resolved_secrets: dict[str, str], secrets_by_placeholder: dict[str, str]) -> dict[str, Any]:
    credential_refs = connector.get("credentialRefs") or {}
    credential_fields: dict[str, Any] = {}
    for field, ref in credential_refs.items():
        credential_fields[field] = {
            "configured": bool(ref and resolved_secrets.get(field)),
            "placeholder": f"{{{{credential.{connector.get('connectorId')}.{field}}}}}",
        }
    return {
        "connectorId": connector.get("connectorId", ""),
        "name": connector.get("name", ""),
        "type": connector.get("type", "api"),
        "category": connector.get("category", ""),
        "status": connector.get("status", ""),
        "provider": connector.get("provider", ""),
        "config": _safe_config(connector, secrets_by_placeholder),
        "credentialFields": credential_fields,
        "toolkit": connector.get("toolkit", {}),
    }


def _redact_value(value: Any, secret_values: list[str], placeholders: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _redact_value(item, secret_values, placeholders) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, secret_values, placeholders) for item in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for secret in secret_values:
        if secret and secret in redacted:
            redacted = redacted.replace(secret, placeholders.get(secret, "{{credential.secret}}"))
    return redacted


def redact_actions(actions: list[dict[str, Any]], secrets_by_placeholder: dict[str, str]) -> list[dict[str, Any]]:
    placeholders = {secret: placeholder for placeholder, secret in secrets_by_placeholder.items() if secret}
    secret_values = sorted(placeholders.keys(), key=len, reverse=True)
    redacted: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        redacted.append(_redact_value(action, secret_values, placeholders))
    return redacted


def redact_text(text: str, secrets_by_placeholder: dict[str, str]) -> str:
    redacted = text or ""
    for placeholder, secret in sorted(secrets_by_placeholder.items(), key=lambda item: len(item[1] or ""), reverse=True):
        if secret:
            redacted = redacted.replace(secret, placeholder)
    return redacted


def _extract_json_candidate(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty harvester output")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("structured_output"), dict):
                return parsed["structured_output"]
            if isinstance(parsed.get("result"), str):
                return _extract_json_candidate(parsed["result"])
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("could not parse JSON from harvester output")


def parse_harvester_output(stdout: str) -> HarvestResult:
    parsed = _extract_json_candidate(stdout)
    raw_trajectory = parsed.get("trajectory") if isinstance(parsed.get("trajectory"), list) else []
    legacy_actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
    trajectory = canonical_tool_trajectory(raw_trajectory or legacy_actions)
    actions = internal_actions_from_trajectory(trajectory)
    evidence = [str(item) for item in parsed.get("evidence", []) if item]
    final_url = str(parsed.get("finalUrl") or parsed.get("final_url") or "")
    if not final_url:
        final_url = _infer_final_url(evidence)
    return HarvestResult(
        success=bool(parsed.get("success")),
        confidence=float(parsed.get("confidence") or 0),
        summary=str(parsed.get("summary") or ""),
        failure_reason=str(parsed.get("failureReason") or parsed.get("failure_reason") or ""),
        actions=actions,
        trajectory=trajectory,
        evidence=evidence,
        notes=str(parsed.get("notes") or ""),
        final_url=final_url,
        final_html=str(parsed.get("finalHtml") or parsed.get("final_html") or ""),
        execution_history=parsed.get("execution_history") if isinstance(parsed.get("execution_history"), list) else parsed.get("executionHistory") if isinstance(parsed.get("executionHistory"), list) else None,
        discovered_tools=parsed.get("discoveredTools") if isinstance(parsed.get("discoveredTools"), list) else parsed.get("discovered_tools") if isinstance(parsed.get("discovered_tools"), list) else [],
        raw_output=stdout,
    )


def _infer_final_url(evidence: list[str]) -> str:
    for item in reversed(evidence):
        match = re.search(r"https?://[^\s'\"<>]+", item)
        if match:
            return match.group(0).rstrip(".,)")
    return ""


def _is_bopa_pdf_task(agent_config: dict[str, Any], task: dict[str, Any]) -> bool:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    text = json.dumps(
        {
            "prompt": task.get("prompt", ""),
            "successCriteria": task.get("successCriteria", ""),
            "websiteUrl": agent_config.get("websiteUrl", ""),
            "metadata": metadata,
        },
        ensure_ascii=False,
    ).lower()
    has_bopa = "bopa" in text or "bopa.ad" in text or metadata.get("site") == "BOPA"
    has_pdf = "pdf" in text or any("pdf" in str(item).lower() for item in metadata.get("expectedArtifacts", []) if item)
    has_latest_bulletin = any(term in text for term in ("bolet", "butllet", "bulletin", "últim", "ultimo", "latest"))
    return bool(has_bopa and has_pdf and has_latest_bulletin)


async def try_bopa_pdf_harvest(agent_config: dict[str, Any], task: dict[str, Any]) -> HarvestResult | None:
    if not _is_bopa_pdf_task(agent_config, task):
        return None
    data = await asyncio.to_thread(latest_bopa_pdf)
    trajectory = [{"name": "bopa.latest_bulletin_pdf", "arguments": {}}]
    return HarvestResult(
        success=True,
        confidence=0.96,
        summary=f"Found latest BOPA bulletin {data['numBOPA']} and verified its PDF link.",
        actions=internal_actions_from_trajectory(trajectory),
        trajectory=trajectory,
        evidence=[
            f"BOPA API: {data['apiUrl']}",
            f"Latest bulletin: {data['numBOPA']} published at {data['publishedAt']} extra={data['isExtra']}",
            f"PDF: {data['pdfUrl']} contentType={data['contentType']} contentLength={data['contentLength']}",
        ],
        notes="Deterministic BOPA public bulletin resolver used before LLM/browser harvesting.",
        final_url=data["pdfUrl"],
        discovered_tools=[
            {
                "name": "bopa.latest_bulletin_pdf",
                "description": "Resolve the latest official BOPA bulletin PDF using the public BOPA API.",
                "inputSchema": {"type": "object", "properties": {}},
                "outputSchema": {"type": "object", "additionalProperties": True},
                "runtimeRequirements": ["network"],
                "sideEffects": "reads",
                "executionType": "api_call",
            }
        ],
    )


async def _load_connectors(company_id: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if not company_id:
        return [], {}
    cursor = connectors_collection.find({"companyId": company_id}, {"_id": 0})
    connectors = await cursor.to_list(length=500)
    secrets_by_placeholder: dict[str, str] = {}
    compact: list[dict[str, Any]] = []
    for connector in connectors:
        resolved = await resolve_secret_refs(connector.get("credentialRefs") or {})
        for field, value in resolved.items():
            secrets_by_placeholder[f"{{{{credential.{connector.get('connectorId')}.{field}}}}}"] = value
        compact.append(_compact_connector(connector, resolved, secrets_by_placeholder))
    return compact, secrets_by_placeholder


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_workspace_readme(path: Path) -> None:
    path.write_text(
        """
# Automata Harvester Workspace

You are running inside an isolated workspace for one trajectory harvesting task.

Available files:
- `task.json`: task prompt, success criteria, website URL, connectors, and credential placeholders.
- `result.json`: write the final structured result here.

Credentials:
- Raw values are not stored in files.
- If needed, read `AUTOMATA_CREDENTIAL_VALUES_JSON` from the environment.
- Never print raw credential values. In trajectory tool arguments, use placeholders like `{{credential.connectorId.field}}`.

Recommended browser approach:
- Create a short Playwright Python script if browser exploration is needed.
- Use stable selectors and record the replayable actions you perform.
- Prefer IWA tool names: `navigate`, `click`, `input`, `select_dropdown`, `send_keys`, `wait`.
- If you discover a public API, stable HTTP endpoint, SDK method, or deterministic file URL pattern that solves the task, prefer a connector/API tool over browser replay. Return that tool in `discoveredTools` and use its tool name in `trajectory`.
- Use IWA selectors only: `attributeValueSelector`, `tagContainsSelector`, or `xpathSelector`.

Result:
- `success=true` only when the task is actually complete.
- If unsure, use `success=false` and explain `failureReason`.
- User-provided task hints in `task.hints` are operational guidance. Use them to explore efficiently, but still verify the final state against `successCriteria`.
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _build_prompt(*, task_file: Path, output_file: Path) -> str:
    return f"""
You are Automata Harvester, the task-specific trajectory runtime used during custom agent creation.

Your job:
1. Read the task package at {task_file}.
2. Use browser/API exploration as needed. You may create and run Playwright or Node/Python scripts in this working directory.
3. Try to complete the task, then produce a reusable trajectory.
4. Write the final JSON result to {output_file}.
5. Print only that same final JSON as your final response.

Important rules:
- Do not claim success unless the target state is actually reached or the success criteria are clearly satisfied.
- Keep harvesting bounded: use at most 12 browser tools, and if the site is stuck loading or blocked, return success=false with the best partial replayable trajectory and evidence.
- If credentials are needed, use the credential placeholders from the package in the trajectory tool arguments; do not print raw credential values.
- Raw credential values are available only to subprocesses through AUTOMATA_CREDENTIAL_VALUES_JSON. Treat them as secrets and never write them to result JSON or logs.
- During harvesting, never execute real write/send/delete/payment actions against external systems. For those, record the intended action only after an `api.human_approval` action. Examples: do not actually send SMTP/Gmail/Telegram messages, create invoices, update CRMs, delete records, or make payments.
- If the task package connector config explicitly sets `allowWritesDuringHarvest=true` for a sandbox/demo web, you may execute writes inside that sandbox web only. This exception does not apply to email, chat, CRM, billing, payment, or other real external services.
- A trajectory may be `success=true` for write tasks when the read/exploration/draft is complete and the final write is represented as a pending approved action, not when the write is actually performed.
- Prefer stable selectors: labels, roles, text, data-testid, href, semantic attributes. Avoid brittle absolute xpaths.
- `trajectory` must be the replayable sequence of IWA/subnet tool calls. Do not return a sequence of action objects.
- For API/tool-based solutions, `trajectory` can contain connector tool calls such as `vendor.latest_report` or `system.lookup_record`; include matching definitions in `discoveredTools`.
- Tool call format examples:
  {{"name": "navigate", "arguments": {{"url": "https://example.com"}}}}
  {{"name": "click", "arguments": {{"selector": {{"type": "attributeValueSelector", "attribute": "id", "value": "submit"}}}}}}
  {{"name": "input", "arguments": {{"selector": {{"type": "attributeValueSelector", "attribute": "name", "value": "email"}}, "text": "{{{{credential.connector.field}}}}"}}}}
- Do not return `roleSelector`, `cssSelector`, or `pressKey`; convert them to `xpathSelector`/`attributeValueSelector` and `send_keys`.
- Include `finalUrl` whenever browser exploration reaches a final page.
- Include `execution_history` when possible. Each item should have `stepIndex`, `toolCall`, `url`, and any available `text` or `html`.
- Read and follow user-provided task hints from `task.hints`, `task.startUrl`, and `task.expectedArtifacts` when present. These are not extra tasks; they are guidance for completing the one task.
- Focus on the one target task. Capability discoverers may already have published connector tools; prefer those stable tools when they solve the task.
- If you discover a stable public API/tool while solving this task, report it in `discoveredTools` with evidence, but do not invent broad unrelated skills. Broad connector exploration belongs to the capability discoverer.
- If the task cannot be completed, return success=false, confidence, failureReason, evidence, and any partial trajectory tool calls.

Return JSON matching this schema:
{json.dumps(ACTION_SCHEMA, ensure_ascii=True)}
""".strip()


def _harvester_task_payload(agent_config: dict[str, Any], task: dict[str, Any], connectors: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    hints = metadata.get("hints") if isinstance(metadata.get("hints"), list) else []
    expected_artifacts = metadata.get("expectedArtifacts") if isinstance(metadata.get("expectedArtifacts"), list) else []
    capability_discovery = metadata.get("capabilityDiscovery") if isinstance(metadata.get("capabilityDiscovery"), dict) else agent_config.get("capabilityDiscovery") if isinstance(agent_config.get("capabilityDiscovery"), dict) else {"mode": "task_scoped"}
    return {
        "agent_config": {
            "agentId": agent_config.get("agentId", ""),
            "name": agent_config.get("name", ""),
            "websiteUrl": agent_config.get("websiteUrl", ""),
            "customInstructions": agent_config.get("customInstructions", ""),
            "runtimeCapabilities": agent_config.get("runtimeCapabilities", {}),
            "capabilityDiscovery": capability_discovery,
        },
        "task": {
            "taskId": task.get("taskId") or task.get("trajectoryId", ""),
            "trajectoryId": task.get("trajectoryId", ""),
            "taskName": task.get("taskName", ""),
            "prompt": task.get("prompt", ""),
            "successCriteria": task.get("successCriteria", ""),
            "metadata": metadata,
            "hints": hints,
            "startUrl": metadata.get("startUrl") or task.get("initialUrl") or agent_config.get("websiteUrl", ""),
            "expectedArtifacts": expected_artifacts,
            "capabilityDiscovery": capability_discovery,
        },
        "iwa_task": iwa_task_payload(task, agent_config),
        "connectors": connectors,
    }


async def run_claude_harvest(agent_config: dict[str, Any], task: dict[str, Any]) -> HarvestResult:
    bopa_result = await try_bopa_pdf_harvest(agent_config, task)
    if bopa_result is not None:
        return bopa_result

    claude_bin = shutil.which(os.getenv("AUTOMATA_CLAUDE_BIN", "claude"))
    if not claude_bin:
        raise RuntimeError("Claude CLI is not installed or not on PATH")

    run_id = str(uuid.uuid4())
    run_dir = _harvester_root() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    connectors, secrets_by_placeholder = await _load_connectors(str(agent_config.get("companyId") or ""))
    task_payload = _harvester_task_payload(agent_config, task, connectors)
    task_file = run_dir / "task.json"
    output_file = run_dir / "result.json"
    _write_json(task_file, task_payload)
    _write_workspace_readme(run_dir / "README.md")

    prompt = _build_prompt(task_file=task_file, output_file=output_file)
    timeout = int(os.getenv("AUTOMATA_HARVESTER_TIMEOUT_SECONDS", "600"))
    model = os.getenv("AUTOMATA_HARVESTER_CLAUDE_MODEL", "sonnet")

    cmd = [
        claude_bin,
        "--print",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(ACTION_SCHEMA, ensure_ascii=True),
        "--model",
        model,
        "--dangerously-skip-permissions",
        "--permission-mode",
        "bypassPermissions",
        "--add-dir",
        str(run_dir),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(run_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "AUTOMATA_HARVESTER_RUN_DIR": str(run_dir),
            "AUTOMATA_CREDENTIAL_VALUES_JSON": json.dumps(secrets_by_placeholder, ensure_ascii=True),
        },
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Claude harvester timed out after {timeout}s") from exc

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    (run_dir / "stdout.log").write_text(redact_text(stdout, secrets_by_placeholder), encoding="utf-8")
    (run_dir / "stderr.log").write_text(redact_text(stderr, secrets_by_placeholder), encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"Claude harvester failed with exit code {proc.returncode}: {stderr[-1000:]}")

    if output_file.exists():
        output_text = output_file.read_text(encoding="utf-8")
    else:
        output_text = stdout
    result = parse_harvester_output(output_text)
    redacted_trajectory = redact_actions(result.trajectory, secrets_by_placeholder)
    trajectory = redacted_trajectory or canonical_tool_trajectory(result.actions, task_url=str((task_payload.get("iwa_task") or {}).get("url") or ""))
    return HarvestResult(
        success=result.success,
        confidence=result.confidence,
        summary=result.summary,
        failure_reason=result.failure_reason,
        actions=internal_actions_from_trajectory(trajectory),
        trajectory=trajectory,
        evidence=result.evidence + [f"harvester_run_dir:{run_dir}"],
        notes=result.notes,
        final_url=result.final_url,
        final_html=result.final_html,
        execution_history=result.execution_history,
        raw_output=result.raw_output,
    )


async def harvest_pending_trajectories(agent_config: dict[str, Any]) -> dict[str, Any]:
    from app.services.agent_harvesters import HarvestTask, get_agent_harvester

    agent_id = str(agent_config.get("agentId") or "")
    task_cursor = benchmark_tasks_collection.find(
        {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}},
        {"_id": 0},
    ).sort("createdAt", 1)
    tasks = await task_cursor.to_list(length=100)
    if tasks:
        harvester = get_agent_harvester("claude_cli")
        results = [await harvester.harvest_task(agent_config, HarvestTask(task)) for task in tasks]
        return {"count": len(results), "results": results}

    cursor = trajectories_collection.find(
        {"agentId": agent_id, "status": {"$in": ["needs_harvest", "draft", "harvester_pending"]}},
        {"_id": 0},
    ).sort("createdAt", 1)
    trajectories = await cursor.to_list(length=100)
    results: list[dict[str, Any]] = []
    for trajectory in trajectories:
        now = _now()
        await trajectories_collection.update_one(
            {"trajectoryId": trajectory["trajectoryId"]},
            {"$set": {"status": "harvesting", "source": "automata_harvester", "updatedAt": now}},
        )
        try:
            result = await run_claude_harvest(agent_config, trajectory)
            iwa_payload = iwa_task_payload(trajectory, agent_config)
            canonical = result.trajectory or canonical_tool_trajectory(result.actions, task_url=str(iwa_payload.get("url") or ""))
            status = "harvested" if result.success and canonical else "harvest_failed"
            await trajectories_collection.update_one(
                {"trajectoryId": trajectory["trajectoryId"]},
                {
                    "$set": {
                        "status": status,
                        "actions": internal_actions_from_trajectory(canonical),
                        "trajectory": canonical,
                        "finalUrl": result.final_url,
                        "finalHtml": result.final_html,
                        "screenshots": [],
                        "metadata": {
                            **(trajectory.get("metadata") if isinstance(trajectory.get("metadata"), dict) else {}),
                            **({"execution_history": result.execution_history} if result.execution_history else {}),
                        },
                        "harvester": {
                            "adapter": "claude_cli",
                            "status": "success" if status == "harvested" else "failed",
                            "confidence": result.confidence,
                            "summary": result.summary,
                            "failureReason": result.failure_reason,
                            "evidence": result.evidence,
                            "notes": result.notes,
                        },
                        "updatedAt": _now(),
                    }
                },
            )
            await capabilities_collection.update_many(
                {"trajectoryIds": trajectory["trajectoryId"]},
                {
                    "$set": {
                        "status": "harvested" if status == "harvested" else "harvest_failed",
                        "updatedAt": _now(),
                    }
                },
            )
            results.append({"trajectoryId": trajectory["trajectoryId"], "status": status, "summary": result.summary})
        except Exception as exc:
            await trajectories_collection.update_one(
                {"trajectoryId": trajectory["trajectoryId"]},
                {
                    "$set": {
                        "status": "harvest_failed",
                        "harvester": {
                            "adapter": "claude_cli",
                            "status": "error",
                            "failureReason": str(exc),
                        },
                        "updatedAt": _now(),
                    }
                },
            )
            await capabilities_collection.update_many(
                {"trajectoryIds": trajectory["trajectoryId"]},
                {"$set": {"status": "harvest_failed", "updatedAt": _now()}},
            )
            results.append({"trajectoryId": trajectory["trajectoryId"], "status": "harvest_failed", "error": str(exc)})
    return {"count": len(results), "results": results}
