from __future__ import annotations

from typing import Any

from app.services.task_contracts import task_contract_from_record


VERTICAL_DEMO_ACTIONS = {
    "email_read": {
        "group": "integration",
        "area": "connectors",
        "severity": "high",
        "action": "Connect email read access through IMAP/Gmail tools or task allowed systems.",
    },
    "erp_lookup": {
        "group": "integration",
        "area": "connectors",
        "severity": "high",
        "action": "Expose an insurance ERP lookup tool or allowed system for claim status retrieval.",
    },
    "document_grounding": {
        "group": "integration",
        "area": "resources",
        "severity": "high",
        "action": "Attach governed knowledge resources or read tools for document grounding.",
    },
    "draft_artifact": {
        "group": "runtime",
        "area": "artifacts",
        "severity": "high",
        "action": "Declare draft_email as a first-class business artifact for the vertical flow.",
    },
    "approval_boundary": {
        "group": "runtime",
        "area": "approvals",
        "severity": "high",
        "action": "Declare human approval or send boundary before any final email side effect.",
    },
    "benchmark": {
        "group": "factory",
        "area": "evals",
        "severity": "high",
        "action": "Create benchmark tasks for the vertical workflow.",
    },
    "trajectory": {
        "group": "factory",
        "area": "trajectories",
        "severity": "high",
        "action": "Harvest and approve at least one trajectory for the vertical workflow.",
    },
    "skill_promotion": {
        "group": "factory",
        "area": "skills",
        "severity": "high",
        "action": "Promote the approved trajectory into a reusable skill package.",
    },
    "runtime_replay": {
        "group": "runtime",
        "area": "runtime",
        "severity": "high",
        "action": "Capture a passing runtime replay or eval run for the vertical flow.",
    },
}


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _list_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item or "").strip()]


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def vertical_demo_spec(benchmark: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _metadata(benchmark)
    vertical_demo = metadata.get("verticalDemo")
    if isinstance(vertical_demo, dict):
        return vertical_demo
    vertical_demo = benchmark.get("verticalDemo")
    return vertical_demo if isinstance(vertical_demo, dict) else None


def _check_evidence(
    key: str,
    *,
    expected_tools: list[str],
    allowed_systems: list[str],
    expected_artifacts: list[str],
    approval_boundaries: list[str],
    risk_classes: list[str],
    skill_ids: list[str],
    trajectory_ids: list[str],
    passing_runs: int,
    task_count: int,
) -> dict[str, Any]:
    email_tools = sorted({"imap.search_emails", "imap.read_email", "gmail.search_emails", "gmail.read_email"} & set(expected_tools))
    approval_tools = sorted({"api.human_approval", "smtp.send_email", "gmail.send_email"} & set(expected_tools))
    evidence: dict[str, list[str] | int] = {
        "tools": [],
        "systems": [],
        "artifacts": [],
        "boundaries": [],
        "riskClasses": [],
        "skillIds": [],
        "trajectoryIds": [],
        "passingRuns": passing_runs,
        "tasks": task_count,
    }
    missing: list[str] = []
    if key == "email_read":
        evidence["tools"] = email_tools
        evidence["systems"] = ["email"] if "email" in allowed_systems else []
        missing = [] if email_tools or "email" in allowed_systems else ["email system or read tool"]
    elif key == "erp_lookup":
        evidence["tools"] = [tool for tool in expected_tools if tool.startswith("erp.")]
        evidence["systems"] = ["insurance_erp"] if "insurance_erp" in allowed_systems else []
        missing = [] if evidence["tools"] or "insurance_erp" in allowed_systems else ["insurance ERP system or ERP lookup tool"]
    elif key == "document_grounding":
        evidence["tools"] = [tool for tool in expected_tools if tool.startswith("knowledge.")]
        evidence["systems"] = ["knowledge"] if "knowledge" in allowed_systems else []
        missing = [] if evidence["tools"] or "knowledge" in allowed_systems else ["knowledge system or document search tool"]
    elif key == "draft_artifact":
        evidence["artifacts"] = [artifact for artifact in expected_artifacts if artifact == "draft_email"]
        missing = [] if "draft_email" in expected_artifacts else ["draft_email artifact"]
    elif key == "approval_boundary":
        evidence["tools"] = approval_tools
        evidence["boundaries"] = approval_boundaries
        evidence["riskClasses"] = [risk for risk in risk_classes if risk == "send"]
        missing = [] if approval_tools or "send" in risk_classes or any("approval" in item or "send" in item for item in approval_boundaries) else ["human approval or send boundary"]
    elif key == "benchmark":
        missing = [] if task_count else ["benchmark task"]
    elif key == "trajectory":
        evidence["trajectoryIds"] = trajectory_ids
        missing = [] if trajectory_ids else ["approved/source trajectory"]
    elif key == "skill_promotion":
        evidence["skillIds"] = skill_ids
        missing = [] if skill_ids else ["promoted skill package"]
    elif key == "runtime_replay":
        missing = [] if passing_runs else ["passing replay/eval run"]
    return {
        "found": {k: v for k, v in evidence.items() if v},
        "missing": missing,
    }


_READINESS_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("integration", "Integration surface", ("email_read", "erp_lookup", "document_grounding")),
    ("factory", "Capability factory", ("benchmark", "trajectory", "skill_promotion")),
    ("runtime", "Runtime controls", ("draft_artifact", "approval_boundary", "runtime_replay")),
)

