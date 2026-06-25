from __future__ import annotations

from typing import Any


READ_EFFECTS = {"none", "read", "reads"}
WRITE_EFFECTS = {"write", "writes", "mutate", "mutates", "side_effect", "side_effects"}


def _clean(value: Any, default: str = "") -> str:
    clean = str(value or "").strip()
    return clean or default


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value if _clean(item)]


def _schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("type"):
        return dict(value)
    return {"type": "object", "properties": {}}


def _schema_typed(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties")
    return schema.get("type") == "object" and isinstance(properties, dict) and bool(properties)


def _policy_boundary(tool_name: str, side_effects: str) -> str:
    name = tool_name.lower()
    effects = side_effects.lower()
    if "send" in name or effects == "send":
        return "send"
    if any(token in name for token in ("draft", "compose", "artifact", "prepare")) or effects == "draft":
        return "draft"
    if effects in WRITE_EFFECTS or any(
        token in name
        for token in ("create", "update", "delete", "write", "post", "publish", "submit", "save", "upload", "call")
    ):
        return "write"
    return "read"


def risk_from_tool_contract(boundary: str, side_effects: str) -> str:
    if boundary == "send":
        return "high"
    if boundary == "write" or side_effects.lower() not in READ_EFFECTS | {"draft"}:
        return "medium"
    return "low"


def approval_policy_for_boundary(boundary: str) -> dict[str, Any]:
    required = boundary in {"write", "send"}
    return {
        "required": required,
        "mode": "always" if required else "never",
        "requiredFor": [boundary] if required else [],
        "humanReview": required,
    }


def normalize_tool_contract(
    raw_tool: dict[str, Any],
    *,
    connector: dict[str, Any] | None = None,
    toolkit: dict[str, Any] | None = None,
    execution_type: str = "",
    surface: str = "",
    runtime_requirements: list[Any] | None = None,
) -> dict[str, Any]:
    connector = connector or {}
    toolkit = toolkit or {}
    tool_name = _clean(raw_tool.get("name"), "tool")
    side_effects = _clean(raw_tool.get("sideEffects"), "reads").lower()
    input_schema = _schema(raw_tool.get("inputSchema"))
    output_schema = _schema(raw_tool.get("outputSchema") or {"type": "object", "additionalProperties": True})
    boundary = _policy_boundary(tool_name, side_effects)
    risk_level = _clean(raw_tool.get("riskLevel"), risk_from_tool_contract(boundary, side_effects)).lower()
    requirements = _list(runtime_requirements if runtime_requirements is not None else raw_tool.get("runtimeRequirements") or toolkit.get("runtimeRequirements") or [])
    input_entities = _list(raw_tool.get("inputEntities"))
    output_entity = _clean(raw_tool.get("outputEntity"))
    approval_policy = approval_policy_for_boundary(boundary)
    scopes = _list(raw_tool.get("scopes")) or [boundary]
    if connector.get("connectorId"):
        scopes.append(f"connector:{connector['connectorId']}")
    if surface:
        scopes.append(f"surface:{surface}")
    return {
        "format": "autoppia.tool_contract",
        "version": 1,
        "toolName": tool_name,
        "description": _clean(raw_tool.get("description")),
        "connectorId": _clean(connector.get("connectorId")),
        "connectorType": _clean(connector.get("type")),
        "executionType": execution_type,
        "surface": surface,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
        "schema": {
            "typed": _schema_typed(input_schema),
            "required": _list(input_schema.get("required")),
        },
        "sideEffects": side_effects,
        "policyBoundary": boundary,
        "riskLevel": risk_level,
        "runtimeRequirements": requirements,
        "scopes": sorted(set(scopes)),
        "entities": {
            "input": input_entities,
            "output": output_entity,
            "linked": bool(input_entities or output_entity),
        },
        "approvalPolicy": approval_policy,
        "permissions": {
            "connectorId": _clean(connector.get("connectorId")),
            "requiresApproval": approval_policy["required"],
            "approval": approval_policy["mode"],
            "scopes": sorted(set(scopes)),
        },
    }


def apply_tool_contract(
    raw_tool: dict[str, Any],
    *,
    connector: dict[str, Any] | None = None,
    toolkit: dict[str, Any] | None = None,
    execution_type: str = "",
    surface: str = "",
    runtime_requirements: list[Any] | None = None,
) -> dict[str, Any]:
    contract = normalize_tool_contract(
        raw_tool,
        connector=connector,
        toolkit=toolkit,
        execution_type=execution_type,
        surface=surface,
        runtime_requirements=runtime_requirements,
    )
    return {
        **raw_tool,
        "inputSchema": contract["inputSchema"],
        "outputSchema": contract["outputSchema"],
        "sideEffects": contract["sideEffects"],
        "policyBoundary": contract["policyBoundary"],
        "riskLevel": contract["riskLevel"],
        "runtimeRequirements": contract["runtimeRequirements"],
        "inputEntities": contract["entities"]["input"],
        "outputEntity": contract["entities"]["output"],
        "permissions": contract["permissions"],
        "approvalPolicy": contract["approvalPolicy"],
        "scopes": contract["scopes"],
        "toolContract": contract,
    }
