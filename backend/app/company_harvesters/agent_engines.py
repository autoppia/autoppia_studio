from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.company_harvesters.base import CompanyHarvesterEngineInfo
from app.company_harvesters.local_heuristic import AgenticDiscoveryCore
from app.models.company_harvester import CompanyHarvesterInput, CompanyHarvesterOutput


@dataclass(frozen=True)
class AgenticHarvester(AgenticDiscoveryCore):
    name: str = "agentic"
    kind: str = "agentic"
    display_name: str = "Agentic Harvester"

    def info(self) -> CompanyHarvesterEngineInfo:
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind="agentic",
            displayName=self.display_name,
            description="Default model-agent CompanyHarvester profile. It plans task discovery and solution discovery with the agentic discovery core.",
            metadata={"adapter": "agentic", "agentRuntime": "model_agent"},
        )


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    candidates = [cleaned]
    if fenced:
        candidates.insert(0, fenced.group(1))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("Harvester CLI did not return a JSON object")


def _harvester_prompt(request: CompanyHarvesterInput, *, runtime_kind: str) -> str:
    request_payload = request.model_dump(mode="json")
    return (
        "You are a CompanyHarvester benchmark participant. Given company onboarding materials, "
        "discover useful benchmark tasks and propose the deliverables needed to build an agent.\n\n"
        "Return ONLY valid JSON matching this shape:\n"
        "{\n"
        '  "schemaVersion": "company_harvester_output/v1",\n'
        '  "companyId": string,\n'
        '  "benchmarkId": string,\n'
        '  "proposedTasks": [{"taskId": string, "name": string, "prompt": string, "successCriteria": string, "expectedSurfaces": [string], "riskClass": string, "confidence": number, "evidence": [object], "metadata": object}],\n'
        '  "taskSolutions": [{"taskId": string, "connectors": [{"connectorId": string, "name": string, "type": "web|api|knowledge|code|email|database|custom", "origin": "existing|derived_from_openapi|derived_from_code|proposed_custom", "existingConnectorId": string, "surface": string, "authRequired": boolean, "runtimeRequirements": [string], "evidence": [object], "customConnectorCode": object|null, "metadata": object}], "tools": [{"toolId": string, "name": string, "origin": "existing_connector_tool|derived_from_openapi|derived_from_code|proposed_custom", "existingToolId": string, "connectorId": string, "executionType": string, "policyBoundary": string, "riskLevel": string, "inputSchema": object, "outputSchema": object, "evidence": [object], "customToolCode": object|null, "metadata": object}], "trajectories": [{"trajectoryId": string, "description": string, "toolCalls": [object], "source": "generated", "confidence": number, "metadata": object}], "skills": [{"skillId": string, "name": string, "description": string, "trajectoryIds": [string], "instructions": string, "source": "hybrid", "metadata": object}], "agentProvider": {"runtimeKind": "'
        + runtime_kind
        + '", "provider": "openai", "model": "", "systemPrompt": string, "metadata": object}, "confidence": number, "metadata": object}],\n'
        '  "agentConfigs": [], "questions": [], "confidence": number, "metadata": object\n'
        "}\n\n"
        "Important scoring rules: proposed task names/prompts should match the actual business tasks implied by the input, not generic validation tasks. "
        "Every proposed task should have a corresponding taskSolution with connectors, tools, trajectories, skills, and agentProvider. "
        "Use availableInventory.connectors/tools when possible. If you derive tools from OpenAPI use origin=derived_from_openapi with evidence. "
        "If you derive tools from source code use origin=derived_from_code with evidence. If no allowed connector/tool exists, use origin=proposed_custom and include customConnectorCode/customToolCode. "
        "questions must be an array of objects, never strings. "
        "customToolCode.language and customConnectorCode.language must be one of python, typescript, javascript. "
        "Never use pseudo, pseudocode, text, shell, bash, or markdown as a custom code language. "
        "If you only have pseudocode or instructions, put it in skills.instructions, trajectory.description, or metadata; do not put it in customToolCode/customConnectorCode. "
        "A proposed custom tool/connector must include executable code; otherwise use an existing allowed tool/connector or describe the guidance as a skill. "
        "Never return a tool or connector with unknown origin. "
        "Do not inspect the filesystem or run commands; answer directly from the CompanyHarvesterInput JSON.\n\n"
        f"CompanyHarvesterInput JSON:\n{json.dumps(request_payload, ensure_ascii=False)}"
    )


