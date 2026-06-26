from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


TASK_CONTRACT_ACTIONS = {
    "businessIntent": "Declare the business intent this task evaluates.",
    "initialState": "Attach an initial URL or state so the task can be replayed.",
    "allowedSystems": "List the systems, connectors, or domains the agent may use.",
    "expectedArtifacts": "Declare the business artifact expected from this task.",
    "successCriteria": "Add deterministic success criteria before using this task as an eval gate.",
    "riskClass": "Assign a risk class for runtime policy and approval routing.",
}


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _metadata(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _nested_contract(task: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(task)
    contract = metadata.get("taskContract")
    return dict(contract) if isinstance(contract, dict) else {}


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean_string(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _list_field(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def build_task_contract(
    task: dict[str, Any],
    *,
    website_url: str = "",
    allowed_systems: list[Any] | None = None,
    default_risk_class: str = "low",
) -> dict[str, Any]:
    metadata = _metadata(task)
    nested = _nested_contract(task)
    success_criteria = _clean_string(task.get("successCriteria") or metadata.get("successCriteria") or nested.get("successCriteria"))
    prompt = _clean_string(task.get("prompt"))
    name = _clean_string(task.get("name") or task.get("taskName"))
    allowed = _list_field(nested.get("allowedSystems")) + _list_field(metadata.get("allowedSystems")) + _list_field(task.get("allowedSystems")) + list(allowed_systems or [])
    if website_url:
        allowed.append(website_url)
        host = _host(website_url)
        if host:
            allowed.append(host)
    expected_artifacts = (
        _list_field(task.get("expectedArtifacts"))
        or _list_field(metadata.get("expectedArtifacts"))
        or _list_field(nested.get("expectedArtifacts"))
        or _list_field(metadata.get("expectedArtifact"))
        or _list_field(nested.get("expectedArtifact"))
        or _list_field(task.get("expectedArtifacts"))
        or ["trajectory_trace"]
    )
    expected_inputs = (
        _list_field(task.get("expectedInputs"))
        or _list_field(metadata.get("expectedInputs"))
        or _list_field(nested.get("expectedInputs"))
        or _list_field(metadata.get("inputRequirements"))
        or _list_field(nested.get("inputRequirements"))
        or _list_field(task.get("inputRequirements"))
    )
    initial_url = _clean_string(task.get("initialUrl") or task.get("startUrl") or metadata.get("startUrl") or metadata.get("iwaStartUrl") or nested.get("initialUrl") or website_url)
    fallback_state = metadata.get("startState") if isinstance(metadata.get("startState"), dict) else {}
    initial_state = (
        task.get("initialState")
        if isinstance(task.get("initialState"), dict)
        else metadata.get("initialState")
        if isinstance(metadata.get("initialState"), dict)
        else nested.get("initialState")
        if isinstance(nested.get("initialState"), dict)
        else {
            "url": initial_url,
            "state": fallback_state,
        }
        if initial_url or fallback_state
        else {}
    )
    evaluator_config = (
        task.get("evaluatorConfig")
        if isinstance(task.get("evaluatorConfig"), dict)
        else metadata.get("evaluatorConfig")
        if isinstance(metadata.get("evaluatorConfig"), dict)
        else nested.get("evaluatorConfig")
        if isinstance(nested.get("evaluatorConfig"), dict)
        else {}
    )
    fixtures = (
        _list_field(task.get("fixtures"))
        or _list_field(metadata.get("fixtures"))
        or _list_field(nested.get("fixtures"))
        or _list_field(task.get("fixtureIds"))
        or _list_field(metadata.get("fixtureIds"))
        or _list_field(nested.get("fixtureIds"))
    )
    seed = (
        task.get("seed")
        if task.get("seed") not in (None, "")
        else metadata.get("seed")
        if metadata.get("seed") not in (None, "")
        else nested.get("seed")
        if nested.get("seed") not in (None, "")
        else ""
    )
    return {
        "businessIntent": _clean_string(
            task.get("businessIntent")
            or metadata.get("businessIntent")
            or nested.get("businessIntent")
            or prompt
            or name
        ),
        "initialState": initial_state,
        "initialUrl": initial_url or _clean_string(initial_state.get("url") if isinstance(initial_state, dict) else ""),
        "allowedSystems": _dedupe(allowed),
        "expectedInputs": _dedupe(expected_inputs),
        "expectedArtifacts": _dedupe(expected_artifacts),
        "successCriteria": success_criteria,
        "riskClass": _clean_string(task.get("riskClass") or metadata.get("riskClass") or nested.get("riskClass") or default_risk_class).lower(),
        "constraints": _list_field(nested.get("constraints")) + _list_field(metadata.get("constraints")) + _list_field(task.get("constraints")),
        "evaluatorConfig": evaluator_config,
        "fixtures": _dedupe(fixtures),
        "seed": seed,
    }


def task_contract_from_record(task: dict[str, Any], *, default_risk_class: str = "") -> dict[str, Any]:
    return build_task_contract(
        task,
        website_url="",
        allowed_systems=[],
        default_risk_class=default_risk_class or "",
    )


def task_contract_ready(task: dict[str, Any]) -> bool:
    contract = task_contract_from_record(task)
    return task_contract_hardening(contract)["state"] == "complete"


def task_contract_hardening(contract: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "businessIntent": bool(str(contract.get("businessIntent") or "").strip()),
        "initialState": bool(contract.get("initialUrl") or contract.get("initialState")),
        "allowedSystems": bool(contract.get("allowedSystems")),
        "expectedArtifacts": bool(contract.get("expectedArtifacts")),
        "successCriteria": bool(str(contract.get("successCriteria") or "").strip()),
        "riskClass": bool(str(contract.get("riskClass") or "").strip()),
    }
    missing = [field for field, ready in checks.items() if not ready]
    passed = sum(1 for ready in checks.values() if ready)
    total = len(checks)
    reproducibility = {
        "initialState": checks["initialState"],
        "evaluatorConfig": bool(contract.get("evaluatorConfig")),
        "fixtures": bool(contract.get("fixtures")),
        "seed": bool(str(contract.get("seed") or "").strip()),
        "readyForReplay": bool(
            checks["initialState"]
            and (contract.get("evaluatorConfig") or contract.get("fixtures") or str(contract.get("seed") or "").strip())
        ),
    }
    return {
        "state": "complete" if not missing else "incomplete",
        "checks": checks,
        "missingFields": missing,
        "nextActions": [TASK_CONTRACT_ACTIONS[field] for field in missing],
        "passedChecks": passed,
        "totalChecks": total,
        "score": round(passed / total, 3) if total else 0.0,
        "evaluationReady": bool(checks["successCriteria"] and reproducibility["readyForReplay"]),
        "productionReady": bool(not missing and reproducibility["readyForReplay"]),
        "reproducibility": reproducibility,
    }


def task_contract_hardening_summary(contracts: list[dict[str, Any]], *, sample_limit: int = 5) -> dict[str, Any]:
    hardening = [task_contract_hardening(contract) for contract in contracts]
    missing_counts: dict[str, int] = {}
    playbook: list[dict[str, Any]] = []
    for item in hardening:
        for field in item.get("missingFields") or []:
            field_name = str(field or "").strip()
            if not field_name:
                continue
            missing_counts[field_name] = missing_counts.get(field_name, 0) + 1
    for field in sorted(missing_counts, key=lambda item: (-missing_counts[item], item)):
        playbook.append(
            {
                "field": field,
                "count": missing_counts[field],
                "severity": "high" if field in {"successCriteria", "riskClass"} else "medium",
                "action": TASK_CONTRACT_ACTIONS.get(field, "Complete this task contract field."),
            }
        )
    return {
        "total": len(contracts),
        "complete": sum(1 for item in hardening if item["state"] == "complete"),
        "evaluationReady": sum(1 for item in hardening if item["evaluationReady"]),
        "productionReady": sum(1 for item in hardening if item["productionReady"]),
        "averageScore": round(sum(float(item.get("score") or 0) for item in hardening) / len(hardening), 3) if hardening else 0.0,
        "missingFields": [{"name": key, "count": missing_counts[key]} for key in sorted(missing_counts, key=lambda item: (-missing_counts[item], item))],
        "playbook": playbook,
        "sample": hardening[:sample_limit],
    }


def task_reproducibility_summary(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(contracts)
    with_initial_state = sum(1 for contract in contracts if contract.get("initialUrl") or contract.get("initialState"))
    with_evaluator_config = sum(1 for contract in contracts if contract.get("evaluatorConfig"))
    with_fixtures = sum(1 for contract in contracts if contract.get("fixtures"))
    with_seed = sum(1 for contract in contracts if str(contract.get("seed") or "").strip())
    ready_for_replay = sum(
        1
        for contract in contracts
        if (contract.get("initialUrl") or contract.get("initialState"))
        and (contract.get("evaluatorConfig") or contract.get("fixtures") or str(contract.get("seed") or "").strip())
    )
    return {
        "total": total,
        "withInitialState": with_initial_state,
        "withEvaluatorConfig": with_evaluator_config,
        "withFixtures": with_fixtures,
        "withSeed": with_seed,
        "readyForReplay": ready_for_replay,
        "replayReadyRatio": round(ready_for_replay / total, 3) if total else 0.0,
    }


def task_evaluation_harness(contract: dict[str, Any], judge_type: str = "manual") -> dict[str, Any]:
    deterministic_ready = bool(str(contract.get("successCriteria") or "").strip())
    stateful_ready = bool(contract.get("initialUrl") or contract.get("initialState"))
    llm_enabled = str(judge_type or "").strip().lower() == "llm"
    layers = [
        {
            "key": "deterministic",
            "label": "Deterministic checks",
            "enabled": deterministic_ready,
            "role": "first_pass",
            "summary": "Success criteria can be checked before model judging." if deterministic_ready else "Add success criteria for deterministic checks.",
        },
        {
            "key": "stateful",
            "label": "Stateful evaluator",
            "enabled": stateful_ready,
            "role": "environment_replay",
            "summary": "Initial URL/state can drive replay or stateful evaluation." if stateful_ready else "Add initial URL or state for replay.",
        },
        {
            "key": "llm",
            "label": "LLM judge",
            "enabled": llm_enabled,
            "role": "semantic_review",
            "summary": "LLMJudge is enabled as semantic review." if llm_enabled else "LLMJudge is disabled unless this task needs semantic review.",
        },
        {
            "key": "manual",
            "label": "Human review",
            "enabled": True,
            "role": "override",
            "summary": "Manual review remains available for overrides and unresolved cases.",
        },
    ]
    return {
        "strategy": "layered",
        "preferredOrder": [layer["key"] for layer in layers if layer["enabled"]],
        "deterministicFirst": deterministic_ready,
        "statefulReplay": stateful_ready,
        "llmAsComplement": llm_enabled,
        "humanOverride": True,
        "layers": layers,
    }


def task_metadata_with_contract(
    task: dict[str, Any],
    *,
    website_url: str = "",
    allowed_systems: list[Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    default_risk_class: str = "low",
) -> dict[str, Any]:
    metadata = {
        **_metadata(task),
        **(extra_metadata or {}),
    }
    contract = build_task_contract(
        {**task, "metadata": metadata},
        website_url=website_url,
        allowed_systems=allowed_systems,
        default_risk_class=default_risk_class,
    )
    return {
        **metadata,
        "taskContract": contract,
        "businessIntent": contract["businessIntent"],
        "initialState": contract["initialState"],
        "allowedSystems": contract["allowedSystems"],
        "expectedInputs": contract["expectedInputs"],
        "expectedArtifacts": contract["expectedArtifacts"],
        "riskClass": contract["riskClass"],
        "evaluatorConfig": contract["evaluatorConfig"],
        "fixtures": contract["fixtures"],
        "seed": contract["seed"],
    }
