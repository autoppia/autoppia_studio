from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.assistant.context import AssistantContext
from app.database import (
    agents_collection,
    approvals_collection,
    artifacts_collection,
    assistant_conversations_collection,
    assistant_memories_collection,
    benchmarks_collection,
    benchmark_tasks_collection,
    capabilities_collection,
    companies_collection,
    connectors_collection,
    credentials_collection,
    entities_collection,
    eval_runs_collection,
    knowledge_documents_collection,
    profiles_collection,
    sessions_collection,
    tools_collection,
    trajectories_collection,
    usage_events_collection,
    users_collection,
    work_items_collection,
)
from app.services.queue import enqueue_job
from app.services.entity_mapper import propose_entities_from_openapi_url
from app.services.task_contracts import task_contract_from_record, task_contract_ready

SECRET_KEY_RE = re.compile(r"(secret|token|password|api[_-]?key|refresh|credential)", re.IGNORECASE)


def _clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in doc.items() if key != "_id"}
    return _mask_secrets(cleaned)


def _mask_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            masked[key] = "***" if SECRET_KEY_RE.search(str(key)) and item not in ("", None) else _mask_secrets(item)
        return masked
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    return value


async def _to_list(cursor: Any, limit: int = 20) -> list[dict[str, Any]]:
    docs = await cursor.to_list(length=limit)
    return [_clean_doc(doc) for doc in docs]


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}


def _skill_hardened(skill: dict[str, Any]) -> bool:
    return bool(
        str(skill.get("instructions") or "").strip()
        and (
            str(skill.get("whenToUse") or skill.get("activationDescription") or "").strip()
            or _list_values(skill.get("sourceTrajectoryIds"))
        )
        and (_list_values(skill.get("expectedArtifacts")) or _list_values(skill.get("preconditions")))
    )


def _resource_contract(doc: dict[str, Any]) -> dict[str, Any]:
    contract = doc.get("resourceContract")
    return contract if isinstance(contract, dict) else {}


def _resource_indexing(doc: dict[str, Any]) -> dict[str, Any]:
    contract = _resource_contract(doc)
    indexing = contract.get("indexing")
    return indexing if isinstance(indexing, dict) else {}


def _resource_governance(doc: dict[str, Any]) -> dict[str, Any]:
    contract = _resource_contract(doc)
    governance = contract.get("governance")
    return governance if isinstance(governance, dict) else {}


def _resource_read_tools(doc: dict[str, Any]) -> list[str]:
    contract = _resource_contract(doc)
    return _list_values(contract.get("readTools") or doc.get("readTools"))


def _resource_status(doc: dict[str, Any]) -> str:
    return str(doc.get("status") or _resource_contract(doc).get("status") or "unknown").strip().lower()


def _resource_indexed(doc: dict[str, Any]) -> bool:
    indexing = _resource_indexing(doc)
    if isinstance(indexing.get("indexed"), bool):
        return indexing["indexed"]
    return _resource_status(doc) in {"indexed", "ready", "active", "completed"}


def _resource_citable(doc: dict[str, Any]) -> bool:
    governance = _resource_governance(doc)
    citability = governance.get("citability")
    if isinstance(citability, dict) and isinstance(citability.get("citable"), bool):
        return citability["citable"]
    return _resource_indexed(doc)


def _resource_vector_id(doc: dict[str, Any]) -> str:
    indexing = _resource_indexing(doc)
    return str(doc.get("vectorDatabaseId") or indexing.get("vectorDatabaseId") or "").strip()


def _resource_governance_summary(docs: list[dict[str, Any]]) -> dict[str, Any]:
    read_tools = _dedupe([tool for doc in docs for tool in _resource_read_tools(doc)])
    sample = []
    for doc in docs[:8]:
        governance = _resource_governance(doc)
        freshness = governance.get("freshness") if isinstance(governance.get("freshness"), dict) else {}
        citability = governance.get("citability") if isinstance(governance.get("citability"), dict) else {}
        sample.append({
            "documentId": str(doc.get("documentId") or ""),
            "resourceId": str(doc.get("resourceId") or doc.get("documentId") or ""),
            "name": str(doc.get("filename") or doc.get("name") or "Untitled resource"),
            "status": _resource_status(doc),
            "indexed": _resource_indexed(doc),
            "citable": _resource_citable(doc),
            "freshnessStatus": str(freshness.get("status") or ("current" if _resource_indexed(doc) else "indexing")),
            "citationLabel": str(citability.get("citationLabel") or doc.get("filename") or ""),
            "vectorDatabaseId": _resource_vector_id(doc),
            "readTools": _resource_read_tools(doc)[:8],
        })
    total = len(docs)
    indexed = sum(1 for doc in docs if _resource_indexed(doc))
    citable = sum(1 for doc in docs if _resource_citable(doc))
    with_contract = sum(1 for doc in docs if _resource_contract(doc))
    with_vector_store = sum(1 for doc in docs if _resource_vector_id(doc))
    gaps = [
        gap
        for gap in [
            {"key": "resource_contracts", "label": "Knowledge documents exist but are not exposed as governed resources.", "target": "knowledge"} if total and with_contract == 0 else None,
            {"key": "resource_indexing", "label": "Knowledge resources exist but none are indexed for retrieval.", "target": "knowledge"} if total and indexed == 0 else None,
            {"key": "resource_citations", "label": "Knowledge resources are not citable yet, so answers cannot cite source evidence.", "target": "knowledge"} if total and citable == 0 else None,
            {"key": "resource_read_tools", "label": "Knowledge resources need read-only tools before AgentRuntimes can ground work in them.", "target": "knowledge"} if total and not read_tools else None,
            {"key": "vector_store", "label": "Knowledge resources are not linked to vector stores.", "target": "knowledge"} if total and with_vector_store == 0 else None,
        ]
        if gap
    ]
    return {
        "total": total,
        "indexed": indexed,
        "citable": citable,
        "withResourceContract": with_contract,
        "withVectorStore": with_vector_store,
        "readTools": read_tools[:20],
        "sample": sample,
        "ready": bool(total and indexed == total and citable == total and with_contract == total and with_vector_store == total and read_tools),
        "gaps": gaps,
    }


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _work_retry_count(doc: dict[str, Any]) -> int:
    history = doc.get("runHistory") if isinstance(doc.get("runHistory"), list) else []
    return max(0, len(history) - 1)