def _normalize_question_items(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return warnings
    normalized: list[dict[str, Any]] = []
    changed = False
    for index, question in enumerate(questions, start=1):
        if isinstance(question, dict):
            normalized.append(question)
            continue
        if isinstance(question, str):
            changed = True
            normalized.append(
                {
                    "questionId": f"q{index}",
                    "code": "harvester_clarification",
                    "prompt": question,
                    "reason": "Harvester returned a free-form clarification question.",
                    "severity": "info",
                    "expectedAnswerType": "text",
                    "visibility": "dev",
                    "metadata": {"normalizedFrom": "string"},
                }
            )
            continue
        normalized.append(
            {
                "questionId": f"q{index}",
                "code": "harvester_clarification",
                "prompt": str(question),
                "reason": "Harvester returned a non-object clarification question.",
                "severity": "info",
                "expectedAnswerType": "text",
                "visibility": "dev",
                "metadata": {"normalizedFrom": type(question).__name__},
            }
        )
        changed = True
    if changed:
        payload["questions"] = normalized
        warnings.append("normalized questions entries into objects")
    return warnings


def _prepare_output_payload(payload: dict[str, Any], request: CompanyHarvesterInput, *, engine_name: str, engine_kind: str) -> tuple[dict[str, Any], list[str]]:
    prepared = json.loads(json.dumps(payload))
    prepared.setdefault("schemaVersion", "company_harvester_output/v1")
    prepared.setdefault("companyId", request.companyId)
    prepared.setdefault("benchmarkId", f"{request.companyId}:{engine_name}:benchmark")
    prepared.setdefault("proposedTasks", [])
    prepared.setdefault("taskSolutions", [])
    prepared.setdefault("agentConfigs", [])
    prepared.setdefault("questions", [])
    prepared.setdefault("confidence", 0.0)
    metadata = prepared.setdefault("metadata", {})
    metadata["harvesterEngine"] = {"name": engine_name, "kind": engine_kind, "execution": "real_cli"}
    warnings = _normalize_question_items(prepared)
    return prepared, warnings


def _contract_hints(errors: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", []))
        message = str(error.get("msg") or "")
        if location.startswith("questions."):
            hints.append("questions must be objects with questionId/code/prompt/reason/severity, never raw strings.")
        if "customToolCode.language" in location or "customConnectorCode.language" in location:
            hints.append("custom code language must be python, typescript, or javascript. Move pseudocode into skills.instructions or metadata instead of customToolCode/customConnectorCode.")
        if "origin" in location:
            hints.append("origins must be existing, existing_connector_tool, derived_from_openapi, derived_from_code, or proposed_custom as appropriate.")
        if "Input should be" in message and "dictionary" in message:
            hints.append(f"{location} must be a JSON object, not a scalar.")
    return sorted(set(hints))


def validate_company_harvester_output(
    payload: dict[str, Any],
    request: CompanyHarvesterInput,
    *,
    engine_name: str,
    engine_kind: str,
    runtime_kind: str,
) -> dict[str, Any]:
    prepared, warnings = _prepare_output_payload(payload, request, engine_name=engine_name, engine_kind=engine_kind)
    try:
        parsed = CompanyHarvesterOutput.model_validate(prepared)
    except ValidationError as exc:
        errors = exc.errors()
        return {
            "valid": False,
            "errors": errors,
            "errorText": str(exc),
            "hints": _contract_hints(errors),
            "normalizedOutput": prepared,
            "warnings": warnings,
        }
    for solution in parsed.taskSolutions:
        solution.agentProvider.runtimeKind = runtime_kind  # type: ignore[assignment]
    return {
        "valid": True,
        "errors": [],
        "errorText": "",
        "hints": [],
        "normalizedOutput": prepared,
        "output": parsed,
        "warnings": warnings,
    }


def _repair_prompt(
    *,
    request: CompanyHarvesterInput,
    runtime_kind: str,
    previous_output: str,
    check: dict[str, Any],
) -> str:
    compact_errors = [
        {
            "loc": ".".join(str(part) for part in error.get("loc", [])),
            "msg": error.get("msg", ""),
            "input": str(error.get("input", ""))[:200],
        }
        for error in check.get("errors", [])[:12]
    ]
    return (
        "Your previous CompanyHarvesterOutput failed schema validation. "
        "Fix only the JSON output. Return ONLY valid JSON and no commentary.\n\n"
        "Validation errors:\n"
        f"{json.dumps(compact_errors, ensure_ascii=False, indent=2)}\n\n"
        "Hints:\n"
        f"{json.dumps(check.get('hints') or [], ensure_ascii=False, indent=2)}\n\n"
        "Strict reminders:\n"
        "- questions must be objects, never strings.\n"
        "- customToolCode.language/customConnectorCode.language must be python, typescript, or javascript only.\n"
        "- pseudo/pseudocode is not executable code. Move it to skills.instructions, trajectory.description, or metadata, or omit customToolCode.\n"
        f"- agentProvider.runtimeKind must be {runtime_kind}.\n\n"
        "Original CompanyHarvesterInput:\n"
        f"{json.dumps(request.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        "Previous invalid output:\n"
        f"{previous_output[:60000]}"
    )


@dataclass(frozen=True)
class CliCompanyHarvester:
    name: str
    kind: str
    display_name: str
    command: str
    runtime_kind: str

    def info(self) -> CompanyHarvesterEngineInfo:
        available = bool(self._command_path())
        return CompanyHarvesterEngineInfo(
            name=self.name,
            kind=self.kind,  # type: ignore[arg-type]
            displayName=self.display_name,
            description=f"{self.display_name} using the local {self.command} CLI as the outer CompanyHarvester runtime.",
            status="ready" if available else "missing_cli",
            metadata={"adapter": self.name, "agentRuntime": self.runtime_kind, "execution": "real_cli"},
        )

    def _command_path(self) -> str:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / self.command
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        return ""

    async def harvest(self, request: CompanyHarvesterInput) -> CompanyHarvesterOutput:
        max_repairs = max(0, int(float(os.getenv("AUTOMATA_CLI_HARVESTER_REPAIR_ATTEMPTS", "2"))))
        prompt = _harvester_prompt(request, runtime_kind=self.runtime_kind)
        last_check: dict[str, Any] | None = None
        last_output = ""
        for attempt in range(max_repairs + 1):
            output = await self._run_prompt(prompt)
            last_output = output
            payload = _extract_json_object(output)
            check = validate_company_harvester_output(
                payload,
                request,
                engine_name=self.name,
                engine_kind=self.kind,
                runtime_kind=self.runtime_kind,
            )
            last_check = check
            if check["valid"]:
                parsed: CompanyHarvesterOutput = check["output"]
                parsed.metadata.setdefault("harvesterEngine", {})["repairAttempts"] = attempt
                if check.get("warnings"):
                    parsed.metadata["contractWarnings"] = check["warnings"]
                return parsed
            if attempt >= max_repairs:
                break
            prompt = _repair_prompt(request=request, runtime_kind=self.runtime_kind, previous_output=last_output, check=check)
        error_text = (last_check or {}).get("errorText") or "unknown contract validation error"
        hints = (last_check or {}).get("hints") or []
        raise RuntimeError(f"{self.name} harvester output failed contract validation after {max_repairs} repair attempt(s): {error_text}\nHints: {json.dumps(hints, ensure_ascii=False)}")

    async def _run_prompt(self, prompt: str) -> str:
        if self.command == "claude":
            return await self._run_claude_prompt(prompt)
        if self.command == "codex":
            return await self._run_codex_prompt(prompt)
        raise RuntimeError(f"Unsupported CLI harvester command: {self.command}")

    async def _run_claude_prompt(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            prompt,
            "--output-format",
            "text",
            "--max-budget-usd",
            os.getenv("AUTOMATA_CLI_HARVESTER_MAX_BUDGET_USD", "0.25"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await _communicate_cli(proc, self.name)

    async def _run_codex_prompt(self, prompt: str) -> str:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as handle:
            output_path = handle.name
        try:
            timeout = int(float(os.getenv("AUTOMATA_CLI_HARVESTER_TIMEOUT_SECONDS", "180")))
            proc = await asyncio.create_subprocess_exec(
                "timeout",
                "--kill-after=5s",
                f"{timeout}s",
                "codex",
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "-s",
                "read-only",
                "-C",
                str(Path(__file__).resolve().parents[3]),
                "--skip-git-repo-check",
                "--output-last-message",
                output_path,
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await _communicate_cli(proc, self.name, input_text=prompt, timeout_seconds=timeout + 15)
            return Path(output_path).read_text(encoding="utf-8")
        finally:
            try:
                Path(output_path).unlink()
            except FileNotFoundError:
                pass


async def _communicate_cli(
    proc: asyncio.subprocess.Process,
    name: str,
    *,
    input_text: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    timeout = timeout_seconds or float(os.getenv("AUTOMATA_CLI_HARVESTER_TIMEOUT_SECONDS", "180"))
    try:
        stdin = input_text.encode() if input_text is not None else None
        stdout, stderr = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"{name} harvester timed out after {timeout}s") from exc
    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")
    if proc.returncode != 0:
        detail = "\n".join(part for part in [f"stderr: {err[-1000:]}" if err else "", f"stdout: {out[-1000:]}" if out else ""] if part)
        raise RuntimeError(f"{name} harvester failed with code {proc.returncode}: {detail}")
    return out


@dataclass(frozen=True)
class ClaudeCodeCompanyHarvester(CliCompanyHarvester):
    name: str = "claude_code"
    kind: str = "claude_code"
    display_name: str = "Claude Code Harvester"
    command: str = "claude"
    runtime_kind: str = "claude_code"


@dataclass(frozen=True)
class CodexCompanyHarvester(CliCompanyHarvester):
    name: str = "codex"
    kind: str = "codex"
    display_name: str = "Codex Harvester"
    command: str = "codex"
    runtime_kind: str = "codex"
