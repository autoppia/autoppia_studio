from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _metadata(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


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
    success_criteria = _clean_string(task.get("successCriteria") or metadata.get("successCriteria"))
    prompt = _clean_string(task.get("prompt"))
    name = _clean_string(task.get("name") or task.get("taskName"))
    allowed = _list_field(metadata.get("allowedSystems")) + _list_field(task.get("allowedSystems")) + list(allowed_systems or [])
    if website_url:
        allowed.append(website_url)
        host = _host(website_url)
        if host:
            allowed.append(host)
    expected_artifacts = (
        _list_field(metadata.get("expectedArtifacts"))
        or _list_field(task.get("expectedArtifacts"))
        or ["trajectory_trace"]
    )
    return {
        "businessIntent": _clean_string(
            task.get("businessIntent")
            or metadata.get("businessIntent")
            or prompt
            or name
        ),
        "initialState": metadata.get("initialState")
        if isinstance(metadata.get("initialState"), dict)
        else {
            "url": _clean_string(task.get("initialUrl") or task.get("startUrl") or website_url),
            "state": metadata.get("startState") if isinstance(metadata.get("startState"), dict) else {},
        },
        "allowedSystems": _dedupe(allowed),
        "expectedArtifacts": _dedupe(expected_artifacts),
        "successCriteria": success_criteria,
        "riskClass": _clean_string(task.get("riskClass") or metadata.get("riskClass") or default_risk_class).lower(),
        "constraints": _list_field(metadata.get("constraints")) + _list_field(task.get("constraints")),
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
        "expectedArtifacts": contract["expectedArtifacts"],
        "riskClass": contract["riskClass"],
    }