INSURANCE_FLOW_STEPS: tuple[tuple[str, str], ...] = (
    ("email_read", "Email read"),
    ("erp_lookup", "ERP lookup"),
    ("document_grounding", "Document grounding"),
    ("draft_artifact", "Draft artifact"),
    ("approval_boundary", "Approval boundary"),
    ("benchmark", "Benchmark"),
    ("trajectory", "Trajectory"),
    ("skill_promotion", "Skill promotion"),
    ("runtime_replay", "Runtime replay"),
)


def _readiness_state(total: int, ready: int) -> str:
    if not total:
        return "missing"
    return "ready" if ready == total else "partial" if ready else "missing"


def _operational_readiness(coverage: list[dict[str, Any]]) -> dict[str, Any]:
    coverage_by_key = {str(item.get("key") or ""): item for item in coverage}
    groups: list[dict[str, Any]] = []
    for key, label, coverage_keys in _READINESS_GROUPS:
        items = [coverage_by_key[item_key] for item_key in coverage_keys if item_key in coverage_by_key]
        ready_count = sum(1 for item in items if item.get("ready"))
        missing = [str(item.get("key") or "") for item in items if not item.get("ready")]
        groups.append(
            {
                "key": key,
                "label": label,
                "state": _readiness_state(len(items), ready_count),
                "readyCount": ready_count,
                "total": len(items),
                "missing": missing,
            }
        )
    total = sum(int(group["total"]) for group in groups)
    ready_count = sum(int(group["readyCount"]) for group in groups)
    missing_groups = [str(group["key"]) for group in groups if group.get("state") != "ready"]
    return {
        "state": _readiness_state(total, ready_count),
        "readyCount": ready_count,
        "total": total,
        "groups": groups,
        "missingGroups": missing_groups,
        "enterpriseReady": bool(total and ready_count == total and not missing_groups),
    }


def _operational_group_ready(payload: dict[str, Any], key: str) -> bool:
    readiness = payload.get("operationalReadiness")
    if not isinstance(readiness, dict):
        return False
    groups = readiness.get("groups")
    if not isinstance(groups, list):
        return False
    return any(isinstance(group, dict) and group.get("key") == key and group.get("state") == "ready" for group in groups)


def _runtime_replay_contract_ready(payload: dict[str, Any]) -> bool:
    proof_gate = payload.get("insuranceFlowProofGate") if isinstance(payload.get("insuranceFlowProofGate"), dict) else {}
    runtime_contract = (
        proof_gate.get("runtimeReplayContract")
        if isinstance(proof_gate.get("runtimeReplayContract"), dict)
        else {}
    )
    return bool(runtime_contract.get("ready"))


def _runtime_replay_contract_present(payload: dict[str, Any]) -> bool:
    proof_gate = payload.get("insuranceFlowProofGate") if isinstance(payload.get("insuranceFlowProofGate"), dict) else {}
    return isinstance(proof_gate.get("runtimeReplayContract"), dict)


