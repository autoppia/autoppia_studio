from __future__ import annotations

from typing import Any

from app.routes.credentials import resolve_secret_refs


SECRET_PREFIX = "secret://credential/"


def contains_secret_ref(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith(SECRET_PREFIX)
    if isinstance(value, dict):
        return any(contains_secret_ref(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_secret_ref(item) for item in value)
    return False


def collect_secret_refs(value: Any, path: str = "") -> dict[str, str]:
    refs: dict[str, str] = {}
    if isinstance(value, str) and value.startswith(SECRET_PREFIX):
        refs[path] = value
    elif isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            refs.update(collect_secret_refs(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            next_path = f"{path}.{index}" if path else str(index)
            refs.update(collect_secret_refs(item, next_path))
    return refs


def _set_path(value: Any, path: str, replacement: str) -> Any:
    if not path:
        return replacement
    parts = path.split(".")
    cursor = value
    for part in parts[:-1]:
        if isinstance(cursor, list):
            cursor = cursor[int(part)]
        else:
            cursor = cursor[part]
    leaf = parts[-1]
    if isinstance(cursor, list):
        cursor[int(leaf)] = replacement
    else:
        cursor[leaf] = replacement
    return value


async def resolve_secret_refs_deep(value: Any) -> Any:
    refs = collect_secret_refs(value)
    if not refs:
        return value
    resolved = await resolve_secret_refs(refs)
    next_value = value.copy() if isinstance(value, dict) else list(value) if isinstance(value, list) else value
    for path, secret in resolved.items():
        next_value = _set_path(next_value, path, secret)
    return next_value


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        return "secret://credential/***" if value.startswith(SECRET_PREFIX) else value
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
