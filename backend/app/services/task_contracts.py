from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


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
        "expectedArtifacts": _dedupe(expected_artifacts),
        "successCriteria": success_criteria,
        "riskClass": _clean_string(task.get("riskClass") or metadata.get("riskClass") or nested.get("riskClass") or default_risk_class).lower(),
        "constraints": _list_field(nested.get("constraints")) + _list_field(metadata.get("constraints")) + _list_field(task.get("constraints")),
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
    return bool(
        contract["businessIntent"]
        and contract["allowedSystems"]
        and contract["expectedArtifacts"]
        and contract["riskClass"]
    )


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
        "expectedArtifacts": contract["expectedArtifacts"],
        "riskClass": contract["riskClass"],
    }