def _vertical_smoke_gate(
    *,
    objective: str,
    operational_readiness: dict[str, Any],
    expected_artifacts: list[str],
    approval_boundaries: list[str],
    risk_classes: list[str],
    passing_runs: int,
) -> dict[str, Any]:
    boundary_text = " ".join([*approval_boundaries, *risk_classes]).lower()
    no_send_guard = bool(
        "draft" in boundary_text
        or "no_send" in boundary_text
        or "without_send" in boundary_text
        or "before_send" in boundary_text
        or "sin enviar" in objective.lower()
    )
    groups = operational_readiness.get("groups") if isinstance(operational_readiness.get("groups"), list) else []
    group_state = {
        str(group.get("key") or ""): str(group.get("state") or "")
        for group in groups
        if isinstance(group, dict)
    }
    checks = {
        "objectiveDeclared": bool(objective.strip()),
        "integrationReady": group_state.get("integration") == "ready",
        "factoryReady": group_state.get("factory") == "ready",
        "runtimeReady": group_state.get("runtime") == "ready",
        "draftArtifact": "draft_email" in expected_artifacts,
        "noFinalSendGuard": no_send_guard,
        "passingReplay": passing_runs > 0,
    }
    actions = {
        "objectiveDeclared": "Declare the vertical smoke objective for the insurance workflow.",
        "integrationReady": "Complete email, ERP and document grounding evidence.",
        "factoryReady": "Create benchmark, approved trajectory and promoted skill evidence.",
        "runtimeReady": "Capture draft artifact, approval boundary and runtime replay evidence.",
        "draftArtifact": "Produce draft_email as the business output instead of sending directly.",
        "noFinalSendGuard": "Declare a draft-only or before-send approval boundary for the final email.",
        "passingReplay": "Run a passing replay or eval for the insurance smoke flow.",
    }
    missing = [key for key, ready in checks.items() if not ready]
    return {
        "state": "ready" if not missing else "needs_hardening",
        "ready": not missing,
        "checks": checks,
        "missing": missing,
        "hardeningPlaybook": [
            {"gap": key, "count": 1, "area": "vertical_demo", "severity": "high", "action": actions[key]}
            for key in missing
        ],
    }


def _runtime_replay_contract(
    *,
    expected_artifacts: list[str],
    approval_boundaries: list[str],
    risk_classes: list[str],
    promoted_skill_ids: list[str],
    passing_runs: int,
) -> dict[str, Any]:
    boundary_text = " ".join([*approval_boundaries, *risk_classes]).lower()
    checks = {
        "agentRuntimeReplay": passing_runs > 0,
        "approvedSkillAvailable": bool(promoted_skill_ids),
        "draftArtifactOutput": "draft_email" in expected_artifacts,
        "approvalBoundaryBeforeSend": (
            "draft" in boundary_text
            or "no_send" in boundary_text
            or "without_send" in boundary_text
            or "before_send" in boundary_text
            or "approval" in boundary_text
            or "send" in boundary_text
        ),
    }
    actions = {
        "agentRuntimeReplay": "Run the approved insurance skill through AgentRuntime and record a passing replay.",
        "approvedSkillAvailable": "Promote the approved trajectory into a callable insurance skill before replay.",
        "draftArtifactOutput": "Assert the replay produces draft_email as the business artifact.",
        "approvalBoundaryBeforeSend": "Assert the replay stops at a human approval boundary before final email send.",
    }
    missing = [key for key, ready in checks.items() if not ready]
    return {
        "state": "ready" if not missing else "needs_hardening",
        "ready": not missing,
        "checks": checks,
        "requiredEvidence": [
            "passing AgentRuntime replay",
            "approved reusable insurance skill",
            "draft_email artifact output",
            "human approval boundary before final send",
        ],
        "missing": missing,
        "hardeningPlaybook": [
            {"gap": key, "count": 1, "group": "runtime", "area": "runtime", "severity": "high", "action": actions[key]}
            for key in missing
        ],
    }


