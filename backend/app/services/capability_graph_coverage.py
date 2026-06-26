from __future__ import annotations

from typing import Any

from app.services.resource_governance import resource_citable
from app.services.resource_governance import resource_contract
from app.services.resource_governance import resource_indexed
from app.services.resource_governance import resource_read_tools
from app.services.resource_governance import resource_vector_id
from app.services.runtime_policy import serialize_runtime_policy
from app.services.skill_lifecycle import skill_promotion_status
from app.services.skill_lifecycle import skill_version
from app.services.skill_lifecycle import skill_version_history
from app.services.skill_manifests import skill_package_assets
from app.services.skill_manifests import skill_io_contract
from app.services.skill_readiness import skill_reusability_ready
from app.services.task_contracts import task_contract_ready


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _sorted_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "count": counts[key]} for key in sorted(counts, key=lambda item: (-counts[item], item))]


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _runtime_state(doc: dict[str, Any]) -> dict[str, Any]:
    runtime_state = doc.get("runtimeState")
    return runtime_state if isinstance(runtime_state, dict) else {}


def _eval_run_label(run: dict[str, Any]) -> str:
    return str(run.get("label") or "pending").strip().lower() or "pending"


def _eval_run_timestamp(run: dict[str, Any]) -> str:
    for key in ("completedAt", "updatedAt", "createdAt", "startedAt"):
        value = str(run.get(key) or "").strip()
        if value:
            return value
    return ""


def _eval_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": str(run.get("runId") or ""),
        "evalId": str(run.get("evalId") or run.get("taskId") or ""),
        "benchmarkId": str(run.get("benchmarkId") or ""),
        "label": _eval_run_label(run),
        "createdAt": str(run.get("createdAt") or ""),
        "completedAt": str(run.get("completedAt") or ""),
    }


def _work_operational(doc: dict[str, Any]) -> dict[str, Any]:
    operational = doc.get("operational")
    return operational if isinstance(operational, dict) else {}


def _vertical_demo_group_ready(payload: dict[str, Any], key: str) -> bool:
    readiness = payload.get("operationalReadiness")
    if not isinstance(readiness, dict):
        return False
    groups = readiness.get("groups")
    if not isinstance(groups, list):
        return False
    return any(isinstance(group, dict) and group.get("key") == key and group.get("state") == "ready" for group in groups)


def _capability_boundary(doc: dict[str, Any]) -> str:
    explicit = str(doc.get("policyBoundary") or (doc.get("toolContract") if isinstance(doc.get("toolContract"), dict) else {}).get("policyBoundary") or "").strip().lower()
    if explicit in {"read", "draft", "write", "send"}:
        return explicit
    side_effects = str(doc.get("sideEffects") or "").strip().lower()
    if side_effects in {"sends", "send"}:
        return "send"
    if side_effects in {"writes", "write", "deletes", "delete", "mutates", "payments"}:
        return "write"
    if side_effects in {"drafts", "draft"}:
        return "draft"
    return "read"


def session_contract_coverage(doc: dict[str, Any]) -> dict[str, Any]:
    contract = doc.get("sessionContract") if isinstance(doc.get("sessionContract"), dict) else {}
    skill = contract.get("selectedSkill") if isinstance(contract.get("selectedSkill"), dict) else {}
    approvals = contract.get("approvalState") if isinstance(contract.get("approvalState"), dict) else {}
    artifacts = contract.get("artifactState") if isinstance(contract.get("artifactState"), dict) else {}
    cost = contract.get("costState") if isinstance(contract.get("costState"), dict) else {}
    trace = contract.get("traceState") if isinstance(contract.get("traceState"), dict) else {}
    runtime_state = _runtime_state(doc)
    trace_ids = _string_list(trace.get("traceIds") if isinstance(trace.get("traceIds"), list) else doc.get("traceIds"))
    skill_id = str(skill.get("skillId") or doc.get("matchedSkillId") or runtime_state.get("matchedSkillId") or "").strip()
    return {
        "withContract": bool(contract),
        "selectedSkill": bool(skill.get("matched") or skill_id),
        "pendingApprovals": int(approvals.get("pending") or doc.get("pendingApprovalCount") or 0),
        "artifactOutputs": int(artifacts.get("count") or doc.get("artifactCount") or 0),
        "traceIds": len(trace_ids),
        "replayReady": bool(trace.get("replayReady")),
        "creditsSpent": _safe_float(cost.get("creditsSpent") or doc.get("creditsSpent")),
    }