def _work_credits_spent(doc: dict[str, Any]) -> float:
    report = doc.get("report") if isinstance(doc.get("report"), dict) else {}
    return _safe_float(report.get("creditsSpent"))


def _surface_status(ready: bool) -> str:
    return "ready" if ready else "needs_work"


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _vertical_demo_summary(
    *,
    benchmarks: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    vertical_benchmarks = [
        benchmark
        for benchmark in benchmarks
        if isinstance(_metadata(benchmark).get("verticalDemo"), dict) or isinstance(benchmark.get("verticalDemo"), dict)
    ]
    tasks_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_benchmark.setdefault(str(task.get("benchmarkId") or ""), []).append(task)
    skills_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    for skill in skills:
        benchmark_id = str(skill.get("benchmarkId") or "")
        if benchmark_id:
            skills_by_benchmark.setdefault(benchmark_id, []).append(skill)
    runs_by_eval = {str(run.get("evalId") or ""): str(run.get("label") or "").lower() for run in runs}
    demos: list[dict[str, Any]] = []
    for benchmark in vertical_benchmarks:
        benchmark_id = str(benchmark.get("benchmarkId") or "")
        metadata = _metadata(benchmark)
        vertical_demo = metadata.get("verticalDemo") if isinstance(metadata.get("verticalDemo"), dict) else benchmark.get("verticalDemo")
        benchmark_tasks = tasks_by_benchmark.get(benchmark_id, [])
        benchmark_skills = skills_by_benchmark.get(benchmark_id, [])
        task_metadata = [_metadata(task) for task in benchmark_tasks]
        expected_tools = _dedupe([tool for metadata in task_metadata for tool in _list_values(metadata.get("expectedTools"))])
        allowed_systems = _dedupe([system for metadata in task_metadata for system in _list_values(metadata.get("allowedSystems"))])
        expected_artifacts = _dedupe([artifact for metadata in task_metadata for artifact in _list_values(metadata.get("expectedArtifacts"))])
        approval_boundaries = _dedupe([
            metadata.get("initialState", {}).get("approvalBoundary")
            for metadata in task_metadata
            if isinstance(metadata.get("initialState"), dict)
        ])
        risk_classes = _dedupe([metadata.get("riskClass") for metadata in task_metadata])
        trajectory_ids = _dedupe([trajectory_id for skill in benchmark_skills for trajectory_id in _list_values(skill.get("trajectoryIds"))])
        promoted_skills = [
            skill
            for skill in benchmark_skills
            if str(skill.get("promotionStatus") or skill.get("status") or "").lower() in {"published", "approved", "active", "production"} or skill.get("skillPackage")
        ]
        eval_ids = _dedupe([task.get("taskId") or task.get("evalId") for task in benchmark_tasks])
        passing_runs = sum(1 for eval_id in eval_ids if runs_by_eval.get(eval_id) == "pass")
        checks = {
            "email_read": bool({"imap.search_emails", "imap.read_email", "gmail.search_emails", "gmail.read_email"} & set(expected_tools)) or "email" in allowed_systems,
            "erp_lookup": any(tool.startswith("erp.") for tool in expected_tools) or "insurance_erp" in allowed_systems,
            "document_grounding": any(tool.startswith("knowledge.") for tool in expected_tools) or "knowledge" in allowed_systems,
            "draft_artifact": "draft_email" in expected_artifacts,
            "approval_boundary": bool({"api.human_approval", "smtp.send_email", "gmail.send_email"} & set(expected_tools)) or "send" in risk_classes or any("approval" in item or "send" in item for item in approval_boundaries),
            "benchmark": bool(benchmark_tasks),
            "trajectory": bool(trajectory_ids),
            "skill_promotion": bool(promoted_skills),
            "runtime_replay": passing_runs > 0,
        }
        coverage = []
        for item in (vertical_demo.get("coverage") if isinstance(vertical_demo, dict) else []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            coverage.append({"key": key, "label": str(item.get("label") or key), "ready": bool(checks.get(key))})
        ready_count = sum(1 for item in coverage if item["ready"])
        total = len(coverage)
        demos.append({
            "benchmarkId": benchmark_id,
            "vertical": str(metadata.get("vertical") or benchmark.get("vertical") or ""),
            "objective": str((vertical_demo or {}).get("objective") or ""),
            "runtimePath": str((vertical_demo or {}).get("runtimePath") or ""),
            "state": "ready" if total and ready_count == total else "partial" if ready_count else "missing",
            "readyCount": ready_count,
            "total": total,
            "missing": [item["key"] for item in coverage if not item["ready"]],
        })
    ready = sum(1 for demo in demos if demo["state"] == "ready")
    return {
        "total": len(demos),
        "ready": ready,
        "partial": sum(1 for demo in demos if demo["state"] == "partial"),
        "missing": sum(1 for demo in demos if demo["state"] == "missing"),
        "demos": demos[:10],
    }


class AutomataAssistantTools:
    """Scoped tools available to the internal Automata Assistant."""

    def __init__(self, context: AssistantContext):
        self.context = context

    def _query(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {"email": self.context.email}
        if self.context.company_id:
            query["companyId"] = self.context.company_id
        query.update(extra or {})
        return query

    async def _count(self, collection: Any, query: dict[str, Any]) -> int:
        return int(await collection.count_documents(query))

    async def studio_snapshot(self) -> dict[str, Any]:
        companies = await _to_list(companies_collection.find({"email": self.context.email}, {"_id": 0}).sort("createdAt", 1), 10)
        company_id = self.context.company_id or (companies[0].get("companyId", "") if companies else "")
        scoped = {"email": self.context.email, **({"companyId": company_id} if company_id else {})}
        connected_connectors = await self._count(connectors_collection, {**scoped, "status": {"$in": ["connected", "ready", "active", "authenticated"]}})
        approved_skills = await self._count(capabilities_collection, {**scoped, "capabilityKind": "skill", "status": {"$in": ["approved", "published", "production"]}})
        approved_trajectories = await self._count(trajectories_collection, {**scoped, "status": {"$in": ["approved", "accepted"]}})
        passing_runs = await self._count(eval_runs_collection, {**scoped, "label": "pass"})
        failing_runs = await self._count(eval_runs_collection, {**scoped, "label": "fail"})
        pending_approvals = await self._count(approvals_collection, {**scoped, "status": "pending"})
        scheduled_work = await self._count(work_items_collection, {**scoped, "triggerType": "scheduled"})
        running_work = await self._count(work_items_collection, {**scoped, "status": "RUNNING"})
        skill_docs = await _to_list(capabilities_collection.find({**scoped, "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", -1), 500)
        tool_docs = await _to_list(tools_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 500)
        benchmark_docs = await _to_list(benchmarks_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 500)
        task_docs = await _to_list(benchmark_tasks_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 1000)
        eval_run_docs = await _to_list(eval_runs_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 1000)
        knowledge_docs = await _to_list(knowledge_documents_collection.find(scoped, {"_id": 0, "storagePath": 0}).sort("createdAt", -1), 1000)
        work_docs = await _to_list(work_items_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 1000)
        approval_docs = await _to_list(approvals_collection.find(scoped, {"_id": 0}).sort("createdAt", -1), 1000)
        counts = {
            "companies": len(companies),
            "agents": await agents_collection.count_documents(scoped),
            "connectors": await connectors_collection.count_documents(scoped),
            "credentials": await credentials_collection.count_documents(scoped),
            "knowledgeDocuments": await knowledge_documents_collection.count_documents(scoped),
            "entities": await entities_collection.count_documents(scoped),
            "skills": await capabilities_collection.count_documents({**scoped, "capabilityKind": "skill"}),
            "tools": await tools_collection.count_documents(scoped),
            "benchmarkTasks": await benchmark_tasks_collection.count_documents(scoped),
            "trajectories": await trajectories_collection.count_documents(scoped),
            "sessions": await sessions_collection.count_documents(scoped),
            "artifacts": await artifacts_collection.count_documents(scoped),
            "workItems": await work_items_collection.count_documents(scoped),
            "pendingApprovals": pending_approvals,
        }
        task_contracts = [task_contract_from_record(task) for task in task_docs]
        task_contracts_ready = sum(1 for task in task_docs if task_contract_ready(task))
        task_expected_artifacts = sorted({artifact for contract in task_contracts for artifact in _list_values(contract.get("expectedArtifacts"))})
        task_allowed_systems = sorted({system for contract in task_contracts for system in _list_values(contract.get("allowedSystems"))})
        hardened_skills = sum(1 for skill in skill_docs if _skill_hardened(skill))
        skill_expected_artifacts = sorted({artifact for skill in skill_docs for artifact in _list_values(skill.get("expectedArtifacts"))})
        typed_tools = sum(1 for tool in tool_docs if _list_values(tool.get("inputEntities")) or str(tool.get("outputEntity") or "").strip())
        vertical_demos = _vertical_demo_summary(benchmarks=benchmark_docs, tasks=task_docs, skills=skill_docs, runs=eval_run_docs)
        resource_map = _resource_governance_summary(knowledge_docs)
        now_dt = datetime.now(timezone.utc)
        work_item_ids = {str(doc.get("workItemId") or "") for doc in work_docs if str(doc.get("workItemId") or "")}
        pending_approval_work_item_ids = {
            str(_metadata(approval).get("workItemId") or "")
            for approval in approval_docs
            if str(approval.get("status") or "") == "pending"
        }
        pending_approval_work_item_ids = {item for item in pending_approval_work_item_ids if item in work_item_ids}
        scheduled_docs = [doc for doc in work_docs if str(doc.get("triggerType") or "manual") == "scheduled"]
        scheduled_due = sum(
            1
            for doc in scheduled_docs
            if (parsed := _parse_iso_datetime(doc.get("nextRunAt"))) is not None and parsed <= now_dt
        )
        budgeted_docs = [doc for doc in work_docs if _safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun"))) > 0]
        budget_exhausted = sum(
            1
            for doc in budgeted_docs
            if _work_credits_spent(doc) >= _safe_float(doc.get("maxBudgetCredits", doc.get("maxCreditsPerRun")))
        )
        review_blocked = sum(
            1
            for doc in work_docs
            if str(doc.get("status") or "") == "REVIEW"
            or str((doc.get("pendingApproval") if isinstance(doc.get("pendingApproval"), dict) else {}).get("approvalId") or "")
            or str(doc.get("workItemId") or "") in pending_approval_work_item_ids
        )
        total_retries = sum(_work_retry_count(doc) for doc in work_docs)
        readiness_checks = [
            {"key": "company", "ready": bool(company_id), "label": "Company context selected", "nextAction": "Create or select the enterprise/company workspace."},
            {"key": "connectors", "ready": counts["connectors"] > 0, "label": "Systems mapped", "nextAction": "Add the ERP/CRM/email/document connectors that define the operating surface."},
            {"key": "credentials", "ready": counts["credentials"] > 0 or connected_connectors > 0, "label": "Access configured", "nextAction": "Attach credentials or OAuth profiles for connectors that need authenticated runtime access."},
            {"key": "knowledge", "ready": counts["knowledgeDocuments"] > 0, "label": "Knowledge resources loaded", "nextAction": "Ingest policies, process docs, FAQs, product sheets, and compliance references."},
            {"key": "entities", "ready": counts["entities"] > 0, "label": "Business entities modeled", "nextAction": "Generate or define domain entities from OpenAPI/schema/docs before publishing tools."},
            {"key": "tools", "ready": counts["tools"] > 0, "label": "Typed tools available", "nextAction": "Publish typed connector tools with schemas, side effects, permissions, and entity links."},
            {"key": "benchmarks", "ready": counts["benchmarkTasks"] > 0, "label": "Benchmark tasks defined", "nextAction": "Convert real business tasks into benchmark cases with success criteria and risk class."},
            {"key": "skills", "ready": counts["skills"] > 0, "label": "Skills promoted", "nextAction": "Promote approved trajectories into reusable skills with runtime policy and regression evidence."},
            {"key": "runtime", "ready": counts["sessions"] > 0, "label": "Runtime exercised", "nextAction": "Run an AgentRuntime session and inspect tool calls, approvals, artifacts, and traces."},
            {"key": "work", "ready": counts["workItems"] > 0, "label": "Work orchestration configured", "nextAction": "Create operational work items with triggers, budgets, retries, SLAs, and approval rules."},
        ]
        ready_count = sum(1 for item in readiness_checks if item["ready"])
        recommended_actions = [
            {"area": item["key"], "action": item["nextAction"], "reason": item["label"]}
            for item in readiness_checks
            if not item["ready"]
        ]
        if pending_approvals:
            recommended_actions.insert(0, {"area": "approvals", "action": "Review pending approvals before continuing automated work.", "reason": f"{pending_approvals} approval(s) are blocking execution."})
        if scheduled_due:
            recommended_actions.insert(0, {"area": "work", "action": "Run or reschedule due scheduled work items.", "reason": f"{scheduled_due} scheduled work item(s) are due."})
        if budget_exhausted:
            recommended_actions.insert(0, {"area": "work", "action": "Review exhausted work budgets before retrying jobs.", "reason": f"{budget_exhausted} work item(s) exhausted their budget."})
        if counts["benchmarkTasks"] and task_contracts_ready == 0:
            recommended_actions.insert(0, {"area": "evals", "action": "Complete task contracts with business intent, allowed systems, artifacts, and risk class.", "reason": "Benchmark tasks exist but none are enterprise-ready."})
        if resource_map["total"] and not resource_map["ready"]:
            first_gap = resource_map["gaps"][0]["label"] if resource_map["gaps"] else "Knowledge resources are not ready for governed runtime grounding."
            recommended_actions.insert(0, {"area": "knowledge", "action": "Finish resource governance before relying on knowledge grounding in skills.", "reason": first_gap})
        if vertical_demos["total"] and vertical_demos["ready"] < vertical_demos["total"]:
            missing = ", ".join(vertical_demos["demos"][0].get("missing") or [])
            recommended_actions.insert(0, {"area": "evals", "action": "Complete vertical demo evidence for the insurance flow.", "reason": f"Vertical demo is not ready yet: {missing or 'missing evidence'}."})
        if counts["skills"] and hardened_skills == 0:
            recommended_actions.insert(0, {"area": "capabilities", "action": "Harden skills with activation guidance, instructions, expected artifacts, and policy.", "reason": "Skills exist but are not packaged as reusable enterprise capabilities."})
        if failing_runs:
            recommended_actions.insert(0, {"area": "evals", "action": "Inspect failed benchmark runs and compare traces before promoting more skills.", "reason": f"{failing_runs} failing eval run(s) detected."})
        risk_alerts = [
            alert
            for alert in [
                {"area": "approvals", "severity": "high", "message": f"{pending_approvals} pending approval(s) block write/send boundaries."} if pending_approvals else None,
                {"area": "evals", "severity": "high", "message": f"{failing_runs} failing eval run(s) need trace review before skill promotion."} if failing_runs else None,
                {"area": "work", "severity": "medium", "message": f"{scheduled_due} scheduled work item(s) are due."} if scheduled_due else None,
                {"area": "work", "severity": "medium", "message": f"{budget_exhausted} work item(s) exhausted budget."} if budget_exhausted else None,
                {"area": "knowledge", "severity": "medium", "message": "Knowledge resources exist but are not fully governed, indexed and citable."} if resource_map["total"] and not resource_map["ready"] else None,
                {"area": "capabilities", "severity": "medium", "message": "Skills exist but none are hardened as reusable packages."} if counts["skills"] and hardened_skills == 0 else None,
                {"area": "evals", "severity": "medium", "message": "Benchmark tasks exist but lack enterprise task contracts."} if counts["benchmarkTasks"] and task_contracts_ready == 0 else None,
            ]
            if alert
        ]
        automata_guidance = {
            "role": "studio_copilot",
            "primaryNextAction": recommended_actions[0] if recommended_actions else {"area": "runtime", "action": "Run a representative AgentRuntime session and inspect approvals, artifacts, trace and skill usage.", "reason": "Core Studio surfaces are configured."},
            "riskAlerts": risk_alerts,
            "surfacePlaybook": [
                {
                    "surface": "Company Setup",
                    "status": _surface_status(bool(company_id) and counts["connectors"] > 0),
                    "nextAction": "Confirm systems, credentials, domains, approvals, ACLs and compliance boundaries.",
                },
                {
                    "surface": "Capability Factory",
                    "status": _surface_status(counts["tools"] > 0 and counts["benchmarkTasks"] > 0 and counts["skills"] > 0),
                    "nextAction": "Move from connector access to typed tools, benchmark tasks, judged trajectories and hardened skills.",
                },
                {
                    "surface": "Runtime Lab",
                    "status": _surface_status(counts["sessions"] > 0),
                    "nextAction": "Run or inspect sessions for skill match, tool calls, approvals, artifacts, cost and replay.",
                },
                {
                    "surface": "Work Orchestration",
                    "status": _surface_status(counts["workItems"] > 0 and review_blocked == 0 and budget_exhausted == 0),
                    "nextAction": "Review queues, schedules, retries, budgets, SLAs and approval-blocked jobs.",
                },
                {
                    "surface": "Automata",
                    "status": "ready",
                    "nextAction": "Ask Automata to explain failing tasks, suggest missing benchmarks, or draft the next capability-hardening step.",
                },
            ],
            "explainFailurePrompts": [
                "Why did the latest eval fail and which trace/tool call should I inspect?",
                "Which skills are blocked from publishing and what hardening evidence is missing?",
                "Which permissions or approvals create the biggest runtime risk right now?",
            ],
        }
        operating_state = {
            "readiness": {
                "score": round(ready_count / len(readiness_checks), 2),
                "readyCount": ready_count,
                "total": len(readiness_checks),
                "checks": readiness_checks,
                "gaps": [item for item in readiness_checks if not item["ready"]],
            },
            "factory": {
                "connectors": counts["connectors"],
                "connectedConnectors": connected_connectors,
                "resources": counts["knowledgeDocuments"],
                "entities": counts["entities"],
                "tools": counts["tools"],
                "benchmarkTasks": counts["benchmarkTasks"],
                "trajectories": counts["trajectories"],
                "approvedTrajectories": approved_trajectories,
                "skills": counts["skills"],
                "approvedSkills": approved_skills,
            },
            "capabilityMap": {
                "taskContracts": {
                    "total": counts["benchmarkTasks"],
                    "ready": task_contracts_ready,
                    "expectedArtifacts": task_expected_artifacts,
                    "allowedSystems": task_allowed_systems,
                },
                "tools": {
                    "total": counts["tools"],
                    "typed": typed_tools,
                },
                "skills": {
                    "total": counts["skills"],
                    "approved": approved_skills,
                    "hardened": hardened_skills,
                    "expectedArtifacts": skill_expected_artifacts,
                },
                "verticalDemos": vertical_demos,
            },
            "resourceMap": resource_map,
            "runtime": {
                "agents": counts["agents"],
                "sessions": counts["sessions"],
                "artifacts": counts["artifacts"],
                "passingEvalRuns": passing_runs,
                "failingEvalRuns": failing_runs,
                "pendingApprovals": pending_approvals,
            },
            "work": {
                "items": counts["workItems"],
                "scheduled": scheduled_work,
                "running": running_work,
                "blockedByApprovals": pending_approvals,
            },
            "workOrchestration": {
                "queues": {
                    "total": counts["workItems"],
                    "running": running_work,
                    "reviewBlocked": review_blocked,
                },
                "triggers": {
                    "scheduled": scheduled_work,
                    "due": scheduled_due,
                },
                "budgets": {
                    "budgetedItems": len(budgeted_docs),
                    "exhaustedItems": budget_exhausted,
                    "latestCreditsSpent": round(sum(_work_credits_spent(doc) for doc in work_docs), 4),
                },
                "retries": {
                    "totalRetryCount": total_retries,
                },
                "approvalBoundary": {
                    "pendingApprovals": pending_approvals,
                    "linkedApprovalWorkItems": len(pending_approval_work_item_ids),
                },
                "sla": {
                    "needsAttention": review_blocked + scheduled_due + budget_exhausted,
                },
            },
            "recommendedNextActions": recommended_actions[:6],
            "automataGuidance": automata_guidance,
        }
        return {"companies": companies, "activeCompanyId": company_id, "counts": counts, "operatingState": operating_state, "automataGuidance": automata_guidance}

    async def list_agents(self, limit: int = 10) -> list[dict[str, Any]]:
        return await _to_list(agents_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def list_connectors(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(connectors_collection.find(self._query(), {"_id": 0}).sort("createdAt", 1), limit)

    async def list_capabilities(self, limit: int = 20) -> dict[str, Any]:
        return {
            "tools": await _to_list(tools_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit),
            "skills": await _to_list(
                capabilities_collection.find({**self._query(), "capabilityKind": "skill"}, {"_id": 0}).sort("createdAt", -1),
                limit,
            ),
        }

    async def list_work_items(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(work_items_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    def _request_scope(self):
        from app.request_scope import RequestScope

        return RequestScope(email=self.context.email, token_email=self.context.email)

    async def create_work_item(
        self,
        *,
        title: str,
        prompt: str,
        success_criteria: str = "",
        agent_id: str = "",
        agent_name: str = "",
        run_target: str = "all",
        browser_enabled: bool = True,
        browser_mode: str = "headless",
        max_credits_per_run: float = 5.0,
        max_budget_credits: float | None = None,
        max_steps: int = 8,
        trigger_type: str = "manual",
        schedule_frequency: str = "none",
        schedule_time: str = "09:00",
        schedule_day_of_week: int = 1,
        trigger_config: dict[str, Any] | None = None,
        judge_implementation: str = "llm",
    ) -> dict[str, Any]:
        from app.request_scope import RequestScope
        from app.routes.work_items import WorkItemCreateRequest, create_work_item

        body = WorkItemCreateRequest(
            email=self.context.email,
            companyId=self.context.company_id,
            title=title,
            prompt=prompt,
            successCriteria=success_criteria,
            agentId=agent_id,
            agentName=agent_name,
            runTarget=run_target if run_target in {"selected", "all"} else "all",
            browserEnabled=browser_enabled,
            browserMode=browser_mode if browser_mode in {"visible", "headless"} else "headless",
            maxCreditsPerRun=max_credits_per_run,
            maxBudgetCredits=max_budget_credits,
            maxSteps=max_steps,
            triggerType=trigger_type if trigger_type in {"manual", "scheduled"} else "manual",
            scheduleFrequency=schedule_frequency if schedule_frequency in {"none", "daily", "weekly"} else "none",
            scheduleTime=schedule_time,
            scheduleDayOfWeek=schedule_day_of_week,
            triggerConfig=trigger_config or {},
            judgeImplementation=judge_implementation,
        )
        return await create_work_item(body, scope=RequestScope(email=self.context.email, token_email=self.context.email))

    async def update_work_item(self, work_item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        from app.routes.work_items import WorkItemUpdateRequest, update_work_item

        return await update_work_item(work_item_id, WorkItemUpdateRequest(**updates), scope=self._request_scope())

    async def run_work_item(
        self,
        work_item_id: str,
        *,
        browser_enabled: bool | None = None,
        browser_mode: str | None = None,
        max_credits_per_run: float | None = None,
    ) -> dict[str, Any]:
        from app.routes.work_items import WorkItemRunRequest, run_work_item

        return await run_work_item(
            work_item_id,
            WorkItemRunRequest(browserEnabled=browser_enabled, browserMode=browser_mode, maxCreditsPerRun=max_credits_per_run),
            scope=self._request_scope(),
        )

    async def rejudge_work_item(self, work_item_id: str) -> dict[str, Any]:
        from app.routes.work_items import rejudge_work_item

        return await rejudge_work_item(work_item_id, scope=self._request_scope())

    async def delete_work_item(self, work_item_id: str) -> dict[str, Any]:
        from app.routes.work_items import delete_work_item

        return await delete_work_item(work_item_id, scope=self._request_scope())

    async def list_work_boards(self) -> list[dict[str, Any]]:
        from app.routes.work_items import list_work_boards

        result = await list_work_boards(self.context.email, self.context.company_id, scope=self._request_scope())
        return result.get("boards", []) if isinstance(result, dict) else []

    async def create_work_board(self, name: str) -> dict[str, Any]:
        from app.routes.work_items import WorkBoardCreateRequest, create_work_board

        return await create_work_board(
            WorkBoardCreateRequest(email=self.context.email, companyId=self.context.company_id, name=name),
            scope=self._request_scope(),
        )

    async def list_companies(self, limit: int = 10) -> list[dict[str, Any]]:
        return await _to_list(companies_collection.find({"email": self.context.email}, {"_id": 0}).sort("createdAt", 1), limit)

    async def create_connector(
        self,
        *,
        name: str,
        connector_type: str = "api",
        category: str = "software",
        description: str = "",
        status: str = "not_connected",
        config: dict[str, Any] | None = None,
        provider: str = "",
        auth_required: bool | None = None,
    ) -> dict[str, Any]:
        from app.routes.connectors import ConnectorCreateRequest, create_connector

        body = ConnectorCreateRequest(
            email=self.context.email,
            companyId=self.context.company_id,
            name=name,
            type=connector_type,
            category=category,
            description=description,
            status=status,
            config=config or {},
            provider=provider,
            authRequired=auth_required,
        )
        return await create_connector(body, scope=self._request_scope())

    async def update_connector(self, connector_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        from app.routes.connectors import ConnectorUpdateRequest, update_connector

        return await update_connector(connector_id, ConnectorUpdateRequest(**updates), scope=self._request_scope())

    async def test_connector(self, connector_id: str) -> dict[str, Any]:
        from app.routes.connectors import test_connector

        return await test_connector(connector_id, scope=self._request_scope())

    async def delete_connector(self, connector_id: str) -> dict[str, Any]:
        from app.routes.connectors import delete_connector

        return await delete_connector(connector_id, scope=self._request_scope())

    async def list_credentials(self, limit: int = 50) -> list[dict[str, Any]]:
        from app.routes.credentials import list_credentials

        result = await list_credentials(self.context.email, self.context.company_id, scope=self._request_scope())
        credentials = result.get("credentials", []) if isinstance(result, dict) else []
        return credentials[: max(1, min(limit, 100))]

    async def create_credential(
        self,
        *,
        name: str,
        value: str,
        credential_type: str = "token",
        created_for: str = "connector",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from app.routes.credentials import CredentialCreateRequest, create_credential

        return await create_credential(
            CredentialCreateRequest(
                email=self.context.email,
                companyId=self.context.company_id,
                name=name,
                value=value,
                type=credential_type,
                createdFor=created_for,
                metadata=metadata or {},
            ),
            scope=self._request_scope(),
        )

    async def update_credential(self, credential_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        from app.routes.credentials import CredentialUpdateRequest, update_credential

        return await update_credential(credential_id, CredentialUpdateRequest(**updates), scope=self._request_scope())

    async def delete_credential(self, credential_id: str) -> dict[str, Any]:
        from app.routes.credentials import delete_credential

        return await delete_credential(credential_id, scope=self._request_scope())

    async def list_api_keys(self) -> dict[str, Any]:
        from app.routes.api_keys import get_api_keys

        import os

        return await get_api_keys(self.context.email, x_admin_key=os.getenv("AUTOMATA_API_KEY_ADMIN_TOKEN", ""))

    async def create_api_key(self, name: str) -> dict[str, Any]:
        from app.routes.api_keys import APIKeyCreateRequest, create_api_key

        import os

        result = await create_api_key(APIKeyCreateRequest(email=self.context.email, name=name), x_admin_key=os.getenv("AUTOMATA_API_KEY_ADMIN_TOKEN", ""))
        api_key = result.get("apiKey") if isinstance(result, dict) and isinstance(result.get("apiKey"), dict) else {}
        if "key" in api_key:
            api_key = {**api_key, "key": "***redacted***", "keyReturnedToAssistant": False}
            result = {**result, "apiKey": api_key, "warning": "The raw API key was redacted from assistant output. Create API keys in Settings when you need to copy the secret value."}
        return result

    async def rename_api_key(self, key_id: str, name: str) -> dict[str, Any]:
        from app.routes.api_keys import APIKeyUpdateRequest, update_api_key

        import os

        owned = await self.list_api_keys()
        ids = {str(item.get("id") or "") for item in owned.get("apiKeys", [])}
        if key_id not in ids:
            return {"success": False, "error": "API key not found"}
        return await update_api_key(key_id, APIKeyUpdateRequest(name=name), x_admin_key=os.getenv("AUTOMATA_API_KEY_ADMIN_TOKEN", ""))

    async def delete_api_key(self, key_id: str) -> dict[str, Any]:
        from app.routes.api_keys import delete_api_key

        import os

        owned = await self.list_api_keys()
        ids = {str(item.get("id") or "") for item in owned.get("apiKeys", [])}
        if key_id not in ids:
            return {"success": False, "error": "API key not found"}
        return await delete_api_key(key_id, x_admin_key=os.getenv("AUTOMATA_API_KEY_ADMIN_TOKEN", ""))

    async def list_browser_profiles(self, limit: int = 50) -> list[dict[str, Any]]:
        from app.routes.profile import get_profiles

        result = await get_profiles(self.context.email)
        profiles = result.get("profiles", []) if isinstance(result, dict) else []
        return profiles[: max(1, min(limit, 100))]

    async def create_browser_profile(self, name: str, provider: str = "") -> dict[str, Any]:
        from app.routes.profile import ProfileCreateRequest, create_profile

        return await create_profile(ProfileCreateRequest(email=self.context.email, name=name, provider=provider))

    async def rename_browser_profile(self, profile_id: str, name: str) -> dict[str, Any]:
        from app.routes.profile import ProfileUpdateRequest, update_profile

        if not await profiles_collection.find_one({"_id": ObjectId(profile_id), "email": self.context.email}, {"_id": 1}):
            return {"success": False, "error": "Profile not found"}
        return await update_profile(profile_id, ProfileUpdateRequest(name=name))

    async def delete_browser_profile(self, profile_id: str) -> dict[str, Any]:
        from app.routes.profile import delete_profile

        if not await profiles_collection.find_one({"_id": ObjectId(profile_id), "email": self.context.email}, {"_id": 1}):
            return {"success": False, "error": "Profile not found"}
        return await delete_profile(profile_id)

    async def get_account_info(self) -> dict[str, Any]:
        user = await users_collection.find_one({"email": self.context.email}, {"_id": 0, "email": 1, "instructions": 1})
        if not user:
            return {"error": "User not found"}
        return {"user": user}

    async def update_account_instructions(self, instructions: str) -> dict[str, Any]:
        from app.routes.user import UserUpdateRequest, update_user

        return await update_user(UserUpdateRequest(email=self.context.email, instructions=instructions))

    async def analytics_summary(self, range_key: str = "30d") -> dict[str, Any]:
        from app.routes.analytics import get_analytics

        clean_range = range_key if range_key in {"24h", "7d", "30d", "90d"} else "30d"
        return await get_analytics(self.context.email, range=clean_range)

    async def usage_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return await _to_list(
            usage_events_collection.find({"email": self.context.email}, {"_id": 0}).sort("createdAt", -1),
            max(1, min(limit, 100)),
        )

    async def billing_plan_status(self) -> dict[str, Any]:
        return {
            "billingBackend": "not_configured",
            "currentPlan": "frontend_local_storage_only",
            "canChangePlanFromAssistant": False,
            "plans": [
                {"id": "free", "name": "Free", "price": "$0/month", "features": ["Access to core agents and connectors", "Limited daily sessions", "Community support"]},
                {"id": "pro", "name": "Pro", "price": "$20/month", "features": ["Everything in Free", "Much higher usage limits", "Priority session scheduling", "Email support"]},
                {"id": "max", "name": "Max", "price": "$100/month", "features": ["Everything in Pro", "Highest usage limits", "Dedicated runtime throughput", "Priority support"]},
            ],
            "note": "Plan selection currently lives in frontend localStorage; payment and wallet backends are not wired yet.",
        }

    async def create_agent(
        self,
        *,
        name: str,
        website_url: str = "",
        success_criteria: str = "",
        tasks: list[dict[str, Any]] | None = None,
        browser_enabled: bool = True,
        browser_mode: str = "visible",
        max_credits_per_run: float = 5.0,
    ) -> dict[str, Any]:
        from app.routes.agent_configs import AgentConfigCreateRequest, AgentTask, create_agent

        body = AgentConfigCreateRequest(
            email=self.context.email,
            companyId=self.context.company_id,
            name=name,
            websiteUrl=website_url,
            successCriteria=success_criteria,
            tasks=[AgentTask(**task) for task in (tasks or [])],
            browserEnabled=browser_enabled,
            browserMode=browser_mode,
            maxCreditsPerRun=max_credits_per_run,
        )
        return await create_agent(body, scope=self._request_scope())

    async def update_agent_runtime_settings(
        self,
        agent_id: str,
        *,
        browser_enabled: bool = True,
        browser_mode: str = "visible",
        max_credits_per_run: float = 5.0,
    ) -> dict[str, Any]:
        from app.routes.agent_configs import AgentRuntimeSettingsRequest, update_agent_runtime_settings

        return await update_agent_runtime_settings(
            agent_id,
            AgentRuntimeSettingsRequest(
                browserEnabled=browser_enabled,
                browserMode=browser_mode,
                maxCreditsPerRun=max_credits_per_run,
            ),
            scope=self._request_scope(),
        )

    async def run_agent_task(
        self,
        *,
        prompt: str,
        target: str = "selected",
        agent_id: str = "",
        browser_enabled: bool | None = None,
        browser_mode: str = "visible",
        max_credits_per_run: float = 5.0,
    ) -> dict[str, Any]:
        from app.routes.agent_configs import AgentRunTaskRequest, run_agent_task

        return await run_agent_task(
            AgentRunTaskRequest(
                email=self.context.email,
                companyId=self.context.company_id,
                prompt=prompt,
                target=target,
                agentId=agent_id,
                browserEnabled=browser_enabled,
                browserMode=browser_mode,
                maxCreditsPerRun=max_credits_per_run,
            ),
            scope=self._request_scope(),
        )

    async def list_entities(self, limit: int = 50) -> list[dict[str, Any]]:
        return await _to_list(entities_collection.find(self._query(), {"_id": 0}).sort("name", 1), limit)

    async def generate_entities_from_openapi(
        self,
        *,
        source_url: str,
        apply: bool = False,
        replace_existing: bool = False,
        limit: int = 25,
    ) -> dict[str, Any]:
        proposals = (await propose_entities_from_openapi_url(source_url))[: max(1, min(limit, 100))]
        existing = await _to_list(entities_collection.find(self._query(), {"_id": 0, "name": 1}).sort("name", 1), 500)
        existing_names = {str(doc.get("name") or "") for doc in existing}
        entities = []
        skipped = []
        if not apply:
            return {"applied": False, "sourceUrl": source_url, "entities": proposals, "skipped": []}

        from datetime import datetime, timezone
        from uuid import uuid4

        now = datetime.now(timezone.utc).isoformat()
        for proposal in proposals:
            name = str(proposal.get("name") or "").strip()[:80]
            if not name:
                continue
            doc = {
                "entityId": str(uuid4()),
                "email": self.context.email,
                "companyId": self.context.company_id,
                "name": name,
                "description": str(proposal.get("description") or "").strip(),
                "fields": proposal.get("fields") if isinstance(proposal.get("fields"), list) else [],
                "relationships": proposal.get("relationships") if isinstance(proposal.get("relationships"), list) else [],
                "sourceConnectorId": "",
                "source": "openapi",
                "metadata": proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {},
                "createdAt": now,
                "updatedAt": now,
            }
            if name in existing_names and not replace_existing:
                skipped.append({"name": name, "reason": "already_exists"})
                continue
            if name in existing_names and replace_existing:
                await entities_collection.update_one(
                    self._query({"name": name}),
                    {"$set": {key: value for key, value in doc.items() if key not in {"entityId", "createdAt"}}},
                )
                refreshed = await entities_collection.find_one(self._query({"name": name}), {"_id": 0}) or doc
                entities.append(_clean_doc(refreshed))
                continue
            await entities_collection.insert_one(doc)
            existing_names.add(name)
            entities.append(_clean_doc(doc))
        return {"applied": True, "sourceUrl": source_url, "entities": entities, "skipped": skipped}

    async def list_approvals(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(approvals_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def approve_approval(self, approval_id: str, reason: str = "") -> dict[str, Any]:
        from app.routes.approvals import ApprovalDecisionRequest, approve_approval

        return await approve_approval(approval_id, ApprovalDecisionRequest(email=self.context.email, reason=reason), scope=self._request_scope())

    async def reject_approval(self, approval_id: str, reason: str = "") -> dict[str, Any]:
        from app.routes.approvals import ApprovalDecisionRequest, reject_approval

        return await reject_approval(approval_id, ApprovalDecisionRequest(email=self.context.email, reason=reason), scope=self._request_scope())

    async def list_knowledge_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(knowledge_documents_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def create_vector_database(self, name: str, provider: str = "local", collection_name: str = "") -> dict[str, Any]:
        from app.routes.knowledge import VectorDatabaseCreateRequest, create_vector_database

        return await create_vector_database(
            VectorDatabaseCreateRequest(
                email=self.context.email,
                companyId=self.context.company_id,
                name=name,
                provider=provider,
                collectionName=collection_name,
            )
        )

    async def save_knowledge_document_from_url(
        self,
        *,
        url: str,
        filename: str = "",
        vector_database_id: str = "",
        source: str = "assistant_url",
    ) -> dict[str, Any]:
        from app.routes.knowledge import KnowledgeFromUrlRequest, create_knowledge_document_from_url

        return await create_knowledge_document_from_url(
            KnowledgeFromUrlRequest(
                email=self.context.email,
                companyId=self.context.company_id,
                vectorDatabaseId=vector_database_id,
                url=url,
                filename=filename,
                source=source,
            )
        )

    async def delete_knowledge_document(self, document_id: str) -> dict[str, Any]:
        doc = await knowledge_documents_collection.find_one(self._query({"documentId": document_id}), {"_id": 0})
        if not doc:
            return {"success": False, "error": "Document not found"}
        from app.routes.knowledge import delete_knowledge_document

        return await delete_knowledge_document(document_id)

    async def list_artifacts(self, limit: int = 20) -> list[dict[str, Any]]:
        return await _to_list(artifacts_collection.find(self._query(), {"_id": 0}).sort("createdAt", -1), limit)

    async def update_tool_approval(self, tool_id: str, approval: str) -> dict[str, Any]:
        from app.routes.capabilities import CapabilityApprovalUpdateRequest, update_tool_approval

        return await update_tool_approval(tool_id, CapabilityApprovalUpdateRequest(email=self.context.email, approval=approval))

    async def update_skill_approval(self, skill_id: str, approval: str) -> dict[str, Any]:
        from app.routes.capabilities import CapabilityApprovalUpdateRequest, update_skill_approval

        return await update_skill_approval(skill_id, CapabilityApprovalUpdateRequest(email=self.context.email, approval=approval))

    async def test_tool(self, tool_id: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.routes.capabilities import ToolTestRequest, test_company_tool

        return await test_company_tool(tool_id, ToolTestRequest(email=self.context.email, arguments=arguments or {}))

    async def publish_connector_tools(self, connector_id: str) -> dict[str, Any]:
        connector = await connectors_collection.find_one(self._query({"connectorId": connector_id}), {"_id": 0})
        if not connector:
            return {"success": False, "error": "Connector not found"}
        from app.routes.capabilities import publish_connector_tools

        return await publish_connector_tools(connector_id)

    async def promote_trajectory_to_skill(
        self,
        trajectory_id: str,
        *,
        name: str = "",
        when_to_use: str = "",
        permissions: dict[str, Any] | None = None,
        risk_policy: str = "human_approval_for_writes",
    ) -> dict[str, Any]:
        trajectory = await trajectories_collection.find_one(self._query({"trajectoryId": trajectory_id}), {"_id": 0})
        if not trajectory:
            return {"success": False, "error": "Trajectory not found"}
        from app.routes.capabilities import PromoteTrajectoryRequest, promote_trajectory_to_skill

        return await promote_trajectory_to_skill(
            trajectory_id,
            PromoteTrajectoryRequest(
                email=self.context.email,
                name=name,
                whenToUse=when_to_use,
                permissions=permissions or {},
                riskPolicy=risk_policy,
            ),
        )

    async def list_assistant_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        query = {"email": self.context.email, "companyId": self.context.company_id or ""}
        return await _to_list(assistant_conversations_collection.find(query, {"_id": 0}).sort("updatedAt", -1), limit)

    async def get_assistant_memory(self) -> dict[str, Any]:
        doc = await assistant_memories_collection.find_one(
            {"email": self.context.email, "companyId": self.context.company_id or ""},
            {"_id": 0},
        )
        if not doc:
            return {
                "exists": False,
                "email": self.context.email,
                "companyId": self.context.company_id or "",
                "summary": "",
                "message": "No assistant memory has been built yet. Run studio_rebuild_assistant_memory first.",
            }
        return {"exists": True, **_clean_doc(doc)}

    async def rebuild_assistant_memory(self, limit: int = 200) -> dict[str, Any]:
        job = await enqueue_job(
            "assistant_memory_rebuild",
            {"email": self.context.email, "companyId": self.context.company_id or "", "limit": max(1, min(limit, 500))},
            dedupe_key=f"assistant_memory_rebuild:{self.context.email}:{self.context.company_id or 'global'}",
            max_attempts=2,
        )
        return {
            "queued": True,
            "jobId": job.get("jobId", ""),
            "status": job.get("status", "queued"),
            "companyId": self.context.company_id or "",
            "limit": max(1, min(limit, 500)),
        }

    async def delete_assistant_conversations(
        self,
        *,
        conversation_ids: list[str] | None = None,
        delete_all: bool = False,
        exclude_conversation_id: str = "",
    ) -> dict[str, Any]:
        ids = [str(item).strip() for item in (conversation_ids or []) if str(item).strip()]
        excluded = str(exclude_conversation_id or "").strip()
        if not delete_all and not ids:
            return {"deleted": 0, "requested": 0, "excludedConversationId": excluded, "error": "conversationIds or deleteAll is required"}

        query = self._query()
        requested = len(ids)
        if delete_all:
            if excluded:
                query["conversationId"] = {"$ne": excluded}
        else:
            filtered_ids = [item for item in ids if item != excluded]
            requested = len(ids)
            if not filtered_ids:
                return {"deleted": 0, "requested": requested, "excludedConversationId": excluded}
            query["conversationId"] = {"$in": filtered_ids}

        result = await assistant_conversations_collection.delete_many(query)
        return {
            "deleted": int(getattr(result, "deleted_count", 0) or 0),
            "requested": requested,
            "deleteAll": delete_all,
            "excludedConversationId": excluded,
        }