def _insurance_flow_proof_gate(
    *,
    objective: str,
    coverage: list[dict[str, Any]],
    smoke_gate: dict[str, Any],
    runtime_replay_contract: dict[str, Any],
) -> dict[str, Any]:
    coverage_by_key = {str(item.get("key") or ""): item for item in coverage if isinstance(item, dict)}
    steps: list[dict[str, Any]] = []
    for key, label in INSURANCE_FLOW_STEPS:
        item = coverage_by_key.get(key) or {}
        steps.append(
            {
                "key": key,
                "label": label,
                "ready": bool(item.get("ready")),
                "evidenceFound": item.get("evidenceFound") if isinstance(item.get("evidenceFound"), dict) else {},
                "missingEvidence": item.get("missingEvidence") if isinstance(item.get("missingEvidence"), list) else [],
            }
        )
    missing_steps = [step["key"] for step in steps if not step["ready"]]
    smoke_ready = bool(smoke_gate.get("ready"))
    missing = [*missing_steps, *(["smoke_gate"] if not smoke_ready else [])]
    playbook: list[dict[str, Any]] = []
    for key in missing_steps:
        metadata = VERTICAL_DEMO_ACTIONS.get(key, {})
        playbook.append(
            {
                "gap": key,
                "count": 1,
                "group": metadata.get("group", "factory"),
                "area": metadata.get("area", "vertical_demo"),
                "severity": metadata.get("severity", "high"),
                "action": metadata.get("action", "Complete missing insurance flow proof evidence."),
            }
        )
    if not smoke_ready:
        playbook.append(
            {
                "gap": "smoke_gate",
                "count": 1,
                "group": "runtime",
                "area": "vertical_demo",
                "severity": "high",
                "action": "Complete the draft-only approval-safe smoke gate before using the insurance flow as enterprise proof.",
            }
        )
    return {
        "state": "ready" if not missing else "needs_hardening",
        "ready": not missing,
        "objective": objective,
        "steps": steps,
        "runtimeReplayContract": runtime_replay_contract,
        "readySteps": sum(1 for step in steps if step["ready"]),
        "totalSteps": len(steps),
        "missing": missing,
        "hardeningPlaybook": playbook,
    }


def _vertical_demo_playbook(demos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gap_counts: dict[str, int] = {}
    examples: dict[str, dict[str, str]] = {}
    for demo in demos:
        benchmark_id = str(demo.get("benchmarkId") or "")
        objective = str(demo.get("objective") or "")
        for item in demo.get("coverage") if isinstance(demo.get("coverage"), list) else []:
            if not isinstance(item, dict) or item.get("ready"):
                continue
            key = str(item.get("key") or "")
            if not key:
                continue
            gap_counts[key] = gap_counts.get(key, 0) + 1
            examples.setdefault(key, {"benchmarkId": benchmark_id, "objective": objective})
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        metadata = VERTICAL_DEMO_ACTIONS.get(
            gap,
            {
                "group": "factory",
                "area": "capabilities",
                "severity": "medium",
                "action": "Complete missing vertical demo evidence before enterprise promotion.",
            },
        )
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "group": metadata["group"],
                "area": metadata["area"],
                "severity": metadata["severity"],
                "action": metadata["action"],
                "example": examples.get(gap, {}),
            }
        )
    return playbook


