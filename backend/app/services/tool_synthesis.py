from __future__ import annotations

from typing import Any


GENERIC_DISCOVERY_TOOLS = {
    "api.discover_schema",
    "api.generate_toolkit",
    "api.call",
    "browser.open",
    "browser.click",
    "browser.type",
}


HARDENING_GAP_PLAYBOOK = {
    "typed_input_schema": {
        "area": "schema",
        "severity": "high",
        "action": "Define a typed input schema with required business identifiers.",
    },
    "typed_output_schema": {
        "area": "schema",
        "severity": "medium",
        "action": "Define a typed output schema so downstream skills can consume artifacts safely.",
    },
    "side_effects": {
        "area": "policy",
        "severity": "high",
        "action": "Declare whether the tool reads, drafts, writes or sends before runtime use.",
    },
    "risk_classification": {
        "area": "policy",
        "severity": "high",
        "action": "Classify risk level before exposing the tool to production agents.",
    },
    "approval_policy": {
        "area": "approvals",
        "severity": "high",
        "action": "Require human approval for write/send boundaries.",
    },
    "scopes": {
        "area": "permissions",
        "severity": "medium",
        "action": "Attach connector scopes or permission claims for least-privilege execution.",
    },
    "entity_bindings": {
        "area": "entities",
        "severity": "medium",
        "action": "Bind input and output business entities before promoting reusable skills.",
    },
    "tool_synthesis_pending": {
        "area": "capabilities",
        "severity": "high",
        "action": "Generate typed atomic tools with schemas, side effects, scopes and entity bindings.",
    },
}


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dedupe_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _schema_typed(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties")
    return schema.get("type") == "object" and isinstance(properties, dict) and bool(properties)


def _permission_list(permissions: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        raw = permissions.get(key)
        if isinstance(raw, str) and raw.strip():
            candidates = [raw.strip()]
        elif isinstance(raw, list):
            candidates = [str(item).strip() for item in raw if str(item).strip()]
        else:
            candidates = []
        for value in candidates:
            dedupe_key = value.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            values.append(value)
    return values


def _tool_contract(tool: dict[str, Any]) -> dict[str, Any]:
    return _dict(tool.get("toolContract"))


def _input_schema(tool: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _dict(tool.get("inputSchema")) or _dict(contract.get("inputSchema"))


def _output_schema(tool: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _dict(tool.get("outputSchema")) or _dict(contract.get("outputSchema"))


def _approval_policy(tool: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _dict(tool.get("approvalPolicy")) or _dict(contract.get("approvalPolicy"))


def _permissions(tool: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _dict(tool.get("permissions")) or _dict(contract.get("permissions"))


def _entities(tool: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    contract_entities = _dict(contract.get("entities"))
    inputs = _list_values(tool.get("inputEntities")) or _list_values(contract.get("inputEntities")) or _list_values(contract_entities.get("input"))
    output = str(tool.get("outputEntity") or contract.get("outputEntity") or contract_entities.get("output") or "").strip()
    return {"input": inputs, "output": output, "linked": bool(inputs or output)}


def _policy_boundary(tool_name: str, side_effects: str, contract: dict[str, Any]) -> str:
    explicit = str(contract.get("policyBoundary") or "").strip().lower()
    if explicit:
        return explicit
    name = tool_name.lower()
    effects = side_effects.lower()
    if "send" in name or effects in {"send", "sends"}:
        return "send"
    if any(token in name for token in ("draft", "compose", "artifact", "prepare")) or effects in {"draft", "drafts"}:
        return "draft"
    if effects in {"write", "writes", "delete", "deletes", "mutate", "mutates"} or any(
        token in name
        for token in ("create", "update", "delete", "write", "post", "publish", "submit", "save", "upload", "call")
    ):
        return "write"
    return "read"


def tool_synthesis_contract(tool: dict[str, Any]) -> dict[str, Any]:
    contract = _tool_contract(tool)
    name = str(tool.get("name") or contract.get("toolName") or "").strip()
    input_schema = _input_schema(tool, contract)
    output_schema = _output_schema(tool, contract)
    approval = _approval_policy(tool, contract)
    permissions = _permissions(tool, contract)
    entities = _entities(tool, contract)
    side_effects = str(tool.get("sideEffects") or contract.get("sideEffects") or "unknown").strip().lower()
    risk_level = str(tool.get("riskLevel") or contract.get("riskLevel") or "unknown").strip().lower()
    policy_boundary = str(tool.get("policyBoundary") or "").strip().lower() or _policy_boundary(name, side_effects, contract)
    scopes = _list_values(tool.get("scopes")) or _list_values(contract.get("scopes")) or _list_values(permissions.get("scopes"))
    typed = name not in GENERIC_DISCOVERY_TOOLS and _schema_typed(input_schema)
    return {
        "toolName": name,
        "typed": typed,
        "governed": bool(contract),
        "schema": {
            "inputTyped": _schema_typed(input_schema),
            "outputTyped": _schema_typed(output_schema),
            "required": _list_values(input_schema.get("required")),
        },
        "sideEffects": side_effects,
        "policyBoundary": policy_boundary,
        "riskLevel": risk_level,
        "approval": {
            "required": bool(approval.get("required") or permissions.get("requiresApproval")),
            "mode": str(approval.get("mode") or permissions.get("approval") or "never"),
            "requiredFor": _list_values(approval.get("requiredFor")),
        },
        "permissions": {
            "scopes": scopes,
            "connectorId": str(permissions.get("connectorId") or contract.get("connectorId") or ""),
        },
        "entities": entities,
        "runtimeRequirements": _list_values(tool.get("runtimeRequirements")) or _list_values(contract.get("runtimeRequirements")),
        "source": "tool_contract" if contract else "toolkit",
    }


def capability_tool_synthesis_contract(tool: dict[str, Any]) -> dict[str, Any]:
    """Legacy-compatible route payload backed by the shared synthesis contract."""
    contract = _tool_contract(tool)
    input_schema = _input_schema(tool, contract)
    output_schema = _output_schema(tool, contract)
    permissions = _permissions(tool, contract)
    synthesis = tool_synthesis_contract(
        {
            **tool,
            "sideEffects": tool.get("sideEffects") or contract.get("sideEffects") or "reads",
            "riskLevel": tool.get("riskLevel") or contract.get("riskLevel") or "low",
        }
    )
    side_effects = synthesis["sideEffects"] or "reads"
    risk_level = synthesis["riskLevel"] or "low"
    scopes = _permission_list(permissions, "scopes", "oauthScopes", "requiredScopes") or synthesis["permissions"]["scopes"]
    approval = str(permissions.get("approval") or "").strip()
    read_tools = _permission_list(permissions, "readTools")
    write_tools = _permission_list(permissions, "writeTools")
    gaps = []
    if not synthesis["schema"]["inputTyped"]:
        gaps.append("typed input schema")
    if not output_schema:
        gaps.append("output schema")
    if not side_effects:
        gaps.append("side effects")
    if not risk_level:
        gaps.append("risk classification")
    if side_effects.lower() in {"writes", "deletes", "sends"} and not approval:
        gaps.append("approval policy")
    if not scopes and not read_tools and not write_tools:
        gaps.append("scopes or permissions")
    entities = synthesis["entities"]
    return {
        "toolId": tool.get("toolId", ""),
        "action": synthesis["toolName"],
        "atomic": True,
        "typedInput": synthesis["schema"]["inputTyped"],
        "typedOutput": bool(output_schema),
        "sideEffects": side_effects,
        "riskLevel": risk_level,
        "policyBoundary": synthesis["policyBoundary"],
        "riskClassification": {
            "level": risk_level,
            "requiresApproval": bool(
                approval == "always"
                or side_effects.lower() in {"writes", "deletes", "sends"}
                or risk_level.lower() in {"high", "critical"}
            ),
            "approvalMode": approval or "auto",
        },
        "permissions": {
            "scopes": scopes,
            "readTools": read_tools,
            "writeTools": write_tools,
            "approval": approval or "auto",
        },
        "entityBindings": {
            "inputEntities": entities["input"],
            "outputEntity": entities["output"],
            "declared": bool(entities["linked"]),
        },
        "readiness": {
            "status": "ready" if not gaps else "needs_hardening",
            "gaps": gaps,
        },
    }


def tool_hardening_playbook(hardening_gaps: dict[str, int]) -> list[dict[str, Any]]:
    playbook: list[dict[str, Any]] = []
    for gap in sorted(hardening_gaps, key=lambda item: (-hardening_gaps[item], item)):
        metadata = HARDENING_GAP_PLAYBOOK.get(
            gap,
            {
                "area": "capabilities",
                "severity": "medium",
                "action": "Review and harden this tool contract before production use.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": hardening_gaps[gap],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
            }
        )
    return playbook


def _tool_production_gate(
    tools: list[dict[str, Any]],
    hardening_gaps: dict[str, int],
    needs_hardening_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = {
        "typedInputSchemas": bool(tools) and "typed_input_schema" not in hardening_gaps,
        "typedOutputSchemas": bool(tools) and "typed_output_schema" not in hardening_gaps,
        "sideEffectsDeclared": bool(tools) and "side_effects" not in hardening_gaps,
        "riskClassified": bool(tools) and "risk_classification" not in hardening_gaps,
        "approvalPolicies": bool(tools) and "approval_policy" not in hardening_gaps,
        "scopesDeclared": bool(tools) and "scopes" not in hardening_gaps,
        "entityBindings": bool(tools) and "entity_bindings" not in hardening_gaps,
    }
    ready = bool(tools) and all(checks.values()) and not needs_hardening_tools
    blockers = [
        {"name": key, "count": hardening_gaps[key]}
        for key in sorted(hardening_gaps, key=lambda item: (-hardening_gaps[item], item))
    ]
    if not tools:
        blockers.append({"name": "tool_synthesis_pending", "count": 1})
    return {
        "state": "ready" if ready else ("no_tools" if not tools else "needs_hardening"),
        "ready": ready,
        "checks": checks,
        "blockers": blockers,
        "hardeningPlaybook": tool_hardening_playbook(
            hardening_gaps if tools else {**hardening_gaps, "tool_synthesis_pending": 1}
        ),
    }


def summarize_tool_synthesis(tool_specs: list[dict[str, Any]], *, runtime_requirements: list[Any] | None = None) -> dict[str, Any]:
    tools = [tool_synthesis_contract(tool) for tool in tool_specs if isinstance(tool, dict)]
    typed_tools = [tool["toolName"] for tool in tools if tool["typed"]]
    governed_tools = [tool for tool in tools if tool["governed"]]
    write_tools = [
        tool["toolName"]
        for tool in tools
        if tool["sideEffects"] in {"write", "writes", "send", "mutate", "mutates"}
        or tool["policyBoundary"] in {"write", "send"}
    ]
    send_tools = [
        tool["toolName"]
        for tool in tools
        if tool["sideEffects"] in {"send", "sends"} or tool["policyBoundary"] == "send"
    ]
    approval_tools = [tool["toolName"] for tool in tools if tool["approval"]["required"]]
    risk_counts: dict[str, int] = {}
    boundary_counts: dict[str, int] = {}
    hardening_gaps: dict[str, int] = {}
    hardened_tools: list[str] = []
    publishable_tools: list[str] = []
    safe_atomic_tools: list[str] = []
    blocked_by_approval: list[str] = []
    needs_hardening_tools: list[dict[str, Any]] = []
    for tool in tools:
        risk = tool["riskLevel"] or "unknown"
        boundary = tool["policyBoundary"] or "unknown"
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
        boundary_counts[boundary] = boundary_counts.get(boundary, 0) + 1
        gaps: list[str] = []
        if not tool["schema"]["inputTyped"]:
            gaps.append("typed_input_schema")
        if not tool["schema"]["outputTyped"]:
            gaps.append("typed_output_schema")
        if tool["sideEffects"] in {"unknown", ""}:
            gaps.append("side_effects")
        if tool["riskLevel"] in {"unknown", ""}:
            gaps.append("risk_classification")
        if tool["policyBoundary"] in {"write", "send"} and not tool["approval"]["required"]:
            gaps.append("approval_policy")
        if not tool["permissions"]["scopes"]:
            gaps.append("scopes")
        if not tool["entities"]["linked"]:
            gaps.append("entity_bindings")
        if not gaps:
            hardened_tools.append(tool["toolName"])
            publishable_tools.append(tool["toolName"])
        else:
            needs_hardening_tools.append({"toolName": tool["toolName"], "gaps": gaps})
        safe_atomic = bool(
            tool["toolName"]
            and tool["toolName"] not in GENERIC_DISCOVERY_TOOLS
            and tool["policyBoundary"] == "read"
            and tool["sideEffects"] in {"read", "reads"}
            and tool["riskLevel"] in {"low", ""}
            and not tool["approval"]["required"]
            and not tool["schema"]["required"]
        )
        if safe_atomic:
            safe_atomic_tools.append(tool["toolName"])
        if "approval_policy" in gaps:
            blocked_by_approval.append(tool["toolName"])
        for gap in gaps:
            hardening_gaps[gap] = hardening_gaps.get(gap, 0) + 1
    return {
        "toolCount": len(tools),
        "typedToolCount": len(typed_tools),
        "governedToolCount": len(governed_tools),
        "typedTools": typed_tools,
        "hardenedToolCount": len(hardened_tools),
        "needsHardeningCount": len(tools) - len(hardened_tools),
        "hardenedTools": hardened_tools,
        "hardeningGaps": hardening_gaps,
        "hardeningPlaybook": tool_hardening_playbook(hardening_gaps),
        "productionGate": _tool_production_gate(tools, hardening_gaps, needs_hardening_tools),
        "promotionReadiness": {
            "publishable": _dedupe_values([*publishable_tools, *safe_atomic_tools]),
            "hardened": publishable_tools,
            "safeAtomicReadOnly": safe_atomic_tools,
            "needsHardening": needs_hardening_tools,
            "blockedByApproval": blocked_by_approval,
            "canPromoteCount": len(_dedupe_values([*publishable_tools, *safe_atomic_tools])),
            "blockedCount": len(needs_hardening_tools),
        },
        "writeToolCount": len(write_tools),
        "writeTools": write_tools,
        "sendToolCount": len(send_tools),
        "sendTools": send_tools,
        "approvalRequiredTools": approval_tools,
        "riskCounts": risk_counts,
        "policyBoundaryCounts": boundary_counts,
        "runtimeRequirements": _list_values(runtime_requirements),
        "tools": tools,
    }