def skill_package_coverage(
    skill: dict[str, Any],
    *,
    trajectory_docs: list[dict[str, Any]],
    eval_run_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    package = skill.get("skillPackage") if isinstance(skill.get("skillPackage"), dict) else {}
    package_activation = package.get("activation") if isinstance(package.get("activation"), dict) else {}
    package_policies = package.get("policies") if isinstance(package.get("policies"), dict) else {}
    package_evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
    package_regression = package_evidence.get("regressionSuite") if isinstance(package_evidence.get("regressionSuite"), dict) else {}
    package_io = package.get("ioContract") if isinstance(package.get("ioContract"), dict) else {}
    package_outputs = package_io.get("outputs") if isinstance(package_io.get("outputs"), dict) else {}
    package_assets = package.get("assets") if isinstance(package.get("assets"), dict) else {}
    assets = skill_package_assets({**skill, **package_assets})
    trajectory_ids = _dedupe_strings([str(value or "") for value in skill.get("trajectoryIds") or []])
    linked_trajectories = [
        trajectory
        for trajectory in trajectory_docs
        if str(trajectory.get("trajectoryId") or "") in set(trajectory_ids)
    ]
    benchmark_ids = _dedupe_strings([
        str(skill.get("benchmarkId") or ""),
        *[str(trajectory.get("benchmarkId") or "") for trajectory in linked_trajectories],
        *[str(value or "") for value in package_regression.get("benchmarkIds") or []],
    ])
    eval_ids = _dedupe_strings([
        str(skill.get("evalId") or ""),
        *[str(trajectory.get("evalId") or "") for trajectory in linked_trajectories],
        *[str(trajectory.get("taskId") or "") for trajectory in linked_trajectories],
        *[str(value or "") for value in package_regression.get("evalIds") or []],
    ])
    linked_runs = [
        run
        for run in eval_run_docs
        if str(run.get("evalId") or "") in set(eval_ids)
        or str(run.get("benchmarkId") or "") in set(benchmark_ids)
    ]
    latest_regression = skill.get("latestRegression") if isinstance(skill.get("latestRegression"), dict) else package_evidence.get("latestRegression") if isinstance(package_evidence.get("latestRegression"), dict) else {}
    io_contract = skill_io_contract(skill)
    io_declared = bool(io_contract.get("declared") or package_io.get("declared"))
    expected_artifacts = _dedupe_strings([
        *[str(value or "") for value in skill.get("expectedArtifacts") or []],
        *[str(value or "") for value in package_outputs.get("artifacts") or []],
    ])
    source_trajectories = bool(trajectory_ids or linked_trajectories or package_evidence.get("sourceTrajectories"))
    activation = bool(str(skill.get("whenToUse") or package_activation.get("description") or "").strip())
    instructions = bool(str(skill.get("instructions") or "").strip())
    risk_policy = bool(str(skill.get("riskPolicy") or package_policies.get("riskPolicy") or "").strip() or package_policies.get("runtimePolicy") or skill.get("runtimePolicy"))
    regression = bool(linked_runs or latest_regression or package_regression.get("cases"))
    publishable_regression = bool(
        any(_eval_run_label(run) == "pass" for run in linked_runs)
        or str(latest_regression.get("label") or "").lower() == "pass"
        or package_regression.get("publishable")
    )
    manifest_ready = activation and instructions and risk_policy and source_trajectories and io_declared
    metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
    lifecycle_doc = {
        **skill,
        "promotionStatus": skill.get("promotionStatus") or metadata.get("promotionStatus"),
        "status": skill.get("status") or metadata.get("status"),
        "version": skill.get("version") or metadata.get("version"),
        "versionLabel": skill.get("versionLabel") or metadata.get("versionLabel"),
        "versionHistory": skill.get("versionHistory") if isinstance(skill.get("versionHistory"), list) else package_evidence.get("versionHistory"),
    }
    promotion_status = skill_promotion_status(lifecycle_doc)
    version = skill_version(lifecycle_doc)
    version_history = skill_version_history(lifecycle_doc, version=version, promotion_status=promotion_status)
    publishable = manifest_ready and publishable_regression
    return {
        "manifestReady": manifest_ready,
        "activation": activation,
        "instructions": instructions,
        "ioContract": io_declared,
        "expectedArtifacts": bool(expected_artifacts or skill.get("outputCard") or package_outputs.get("outputCard")),
        "riskPolicy": risk_policy,
        "sourceTrajectories": source_trajectories,
        "regressionSuite": regression,
        "assets": bool(assets.get("declared")),
        "resources": bool(assets.get("resources") or assets.get("resourceIds")),
        "scripts": bool(assets.get("scripts") or assets.get("scriptIds")),
        "publishable": publishable,
        "versioned": bool(skill.get("version") or skill.get("versionHistory") or package.get("manifestVersion")),
        "release": {
            "promotionStatus": promotion_status,
            "version": version,
            "versionLabel": lifecycle_doc.get("versionLabel") or f"v{version}",
            "published": promotion_status == "published",
            "readyForPublish": publishable and promotion_status in {"ready", "published"},
            "historyCount": len(version_history),
            "latestEvent": version_history[-1] if version_history else {},
        },
    }


def work_orchestration_coverage(work_item: dict[str, Any]) -> dict[str, Any]:
    operational = _work_operational(work_item)
    orchestration = operational.get("orchestration") if isinstance(operational.get("orchestration"), dict) else {}
    schedule = orchestration.get("schedule") if isinstance(orchestration.get("schedule"), dict) else {}
    budget = orchestration.get("budget") if isinstance(orchestration.get("budget"), dict) else {}
    retry = orchestration.get("retry") if isinstance(orchestration.get("retry"), dict) else {}
    approval = orchestration.get("approval") if isinstance(orchestration.get("approval"), dict) else {}
    sla = orchestration.get("sla") if isinstance(orchestration.get("sla"), dict) else {}
    automation_gate = orchestration.get("automationGate") if isinstance(orchestration.get("automationGate"), dict) else {}
    audit_trail = orchestration.get("auditTrail") if isinstance(orchestration.get("auditTrail"), dict) else {}
    browser_policy = orchestration.get("browserPolicy") if isinstance(orchestration.get("browserPolicy"), dict) else {}
    allowed_domains = _string_list(browser_policy.get("allowedDomains") if isinstance(browser_policy.get("allowedDomains"), list) else work_item.get("allowedDomains"))
    run_attempts = retry.get("runAttempts") or len(work_item.get("runHistory") if isinstance(work_item.get("runHistory"), list) else [])
    trigger_type = str(work_item.get("triggerType") or orchestration.get("triggerType") or "").lower()
    return {
        "withContract": bool(orchestration),
        "scheduled": trigger_type == "scheduled" or bool(schedule),
        "budgeted": bool(budget) or _safe_float(work_item.get("maxBudgetCredits") or work_item.get("maxCreditsPerRun")) > 0,
        "budgetExhausted": bool(budget.get("exhausted")),
        "retryConfigured": bool(retry) or _safe_int(work_item.get("maxSteps")) > 0,
        "runAttempts": _safe_int(run_attempts),
        "slaTracked": bool(sla) or bool(schedule.get("dueAt") or work_item.get("nextRunAt")),
        "slaNeedsAttention": bool(sla.get("needsAttention") or str(sla.get("state") or "").lower() in {"blocked", "overdue"}),
        "approvalGate": bool(approval or operational.get("reviewBlocked") or operational.get("pendingApprovalCount") or str(work_item.get("status") or "").upper() == "REVIEW"),
        "auditTrail": bool(audit_trail.get("uniform") or audit_trail.get("eventCount") or audit_trail.get("events")),
        "browserPolicy": bool(browser_policy) or bool(work_item.get("browserEnabled")),
        "browserAllowlist": bool(allowed_domains),
        "unattendedReady": bool(automation_gate.get("canRunUnattended")),
        "automationBlockers": _string_list(automation_gate.get("blockers")),
    }


def _coverage_playbook(
    *,
    task_total: int,
    task_complete: int,
    skill_total: int,
    publishable_skills: int,
    recent_failures: int,
    session_total: int,
    replay_ready_sessions: int,
    pending_approvals: int,
    work_blockers: dict[str, int],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if task_total > task_complete:
        gaps.append(
            {
                "gap": "incomplete_task_contracts",
                "count": task_total - task_complete,
                "area": "evals",
                "severity": "high",
                "action": "Complete task contracts before using benchmarks as production gates.",
            }
        )
    if skill_total > publishable_skills:
        gaps.append(
            {
                "gap": "skill_hardening",
                "count": skill_total - publishable_skills,
                "area": "capabilities",
                "severity": "high",
                "action": "Harden skill packages with IO, policy, source trajectories and passing regression evidence.",
            }
        )
    if recent_failures:
        gaps.append(
            {
                "gap": "failing_regressions",
                "count": recent_failures,
                "area": "evals",
                "severity": "high",
                "action": "Inspect recent failing eval runs before publishing or widening runtime access.",
            }
        )
    if session_total > replay_ready_sessions:
        gaps.append(
            {
                "gap": "runtime_replay",
                "count": session_total - replay_ready_sessions,
                "area": "runtime",
                "severity": "medium",
                "action": "Capture replay-ready traces for Runtime Lab sessions.",
            }
        )
    if pending_approvals:
        gaps.append(
            {
                "gap": "pending_approvals",
                "count": pending_approvals,
                "area": "approvals",
                "severity": "high",
                "action": "Resolve pending approvals blocking write/send boundaries.",
            }
        )
    for blocker in sorted(work_blockers, key=lambda item: (-work_blockers[item], item)):
        gaps.append(
            {
                "gap": f"work_{blocker}",
                "count": work_blockers[blocker],
                "area": "work",
                "severity": "high" if blocker in {"pending_approval", "budget_exhausted"} else "medium",
                "action": "Resolve Work Orchestration blockers before unattended operation.",
            }
        )
    return gaps


def _operational_graph_gate(edge_relations: set[Any]) -> dict[str, Any]:
    checks = {
        "factoryAssetsLinked": bool({"maps_entity", "input_entity", "output_entity"} & edge_relations)
        and bool({"exposes_tool", "read_by_tool", "used_by_skill"} & edge_relations)
        and bool({"contains_task", "produced_trajectory"} & edge_relations),
        "promotionPathLinked": {"produced_trajectory", "promoted_to"}.issubset(edge_relations),
        "evalsLinked": {"evaluated_by_run", "gates_skill"}.issubset(edge_relations),
        "runtimeEvidenceLinked": bool({"exercised_skill", "exercised_trajectory", "exercised_tool"} & edge_relations)
        and bool({"requires_approval", "produced_artifact"} & edge_relations),
        "workLinked": bool({"scheduled_from_task", "opened_session"} & edge_relations)
        and bool({"orchestrates_skill", "orchestrates_trajectory", "orchestrates_tool"} & edge_relations),
    }
    playbook_metadata = {
        "factoryAssetsLinked": {
            "area": "factory",
            "severity": "high",
            "action": "Link connectors, entities, tools and benchmark tasks inside the capability graph.",
        },
        "promotionPathLinked": {
            "area": "promotion",
            "severity": "high",
            "action": "Connect benchmark tasks to generated trajectories and promoted skills.",
        },
        "evalsLinked": {
            "area": "evals",
            "severity": "high",
            "action": "Attach eval runs to benchmark tasks and use passing runs as skill gates.",
        },
        "runtimeEvidenceLinked": {
            "area": "runtime",
            "severity": "high",
            "action": "Link Runtime Lab sessions to exercised capabilities, approvals and artifacts.",
        },
        "workLinked": {
            "area": "work",
            "severity": "medium",
            "action": "Connect Work Orchestration items to source tasks, sessions and capabilities.",
        },
    }
    hardening_playbook = [
        {
            "gap": key,
            "count": 1,
            **playbook_metadata[key],
        }
        for key, ready in checks.items()
        if not ready
    ]
    blockers = [
        {"name": item["gap"], "action": item["action"]}
        for item in hardening_playbook
    ]
    ready_count = sum(1 for ready in checks.values() if ready)
    ready = ready_count == len(checks)
    return {
        "state": "ready" if ready else "needs_hardening",
        "ready": ready,
        "readyCount": ready_count,
        "total": len(checks),
        "coverageRatio": round(ready_count / len(checks), 3) if checks else 1.0,
        "checks": checks,
        "blockers": blockers,
        "hardeningPlaybook": hardening_playbook,
    }


def capability_graph_coverage(
    *,
    entity_docs: list[dict[str, Any]],
    resource_docs: list[dict[str, Any]],
    vector_store_docs: list[dict[str, Any]],
    tool_docs: list[dict[str, Any]],
    benchmark_docs: list[dict[str, Any]],
    task_docs: list[dict[str, Any]],
    trajectory_docs: list[dict[str, Any]],
    skill_docs: list[dict[str, Any]],
    eval_run_docs: list[dict[str, Any]],
    session_docs: list[dict[str, Any]],
    approval_docs: list[dict[str, Any]],
    artifact_docs: list[dict[str, Any]],
    work_item_docs: list[dict[str, Any]],
    vertical_demo_payloads: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    edge_relations = {edge.get("relation") for edge in edges}
    operational_graph_gate = _operational_graph_gate(edge_relations)
    ready_tools = sum(1 for tool in tool_docs if str(tool.get("status") or "").lower() == "ready")
    ready_skills = sum(1 for skill in skill_docs if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in {"ready", "published", "approved"})
    reusable_skills = sum(1 for skill in skill_docs if skill_reusability_ready(skill))
    complete_tasks = sum(1 for task in task_docs if task_contract_ready(task))
    tool_policies = [(tool, serialize_runtime_policy(tool)) for tool in tool_docs]
    write_tools = [tool for tool in tool_docs if _capability_boundary(tool) in {"write", "send"}]
    skill_policies = [serialize_runtime_policy(skill) for skill in skill_docs]
    write_skills = [policy for policy in skill_policies if {"write", "send"} & set(policy.get("approvalRequiredFor") or [])]
    browser_skill_policies = [policy for policy in skill_policies if policy.get("browserRuntime")]
    browser_work_items = [item for item in work_item_docs if bool(item.get("browserEnabled", True))]
    write_tools_protected = all(
        "write" in set(policy.get("approvalRequiredFor") or [])
        for tool, policy in tool_policies
        if _capability_boundary(tool) == "write"
    )
    send_tools_protected = all(
        "send" in set(policy.get("approvalRequiredFor") or [])
        for tool, policy in tool_policies
        if _capability_boundary(tool) == "send"
    )
    write_skills_protected = all("write" in set(policy.get("approvalRequiredFor") or []) for policy in skill_policies)
    send_skills_protected = all("send" in set(policy.get("approvalRequiredFor") or []) for policy in skill_policies)
    browser_skills_sandboxed = all(bool((policy.get("browserPolicy") if isinstance(policy.get("browserPolicy"), dict) else {}).get("requiresSandbox")) for policy in browser_skill_policies)
    vector_store_ids = {str(store.get("vectorDatabaseId") or "") for store in vector_store_docs if str(store.get("vectorDatabaseId") or "")}
    resource_vector_ids = {
        resource_vector_id(resource)
        for resource in resource_docs
        if resource_vector_id(resource)
    }
    session_contracts = [session_contract_coverage(doc) for doc in session_docs]
    skill_packages = [
        skill_package_coverage(skill, trajectory_docs=trajectory_docs, eval_run_docs=eval_run_docs)
        for skill in skill_docs
    ]
    skill_release_statuses = [str(item.get("release", {}).get("promotionStatus") or "draft") for item in skill_packages]
    work_orchestration = [work_orchestration_coverage(item) for item in work_item_docs]
    work_automation_blockers: dict[str, int] = {}
    for item in work_orchestration:
        for blocker in item["automationBlockers"]:
            work_automation_blockers[blocker] = work_automation_blockers.get(blocker, 0) + 1
    recent_eval_runs = sorted(eval_run_docs, key=_eval_run_timestamp, reverse=True)
    recent_eval_failures = [run for run in recent_eval_runs if _eval_run_label(run) == "fail"]
    publishable_skills = sum(1 for item in skill_packages if item["publishable"])
    replay_ready_sessions = sum(1 for item in session_contracts if item["replayReady"])
    pending_approvals = sum(1 for item in approval_docs if str(item.get("status") or "").lower() == "pending")
    return {
        "entities": {"total": len(entity_docs), "linked": "input_entity" in edge_relations or "output_entity" in edge_relations},
        "resources": {
            "total": len(resource_docs),
            "indexed": sum(1 for resource in resource_docs if resource_indexed(resource)),
            "citable": sum(1 for resource in resource_docs if resource_citable(resource)),
            "withResourceContract": sum(1 for resource in resource_docs if bool(resource_contract(resource))),
            "withReadTools": sum(1 for resource in resource_docs if bool(resource_read_tools(resource))),
            "vectorStores": len(vector_store_docs),
            "linkedVectorStores": len(resource_vector_ids & vector_store_ids) if vector_store_ids else 0,
            "linkedToConnectors": "grounds_connector" in edge_relations,
            "linkedToTools": "read_by_tool" in edge_relations,
            "linkedToTasks": "grounds_task" in edge_relations,
            "linkedToSkills": "grounds_skill" in edge_relations,
        },
        "tools": {"total": len(tool_docs), "ready": ready_tools, "governed": sum(1 for tool in tool_docs if isinstance(tool.get("toolContract"), dict))},
        "policies": {
            "policyNodes": sum(1 for relation in edge_relations if relation in {"governed_by_boundary", "uses_approval_mode", "uses_browser_policy"}),
            "writeCapabilities": len(write_tools) + len(write_skills),
            "writesProtected": write_tools_protected and write_skills_protected,
            "sendProtected": send_tools_protected and send_skills_protected,
            "browserCapabilities": len(browser_skill_policies) + len(browser_work_items),
            "browserSandboxed": browser_skills_sandboxed and all(bool(item.get("browserEnabled", True)) for item in browser_work_items),
            "domainRestricted": "restricted_to_domains" in edge_relations,
            "highRiskTools": sum(1 for tool in tool_docs if str(tool.get("riskLevel") or "").lower() in {"high", "critical"}),
            "approvalModes": sorted({str(policy.get("approvalMode") or "auto") for policy in skill_policies} | {str((tool.get("permissions") if isinstance(tool.get("permissions"), dict) else {}).get("approval") or "auto") for tool in tool_docs}),
        },
        "benchmarks": {"total": len(benchmark_docs), "tasks": len(task_docs), "tasksWithContracts": complete_tasks},
        "verticalDemos": {
            "total": len(vertical_demo_payloads),
            "ready": sum(1 for item in vertical_demo_payloads if item.get("state") == "ready"),
            "partial": sum(1 for item in vertical_demo_payloads if item.get("state") == "partial"),
            "missing": sum(1 for item in vertical_demo_payloads if item.get("state") == "missing"),
            "enterpriseReady": sum(1 for item in vertical_demo_payloads if bool((item.get("operationalReadiness") or {}).get("enterpriseReady"))),
            "proofReady": sum(1 for item in vertical_demo_payloads if bool((item.get("insuranceFlowProofGate") or {}).get("ready"))),
            "proofBlocked": sum(1 for item in vertical_demo_payloads if item.get("insuranceFlowProofGate") and not bool((item.get("insuranceFlowProofGate") or {}).get("ready"))),
            "proofReadySteps": sum(int((item.get("insuranceFlowProofGate") or {}).get("readySteps") or 0) for item in vertical_demo_payloads),
            "proofTotalSteps": sum(int((item.get("insuranceFlowProofGate") or {}).get("totalSteps") or 0) for item in vertical_demo_payloads),
            "integrationReady": sum(1 for item in vertical_demo_payloads if _vertical_demo_group_ready(item, "integration")),
            "factoryReady": sum(1 for item in vertical_demo_payloads if _vertical_demo_group_ready(item, "factory")),
            "runtimeReady": sum(1 for item in vertical_demo_payloads if _vertical_demo_group_ready(item, "runtime")),
            "linkedToBenchmarks": "validates_vertical_demo" in edge_relations,
            "linkedToProofGate": "gated_by_proof" in edge_relations,
            "runtimeReplayReady": sum(1 for item in vertical_demo_payloads if int((item.get("evidence") or {}).get("passingRuns") or 0) > 0),
        },
        "evals": {
            "runs": len(eval_run_docs),
            "pass": sum(1 for run in eval_run_docs if _eval_run_label(run) == "pass"),
            "fail": sum(1 for run in eval_run_docs if _eval_run_label(run) == "fail"),
            "pending": sum(1 for run in eval_run_docs if _eval_run_label(run) == "pending"),
            "recentRuns": [_eval_run_summary(run) for run in recent_eval_runs[:5]],
            "recentFailures": [_eval_run_summary(run) for run in recent_eval_failures[:5]],
            "linkedToTasks": "evaluated_by_run" in edge_relations,
            "linkedToSkills": "gates_skill" in edge_relations,
            "linkedToRuntime": "replayed_session" in edge_relations,
        },
        "trajectories": {"total": len(trajectory_docs), "approved": sum(1 for item in trajectory_docs if str(item.get("status") or "").lower() == "approved")},
        "skills": {
            "total": len(skill_docs),
            "ready": ready_skills,
            "reusable": reusable_skills,
            "packages": {
                "manifestReady": sum(1 for item in skill_packages if item["manifestReady"]),
                "activation": sum(1 for item in skill_packages if item["activation"]),
                "instructions": sum(1 for item in skill_packages if item["instructions"]),
                "ioContracts": sum(1 for item in skill_packages if item["ioContract"]),
                "expectedArtifacts": sum(1 for item in skill_packages if item["expectedArtifacts"]),
                "riskPolicies": sum(1 for item in skill_packages if item["riskPolicy"]),
                "sourceTrajectories": sum(1 for item in skill_packages if item["sourceTrajectories"]),
                "regressionSuites": sum(1 for item in skill_packages if item["regressionSuite"]),
                "assets": sum(1 for item in skill_packages if item["assets"]),
                "resources": sum(1 for item in skill_packages if item["resources"]),
                "scripts": sum(1 for item in skill_packages if item["scripts"]),
                "publishable": publishable_skills,
                "versioned": sum(1 for item in skill_packages if item["versioned"]),
                "releaseStatus": _sorted_counts(skill_release_statuses),
                "releaseReadiness": {
                    "readyForPublish": sum(1 for item in skill_packages if item.get("release", {}).get("readyForPublish")),
                    "published": sum(1 for item in skill_packages if item.get("release", {}).get("published")),
                    "withVersionHistory": sum(1 for item in skill_packages if int(item.get("release", {}).get("historyCount") or 0) > 1),
                    "draft": skill_release_statuses.count("draft"),
                    "ready": skill_release_statuses.count("ready"),
                    "archived": skill_release_statuses.count("archived"),
                },
            },
        },
        "runtime": {
            "sessions": len(session_docs),
            "sessionContracts": {
                "withContract": sum(1 for item in session_contracts if item["withContract"]),
                "selectedSkill": sum(1 for item in session_contracts if item["selectedSkill"]),
                "pendingApprovals": sum(item["pendingApprovals"] for item in session_contracts),
                "artifactOutputs": sum(item["artifactOutputs"] for item in session_contracts),
                "traceIds": sum(item["traceIds"] for item in session_contracts),
                "replayReady": replay_ready_sessions,
                "creditsSpent": round(sum(item["creditsSpent"] for item in session_contracts), 4),
            },
            "approvals": len(approval_docs),
            "pendingApprovals": pending_approvals,
            "artifacts": len(artifact_docs),
            "linkedSessions": "exercised_skill" in edge_relations or "exercised_trajectory" in edge_relations or "exercised_tool" in edge_relations,
            "linkedApprovals": "requires_approval" in edge_relations,
            "linkedArtifacts": "produced_artifact" in edge_relations,
        },
        "work": {
            "total": len(work_item_docs),
            "scheduled": sum(1 for item in work_item_docs if str(item.get("triggerType") or "").lower() == "scheduled"),
            "running": sum(1 for item in work_item_docs if str(item.get("status") or "").upper() == "RUNNING"),
            "review": sum(1 for item in work_item_docs if str(item.get("status") or "").upper() == "REVIEW"),
            "blockedByApproval": sum(1 for item in work_item_docs if bool(_work_operational(item).get("reviewBlocked")) or str(item.get("status") or "").upper() == "REVIEW"),
            "orchestration": {
                "withContract": sum(1 for item in work_orchestration if item["withContract"]),
                "scheduled": sum(1 for item in work_orchestration if item["scheduled"]),
                "budgeted": sum(1 for item in work_orchestration if item["budgeted"]),
                "budgetExhausted": sum(1 for item in work_orchestration if item["budgetExhausted"]),
                "retryConfigured": sum(1 for item in work_orchestration if item["retryConfigured"]),
                "runAttempts": sum(item["runAttempts"] for item in work_orchestration),
                "slaTracked": sum(1 for item in work_orchestration if item["slaTracked"]),
                "slaNeedsAttention": sum(1 for item in work_orchestration if item["slaNeedsAttention"]),
                "approvalGates": sum(1 for item in work_orchestration if item["approvalGate"]),
                "auditTrails": sum(1 for item in work_orchestration if item["auditTrail"]),
                "browserPolicies": sum(1 for item in work_orchestration if item["browserPolicy"]),
                "browserAllowlists": sum(1 for item in work_orchestration if item["browserAllowlist"]),
                "unattendedReady": sum(1 for item in work_orchestration if item["unattendedReady"]),
                "unattendedBlocked": sum(1 for item in work_orchestration if item["automationBlockers"]),
                "automationBlockers": [{"name": key, "count": work_automation_blockers[key]} for key in sorted(work_automation_blockers, key=lambda item: (-work_automation_blockers[item], item))],
            },
            "linkedToTasks": "scheduled_from_task" in edge_relations,
            "linkedToRuntime": "opened_session" in edge_relations,
            "linkedToCapabilities": "orchestrates_skill" in edge_relations or "orchestrates_trajectory" in edge_relations or "orchestrates_tool" in edge_relations,
        },
        "promotionPath": {
            "hasTaskToTrajectory": "produced_trajectory" in edge_relations,
            "hasTrajectoryToSkill": "promoted_to" in edge_relations,
            "hasToolToSkill": "used_by_skill" in edge_relations,
        },
        "operationalGraphGate": operational_graph_gate,
        "coveragePlaybook": _coverage_playbook(
            task_total=len(task_docs),
            task_complete=complete_tasks,
            skill_total=len(skill_docs),
            publishable_skills=publishable_skills,
            recent_failures=len(recent_eval_failures),
            session_total=len(session_docs),
            replay_ready_sessions=replay_ready_sessions,
            pending_approvals=pending_approvals,
            work_blockers=work_automation_blockers,
        ),
    }
