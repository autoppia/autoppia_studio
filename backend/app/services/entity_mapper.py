from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.request import Request, urlopen

from app.models.entity import EntityField, EntityRelationship


MAX_OPENAPI_BYTES = 5_000_000
HTTP_TIMEOUT_SECONDS = 15
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
NOISE_SCHEMA_NAMES = {
    "HTTPValidationError",
    "ValidationError",
    "TokenPair",
    "LoginRequest",
    "MessageResponse",
}
NOISE_SCHEMA_PREFIXES = ("Body_", "Agent")
NOISE_SCHEMA_SUFFIXES = ("Summary",)


def entity_name_from_schema(name: str) -> str:
    clean = re.sub(r"(Read|Create|Update|Patch|Upsert|Request|Response|Out|In|DTO|Schema)$", "", str(name or "").strip())
    clean = re.sub(r"[^A-Za-z0-9_ -]", "", clean).strip(" _-")
    return clean[:80] or str(name or "Entity")[:80]


def normalize_field_type(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type")
    fmt = schema.get("format")
    if "$ref" in schema:
        return "ref"
    if raw_type == "array":
        item = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        if "$ref" in item:
            return "ref[]"
        item_type = normalize_field_type(item) if item else "object"
        return f"{item_type}[]"
    if raw_type == "integer":
        return "integer"
    if raw_type == "number":
        return "number"
    if raw_type == "boolean":
        return "boolean"
    if raw_type == "object":
        return "object"
    if fmt in {"date", "date-time"}:
        return "date"
    if fmt == "uuid":
        return "string"
    return str(raw_type or "string")


def infer_field_role(name: str, schema: dict[str, Any]) -> str:
    lower = name.lower()
    fmt = str(schema.get("format") or "")
    field_type = str(schema.get("type") or "")
    if lower in {"id", "uuid"} or lower.endswith("_id") or lower.endswith("id"):
        return "identifier" if lower in {"id", "uuid"} else "reference"
    if lower in {"name", "title", "display_name", "label"}:
        return "display"
    if "status" in lower or "state" in lower:
        return "status"
    if fmt in {"date", "date-time"} or "date" in lower or "at" == lower[-2:]:
        return "date"
    if field_type == "number" or any(token in lower for token in ("amount", "total", "price", "balance")):
        return "amount"
    return ""


def ref_name(value: str) -> str:
    return str(value or "").rstrip("/").split("/")[-1]


def schema_ref_target(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return entity_name_from_schema(ref_name(str(schema.get("$ref") or "")))
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict) and "$ref" in schema["items"]:
        return entity_name_from_schema(ref_name(str(schema["items"].get("$ref") or "")))
    return ""


def relationship_kind(schema: dict[str, Any]) -> str:
    return "hasMany" if schema.get("type") == "array" else "belongsTo"


def field_from_property(name: str, schema: dict[str, Any], required: set[str]) -> EntityField:
    target = schema_ref_target(schema)
    role = infer_field_role(name, schema)
    return EntityField(
        name=name,
        type=normalize_field_type(schema),
        description=str(schema.get("description") or schema.get("title") or ""),
        role=role,
        required=name in required,
        ref=target,
        target=target,
    )


def relationship_from_property(name: str, schema: dict[str, Any]) -> EntityRelationship | None:
    target = schema_ref_target(schema)
    if not target:
        return None
    return EntityRelationship(
        name=name,
        kind=relationship_kind(schema),
        target=target,
        via=name if schema.get("type") != "array" else "",
        description=str(schema.get("description") or ""),
    )


def _snake(value: str) -> str:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", parts).strip("_").lower()


def _relationship_name_from_field(field_name: str, target: str) -> str:
    lower = field_name.lower()
    for suffix in ("_id", "id"):
        if lower.endswith(suffix) and len(lower) > len(suffix):
            return field_name[: -len(suffix)].strip("_") or target[:1].lower() + target[1:]
    return target[:1].lower() + target[1:]


def _infer_reference_target(field_name: str, entity_names: set[str]) -> str:
    lower = field_name.lower()
    if lower in {"id", "uuid"}:
        return ""
    if not (lower.endswith("_id") or lower.endswith("id")):
        return ""
    base = re.sub(r"_?id$", "", lower).strip("_")
    aliases: dict[str, str] = {}
    for entity_name in entity_names:
        snake = _snake(entity_name)
        aliases[snake] = entity_name
        aliases[snake.rstrip("s")] = entity_name
    if base in aliases:
        return aliases[base]
    for alias, entity_name in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and base.endswith(alias):
            return entity_name
    return ""


def _add_foreign_key_relationships(proposals: list[dict[str, Any]]) -> None:
    entity_names = {str(item.get("name") or "") for item in proposals if item.get("name")}
    for proposal in proposals:
        existing = {(rel.get("name"), rel.get("target"), rel.get("via")) for rel in proposal.get("relationships", []) if isinstance(rel, dict)}
        for field in proposal.get("fields", []):
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("name") or "")
            if field.get("target") or field.get("ref"):
                continue
            target = _infer_reference_target(field_name, entity_names)
            if not target or target == proposal.get("name"):
                continue
            field["target"] = target
            field["ref"] = target
            field["role"] = field.get("role") or "reference"
            rel = {
                "name": _relationship_name_from_field(field_name, target),
                "kind": "belongsTo",
                "target": target,
                "via": field_name,
                "description": f"Inferred from {field_name}.",
            }
            key = (rel["name"], rel["target"], rel["via"])
            if key not in existing:
                proposal.setdefault("relationships", []).append(rel)
                existing.add(key)