def _vertical_smoke_playbook(demos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gap_counts: dict[str, int] = {}
    examples: dict[str, dict[str, str]] = {}
    for demo in demos:
        smoke_gate = demo.get("smokeGate") if isinstance(demo.get("smokeGate"), dict) else {}
        for item in smoke_gate.get("hardeningPlaybook") if isinstance(smoke_gate.get("hardeningPlaybook"), list) else []:
            if not isinstance(item, dict):
                continue
            gap = str(item.get("gap") or "")
            if not gap:
                continue
            gap_counts[gap] = gap_counts.get(gap, 0) + int(item.get("count") or 1)
            examples.setdefault(
                gap,
                {
                    "benchmarkId": str(demo.get("benchmarkId") or ""),
                    "objective": str(demo.get("objective") or ""),
                },
            )
    playbook: list[dict[str, Any]] = []
    for gap in sorted(gap_counts, key=lambda item: (-gap_counts[item], item)):
        playbook.append(
            {
                "gap": gap,
                "count": gap_counts[gap],
                "area": "vertical_demo",
                "severity": "high",
                "action": "Complete the insurance smoke gate before using the vertical demo as enterprise proof.",
                "example": examples.get(gap, {}),
            }
        )
    return playbook


def vertical_demo_payload(
    *,
    benchmark: dict[str, Any],
    tasks: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    metadata = _metadata(benchmark)
    vertical_demo = vertical_demo_spec(benchmark)
    if not vertical_demo:
        return None

    task_metadata = [_metadata(task) for task in tasks]
    task_contracts = [task_contract_from_record(task) for task in tasks]
    expected_tools = _dedupe(
        [
            tool
            for task, task_meta in zip(tasks, task_metadata, strict=False)
            for tool in [
                *_list_values(task_meta.get("expectedTools")),
                *_list_values(task.get("expectedTools")),
            ]
        ]
    )
    allowed_systems = _dedupe([system for contract in task_contracts for system in _list_values(contract.get("allowedSystems"))])
    expected_artifacts = _dedupe([artifact for contract in task_contracts for artifact in _list_values(contract.get("expectedArtifacts"))])
    approval_boundaries = _dedupe(
        [
            task_meta.get("initialState", {}).get("approvalBoundary")
            for task_meta in task_metadata
            if isinstance(task_meta.get("initialState"), dict)
        ]
    )
    risk_classes = _dedupe([contract.get("riskClass") for contract in task_contracts])
    skill_ids = _dedupe([skill.get("capabilityId") or skill.get("skillId") for skill in skills])
    trajectory_ids = _dedupe([trajectory_id for skill in skills for trajectory_id in _list_values(skill.get("trajectoryIds"))])
    labels = [str(run.get("label") or "pending").lower() for run in runs]
    passing_runs = labels.count("pass")
    promoted_statuses = {"published", "approved", "active", "production"}
    promoted_skills = [
        skill
        for skill in skills
        if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in promoted_statuses or skill.get("skillPackage")
    ]
    promoted_skill_ids = _dedupe([skill.get("capabilityId") or skill.get("skillId") for skill in promoted_skills])

    expected_tool_set = set(expected_tools)
    checks = {
        "email_read": bool({"imap.search_emails", "imap.read_email", "gmail.search_emails", "gmail.read_email"} & expected_tool_set) or "email" in allowed_systems,
        "erp_lookup": any(tool.startswith("erp.") for tool in expected_tools) or "insurance_erp" in allowed_systems,
        "document_grounding": any(tool.startswith("knowledge.") for tool in expected_tools) or "knowledge" in allowed_systems,
        "draft_artifact": "draft_email" in expected_artifacts,
        "approval_boundary": bool({"api.human_approval", "smtp.send_email", "gmail.send_email"} & expected_tool_set) or "send" in risk_classes or any("approval" in item or "send" in item for item in approval_boundaries),
        "benchmark": bool(tasks),
        "trajectory": bool(trajectory_ids),
        "skill_promotion": bool(promoted_skills),
        "runtime_replay": labels.count("pass") > 0,
    }

    coverage: list[dict[str, Any]] = []
    for item in vertical_demo.get("coverage") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        ready = bool(checks.get(key))
        check_evidence = _check_evidence(
            key,
            expected_tools=expected_tools,
            allowed_systems=allowed_systems,
            expected_artifacts=expected_artifacts,
            approval_boundaries=approval_boundaries,
            risk_classes=risk_classes,
            skill_ids=skill_ids,
            trajectory_ids=trajectory_ids,
            passing_runs=passing_runs,
            task_count=len(tasks),
        )
        coverage.append(
            {
                "key": key,
                "label": str(item.get("label") or key),
                "expectedEvidence": str(item.get("evidence") or ""),
                "ready": ready,
                "status": "ready" if ready else "missing",
                "evidenceFound": check_evidence["found"],
                "missingEvidence": check_evidence["missing"],
            }
        )
    total = len(coverage)
    ready_count = sum(1 for item in coverage if item.get("ready"))
    missing = [str(item.get("key") or "") for item in coverage if not item.get("ready")]
    operational_readiness = _operational_readiness(coverage)
    objective = str(vertical_demo.get("objective") or "")
    smoke_gate = _vertical_smoke_gate(
        objective=objective,
        operational_readiness=operational_readiness,
        expected_artifacts=expected_artifacts,
        approval_boundaries=approval_boundaries,
        risk_classes=risk_classes,
        passing_runs=passing_runs,
    )
    runtime_replay_contract = _runtime_replay_contract(
        expected_artifacts=expected_artifacts,
        approval_boundaries=approval_boundaries,
        risk_classes=risk_classes,
        promoted_skill_ids=promoted_skill_ids,
        passing_runs=passing_runs,
    )
    insurance_flow_proof_gate = _insurance_flow_proof_gate(
        objective=objective,
        coverage=coverage,
        smoke_gate=smoke_gate,
        runtime_replay_contract=runtime_replay_contract,
    )
    return {
        "benchmarkId": str(benchmark.get("benchmarkId") or ""),
        "objective": objective,
        "runtimePath": str(vertical_demo.get("runtimePath") or metadata.get("runtimePath") or ""),
        "vertical": str(metadata.get("vertical") or benchmark.get("vertical") or ""),
        "state": _readiness_state(total, ready_count),
        "readyCount": ready_count,
        "total": total,
        "missing": missing,
        "coverage": coverage,
        "operationalReadiness": operational_readiness,
        "smokeGate": smoke_gate,
        "insuranceFlowProofGate": insurance_flow_proof_gate,
        "evidence": {
            "expectedTools": expected_tools,
            "allowedSystems": allowed_systems,
            "expectedArtifacts": expected_artifacts,
            "approvalBoundaries": approval_boundaries,
            "riskClasses": risk_classes,
            "skillIds": skill_ids,
            "trajectoryIds": trajectory_ids,
            "passingRuns": passing_runs,
        },
        "nextActions": [
            f"Complete vertical demo evidence for: {', '.join(missing)}."
            if missing
            else "Vertical demo has benchmark, skill and runtime replay evidence."
        ],
    }


def summarize_vertical_demos(
    *,
    benchmarks: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    limit: int = 10,
) -> dict[str, Any]:
    tasks_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_benchmark.setdefault(str(task.get("benchmarkId") or ""), []).append(task)
    skills_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for skill in skills:
        benchmark_id = str(skill.get("benchmarkId") or "")
        if benchmark_id:
            skills_by_benchmark.setdefault(benchmark_id, []).append(skill)
    runs_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        benchmark_id = str(run.get("benchmarkId") or "")
        if benchmark_id:
            runs_by_benchmark.setdefault(benchmark_id, []).append(run)

    demos = [
        payload
        for benchmark in benchmarks
        if (
            payload := vertical_demo_payload(
                benchmark=benchmark,
                tasks=tasks_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), []),
                skills=skills_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), []),
                runs=runs_by_benchmark.get(str(benchmark.get("benchmarkId") or ""), runs),
            )
        )
    ]
    return {
        "total": len(demos),
        "ready": sum(1 for demo in demos if demo.get("state") == "ready"),
        "partial": sum(1 for demo in demos if demo.get("state") == "partial"),
        "missing": sum(1 for demo in demos if demo.get("state") == "missing"),
        "smokeReady": sum(1 for demo in demos if bool((demo.get("smokeGate") or {}).get("ready"))),
        "smokeBlocked": sum(1 for demo in demos if demo.get("smokeGate") and not (demo.get("smokeGate") or {}).get("ready")),
        "proofReady": sum(1 for demo in demos if bool((demo.get("insuranceFlowProofGate") or {}).get("ready"))),
        "proofBlocked": sum(1 for demo in demos if demo.get("insuranceFlowProofGate") and not (demo.get("insuranceFlowProofGate") or {}).get("ready")),
        "enterpriseReady": sum(1 for demo in demos if bool((demo.get("operationalReadiness") or {}).get("enterpriseReady"))),
        "integrationReady": sum(1 for demo in demos if _operational_group_ready(demo, "integration")),
        "factoryReady": sum(1 for demo in demos if _operational_group_ready(demo, "factory")),
        "runtimeReady": sum(1 for demo in demos if _operational_group_ready(demo, "runtime")),
        "replayContractReady": sum(1 for demo in demos if _runtime_replay_contract_ready(demo)),
        "replayContractBlocked": sum(1 for demo in demos if _runtime_replay_contract_present(demo) and not _runtime_replay_contract_ready(demo)),
        "hardeningPlaybook": _vertical_demo_playbook(demos),
        "smokeHardeningPlaybook": _vertical_smoke_playbook(demos),
        "demos": demos[:limit],
    }