def _schema_is_entity_candidate(name: str, schema: dict[str, Any], used_refs: set[str], response_refs: set[str]) -> bool:
    if name in NOISE_SCHEMA_NAMES:
        return False
    if name.startswith(NOISE_SCHEMA_PREFIXES) or name.endswith(NOISE_SCHEMA_SUFFIXES):
        return False
    if not isinstance(schema, dict):
        return False
    if schema.get("type") != "object" and "properties" not in schema:
        return False
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if not properties:
        return False
    if name in used_refs or name in response_refs:
        return True
    if len(properties) >= 3:
        return True
    return any(str(field).lower() in {"id", "name", "email", "status"} for field in properties)


def _collect_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            refs.add(ref_name(ref))
        for item in value.values():
            refs.update(_collect_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_refs(item))
    return refs


def _operation_response_refs(openapi: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    paths = openapi.get("paths") if isinstance(openapi.get("paths"), dict) else {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if str(method).lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            responses = operation.get("responses") if isinstance(operation.get("responses"), dict) else {}
            for status, response in responses.items():
                if not str(status).startswith("2"):
                    continue
                refs.update(_collect_refs(response))
    return refs


def propose_entities_from_openapi(openapi: dict[str, Any], *, source_url: str = "") -> list[dict[str, Any]]:
    components = openapi.get("components") if isinstance(openapi.get("components"), dict) else {}
    schemas = components.get("schemas") if isinstance(components.get("schemas"), dict) else {}
    used_refs = _collect_refs(openapi.get("paths") or {})
    response_refs = _operation_response_refs(openapi)
    proposals: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for schema_name, schema in schemas.items():
        if not _schema_is_entity_candidate(str(schema_name), schema, used_refs, response_refs):
            continue
        entity_name = entity_name_from_schema(str(schema_name))
        if entity_name in seen_names:
            continue
        seen_names.add(entity_name)
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = set(schema.get("required") if isinstance(schema.get("required"), list) else [])
        fields = [field_from_property(str(name), prop if isinstance(prop, dict) else {}, required).model_dump() for name, prop in properties.items()]
        relationships = [
            rel.model_dump()
            for name, prop in properties.items()
            if isinstance(prop, dict)
            for rel in [relationship_from_property(str(name), prop)]
            if rel is not None
        ]
        proposals.append(
            {
                "name": entity_name,
                "description": str(schema.get("description") or schema.get("title") or f"{entity_name} entity inferred from OpenAPI schema {schema_name}."),
                "fields": fields,
                "relationships": relationships,
                "source": "openapi",
                "metadata": {"schemaName": schema_name, "sourceUrl": source_url},
            }
        )

    _add_foreign_key_relationships(proposals)
    proposals.sort(key=lambda item: (0 if any(field.get("role") == "identifier" for field in item.get("fields", [])) else 1, item["name"]))
    return proposals


def _fetch_json_sync(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Automata Entity Mapper/1.0"})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        content_type = str(response.headers.get("content-type") or "")
        raw = response.read(MAX_OPENAPI_BYTES + 1)
    if len(raw) > MAX_OPENAPI_BYTES:
        raise ValueError("OpenAPI document is too large")
    if "json" not in content_type and not url.endswith(".json"):
        text = raw.decode("utf-8", errors="replace")
        match = re.search(r"url:\s*['\"]([^'\"]+openapi\.json[^'\"]*)['\"]", text)
        if not match:
            raise ValueError("URL did not return JSON or a Swagger UI page pointing to openapi.json")
        from urllib.parse import urljoin

        return _fetch_json_sync(urljoin(url, match.group(1)))
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("OpenAPI document must be a JSON object")
    return parsed


async def fetch_openapi_json(url: str) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_json_sync, url)


async def propose_entities_from_openapi_url(url: str) -> list[dict[str, Any]]:
    openapi = await fetch_openapi_json(url)
    return propose_entities_from_openapi(openapi, source_url=url)
