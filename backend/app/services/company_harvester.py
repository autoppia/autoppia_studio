from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.database import (
    benchmark_tasks_collection,
    benchmarks_collection,
    company_harvest_runs_collection,
    company_intakes_collection,
    connectors_collection,
    entities_collection,
    knowledge_documents_collection,
    tools_collection,
)
from app.models.company_harvester import (
    CompanyHarvestArtifact,
    CompanyHarvesterOutput,
    CompanyHarvestQuestion,
    CompanyHarvestRun,
    CompanyHarvestStep,
    CompanyIntake,
)
from app.services.connector_discovery import connector_capability_discovery
from app.services.custom_connector_executors import custom_connector_executor_name, has_custom_connector_executor
from app.services.resource_governance import build_resource_contract
from app.services.task_contracts import task_metadata_with_contract
from app.services.tool_contracts import apply_tool_contract


HARVEST_STEPS: tuple[tuple[str, str, str], ...] = (
    ("intaking", "Understand uploaded company material", "normal"),
    ("indexing_knowledge", "Index documents and knowledge", "normal"),
    ("discovering_systems", "Discover systems and access surfaces", "normal"),
    ("discovering_connectors", "Create connector candidates", "dev"),
    ("discovering_tools", "Discover or synthesize tools", "dev"),
    ("discovering_entities", "Infer business entities", "dev"),
    ("discovering_tasks", "Infer useful company tasks", "normal"),
    ("building_benchmarks", "Build benchmarks from tasks", "dev"),
    ("solving_tasks", "Solve tasks with tools, APIs or browser", "normal"),
    ("judging_trajectories", "Judge generated trajectories", "dev"),
    ("promoting_skills", "Promote approved trajectories to skills", "normal"),
    ("building_agents", "Build deployable agent configs", "normal"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_company_harvester_output(raw: dict[str, Any] | CompanyHarvesterOutput | None) -> CompanyHarvesterOutput:
    if isinstance(raw, CompanyHarvesterOutput):
        return raw
    return CompanyHarvesterOutput.model_validate(raw or {})


def company_harvester_output_summary(output: CompanyHarvesterOutput) -> dict[str, Any]:
    runtime_kinds = sorted({solution.agentProvider.runtimeKind for solution in output.taskSolutions if solution.agentProvider.runtimeKind})
    return {
        "schemaVersion": output.schemaVersion,
        "companyId": output.companyId,
        "benchmarkId": output.benchmarkId,
        "proposedTaskCount": len(output.proposedTasks),
        "taskSolutionCount": len(output.taskSolutions),
        "agentConfigCount": len(output.agentConfigs),
        "questionCount": len(output.questions),
        "runtimeKinds": runtime_kinds,
        "confidence": output.confidence,
    }


def _new_steps() -> list[dict[str, Any]]:
    return [
        CompanyHarvestStep(key=key, label=label, visibility=visibility).model_dump()
        for key, label, visibility in HARVEST_STEPS
    ]


def _material_artifact(intake_id: str, index: int, material: dict[str, Any]) -> dict[str, Any]:
    kind = str(material.get("kind") or "")
    if kind in {"document_url", "file", "knowledge_note"}:
        artifact_kind = "knowledge_document"
        visibility = "normal"
    elif kind in {"api_docs", "openapi"}:
        artifact_kind = "connector_candidate"
        visibility = "dev"
    elif kind in {"website", "code_repository", "code_file"}:
        artifact_kind = "connector_candidate"
        visibility = "normal" if kind == "website" else "dev"
    elif kind == "task_list":
        artifact_kind = "task_candidate"
        visibility = "normal"
    else:
        artifact_kind = "question_for_user"
        visibility = "normal"
    title = str(material.get("name") or material.get("url") or material.get("documentId") or kind or "Material")
    return CompanyHarvestArtifact(
        artifactId=f"{intake_id}:material:{index}",
        kind=artifact_kind,  # type: ignore[arg-type]
        title=title,
        refId=str(material.get("documentId") or material.get("connectorId") or ""),
        status="discovered",
        visibility=visibility,  # type: ignore[arg-type]
        summary=f"Discovered {kind or 'material'} for company harvesting.",
        payload={"material": material},
        createdAt=now_iso(),
    ).model_dump()


def _material_ref(index: int, material: dict[str, Any]) -> str:
    return str(material.get("documentId") or material.get("connectorId") or material.get("url") or material.get("name") or f"material:{index}")


def _has_auth_material(intake: dict[str, Any]) -> bool:
    for material in intake.get("materials") or []:
        if not isinstance(material, dict):
            continue
        if str(material.get("kind") or "") == "auth_note":
            return True
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        if metadata.get("authConfigured") or metadata.get("credentialRef") or metadata.get("authInstructions"):
            return True
    return False


def _company_harvest_questions(intake: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    materials = [item for item in intake.get("materials") or [] if isinstance(item, dict)]
    user_tasks = [item for item in intake.get("userTasks") or [] if isinstance(item, dict)]

    if not materials and not user_tasks and not str(intake.get("description") or "").strip():
        questions.append(
            CompanyHarvestQuestion(
                questionId=f"{intake.get('intakeId', '')}:q:company_material",
                code="company_material_required",
                prompt="Add company docs, a web app URL, API docs, or task examples so Automata can discover useful automations.",
                reason="CompanyHarvester needs at least one source of business context before creating benchmark tasks.",
                severity="blocking",
                expectedAnswerType="file",
            ).model_dump()
        )

    has_auth = _has_auth_material(intake)
    for index, material in enumerate(materials, start=1):
        kind = str(material.get("kind") or "")
        url = str(material.get("url") or "").strip()
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        title = str(material.get("name") or url or kind or f"material {index}")
        material_ref = _material_ref(index, material)
        if kind in {"website", "api_docs", "openapi", "document_url"} and not url:
            questions.append(
                CompanyHarvestQuestion(
                    questionId=f"{intake.get('intakeId', '')}:q:{index}:missing_url",
                    code=f"{kind}_url_required",
                    prompt=f"Provide the URL for {title}.",
                    reason=f"The {kind} material cannot be inspected without a URL.",
                    severity="blocking",
                    expectedAnswerType="url",
                    materialRef=material_ref,
                    metadata={"materialKind": kind},
                ).model_dump()
            )
        if kind in {"website", "api_docs", "openapi"} and metadata.get("authRequired") and not has_auth:
            questions.append(
                CompanyHarvestQuestion(
                    questionId=f"{intake.get('intakeId', '')}:q:{index}:missing_auth",
                    code=f"{kind}_auth_required",
                    prompt=f"Provide owner-level auth instructions or credentials for {title}.",
                    reason="This system is marked as requiring authentication, and no auth material was provided.",
                    severity="blocking",
                    expectedAnswerType="credentials",
                    materialRef=material_ref,
                    metadata={"materialKind": kind, "url": url},
                ).model_dump()
            )
        for spec_index, (_source_material, spec) in enumerate(_connector_spec_items([material]), start=1):
            if not spec.get("authRequired") or has_auth:
                continue
            connector_name = _connector_spec_name(spec, material)
            questions.append(
                CompanyHarvestQuestion(
                    questionId=f"{intake.get('intakeId', '')}:q:{index}:custom_connector:{spec_index}:missing_auth",
                    code="custom_connector_auth_required",
                    prompt=f"Provide owner-level auth instructions or credentials for {connector_name}.",
                    reason="This custom system is marked as requiring authentication, and no auth material was provided.",
                    severity="blocking",
                    expectedAnswerType="credentials",
                    materialRef=material_ref,
                    metadata={
                        "materialKind": kind,
                        "connectorName": connector_name,
                        "connectorSurface": _connector_spec_surface(spec, material),
                    },
                ).model_dump()
            )
        if kind == "task_list" and not metadata.get("tasks") and not str(material.get("content") or "").strip():
            questions.append(
                CompanyHarvestQuestion(
                    questionId=f"{intake.get('intakeId', '')}:q:{index}:empty_task_list",
                    code="task_list_empty",
                    prompt=f"Add the task examples for {title}.",
                    reason="The task list material is present but does not include tasks.",
                    severity="warning",
                    expectedAnswerType="task_list",
                    materialRef=material_ref,
                    metadata={"materialKind": kind},
                ).model_dump()
            )
    return questions


def _question_artifact(intake_id: str, question: dict[str, Any]) -> dict[str, Any]:
    return CompanyHarvestArtifact(
        artifactId=f"{intake_id}:question:{question.get('questionId')}",
        kind="question_for_user",
        title=str(question.get("prompt") or question.get("code") or "Question for user"),
        refId=str(question.get("questionId") or ""),
        status="open",
        visibility=str(question.get("visibility") or "normal"),  # type: ignore[arg-type]
        summary=str(question.get("reason") or ""),
        payload={"question": question},
        createdAt=now_iso(),
    ).model_dump()


def _answer_artifact(run_id: str, answer: dict[str, Any]) -> dict[str, Any]:
    question_id = str(answer.get("questionId") or answer.get("code") or uuid.uuid4())
    return CompanyHarvestArtifact(
        artifactId=f"{run_id}:answer:{question_id}",
        kind="question_for_user",
        title=f"Answered {str(answer.get('code') or question_id)}",
        refId=question_id,
        status="answered",
        visibility="dev",
        summary="Conversational setup answer received.",
        payload={
            "questionId": answer.get("questionId", ""),
            "code": answer.get("code", ""),
            "answerKind": answer.get("kind", ""),
            "hasValue": bool(answer.get("value") or answer.get("url") or answer.get("material") or answer.get("materials") or answer.get("tasks")),
        },
        createdAt=now_iso(),
    ).model_dump()


def _mark_answered_question_artifacts(artifacts: list[dict[str, Any]], answered_ids: set[str], answered_codes: set[str]) -> list[dict[str, Any]]:
    updated = []
    for artifact in artifacts:
        if artifact.get("kind") != "question_for_user":
            updated.append(artifact)
            continue
        question = (artifact.get("payload") or {}).get("question") if isinstance(artifact.get("payload"), dict) else {}
        question_id = str((question or {}).get("questionId") or artifact.get("refId") or "")
        code = str((question or {}).get("code") or "")
        if question_id in answered_ids or code in answered_codes:
            updated.append({**artifact, "status": "answered"})
        else:
            updated.append(artifact)
    return updated


def _answer_value(answer: dict[str, Any]) -> str:
    return str(answer.get("value") or answer.get("url") or answer.get("text") or "").strip()


def _apply_answer_to_intake(intake: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    updated = dict(intake)
    materials = [dict(item) for item in updated.get("materials") or [] if isinstance(item, dict)]
    user_tasks = [dict(item) for item in updated.get("userTasks") or [] if isinstance(item, dict)]
    code = str(answer.get("code") or "").strip()
    value = _answer_value(answer)
    material_ref = str(answer.get("materialRef") or "").strip()

    if code == "company_material_required":
        raw_materials = answer.get("materials")
        if isinstance(raw_materials, list):
            materials.extend(dict(item) for item in raw_materials if isinstance(item, dict))
        material = answer.get("material")
        if isinstance(material, dict):
            materials.append(dict(material))
        raw_tasks = answer.get("tasks")
        if isinstance(raw_tasks, list):
            user_tasks.extend(dict(item) for item in raw_tasks if isinstance(item, dict))
        if value and not raw_materials and not isinstance(material, dict) and not raw_tasks:
            materials.append(
                {
                    "kind": "knowledge_note",
                    "name": "Company onboarding note",
                    "content": value,
                    "metadata": {"source": "company_harvest_answer"},
                }
            )
    elif code.endswith("_auth_required"):
        credential_ref = str(answer.get("credentialRef") or "").strip()
        materials.append(
            {
                "kind": "auth_note",
                "name": "Owner auth provided",
                "content": "Owner-level auth was provided through conversational onboarding.",
                "metadata": {
                    "source": "company_harvest_answer",
                    "authConfigured": True,
                    "credentialRef": credential_ref,
                    "targetQuestionId": answer.get("questionId", ""),
                    "targetCode": code,
                },
            }
        )
    elif code.endswith("_url_required") and value:
        target_kind = str(code.removesuffix("_url_required"))
        for index, material in enumerate(materials, start=1):
            if str(material.get("url") or "").strip():
                continue
            if material_ref and _material_ref(index, material) != material_ref:
                continue
            if str(material.get("kind") or "") == target_kind:
                material["url"] = value
                metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
                material["metadata"] = {**metadata, "source": metadata.get("source") or "company_harvest_answer"}
                break
        else:
            materials.append(
                {
                    "kind": target_kind,
                    "name": str(answer.get("name") or target_kind),
                    "url": value,
                    "metadata": {"source": "company_harvest_answer"},
                }
            )
    elif code == "task_list_empty":
        raw_tasks = answer.get("tasks")
        if isinstance(raw_tasks, list) and raw_tasks:
            for material in materials:
                if str(material.get("kind") or "") == "task_list" and not ((material.get("metadata") or {}).get("tasks") if isinstance(material.get("metadata"), dict) else None):
                    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
                    material["metadata"] = {**metadata, "tasks": [dict(item) for item in raw_tasks if isinstance(item, dict)]}
                    break
        elif value:
            for material in materials:
                if str(material.get("kind") or "") == "task_list" and not str(material.get("content") or "").strip():
                    material["content"] = value
                    break
    elif isinstance(answer.get("material"), dict):
        materials.append(dict(answer["material"]))
    elif isinstance(answer.get("tasks"), list):
        user_tasks.extend(dict(item) for item in answer["tasks"] if isinstance(item, dict))
    elif value:
        materials.append(
            {
                "kind": "knowledge_note",
                "name": str(answer.get("name") or "Company onboarding answer"),
                "content": value,
                "metadata": {"source": "company_harvest_answer", "targetCode": code},
            }
        )

    updated["materials"] = materials
    updated["userTasks"] = user_tasks
    updated["updatedAt"] = now_iso()
    return updated


def _task_artifact(intake_id: str, index: int, task: dict[str, Any]) -> dict[str, Any]:
    prompt = str(task.get("prompt") or task.get("name") or "").strip()
    return CompanyHarvestArtifact(
        artifactId=f"{intake_id}:task:{index}",
        kind="task_candidate",
        title=str(task.get("name") or prompt[:80] or "Task candidate"),
        status="discovered",
        visibility="normal",
        summary=prompt,
        payload={"task": task},
        createdAt=now_iso(),
    ).model_dump()


def _normal_summary(intake: dict[str, Any], artifacts: list[dict[str, Any]], questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    for artifact in artifacts:
        kind = str(artifact.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    materials = intake.get("materials") if isinstance(intake.get("materials"), list) else []
    questions = questions or []
    blocking_questions = [item for item in questions if item.get("severity") == "blocking"]
    return {
        "companyId": intake.get("companyId", ""),
        "materialsReceived": len(materials),
        "systemsFound": by_kind.get("connector_candidate", 0),
        "knowledgeSourcesFound": by_kind.get("knowledge_document", 0),
        "taskCandidatesFound": by_kind.get("task_candidate", 0),
        "agentsReady": 0,
        "openQuestions": len(questions),
        "blockedItems": [
            {"code": item.get("code", ""), "prompt": item.get("prompt", ""), "materialRef": item.get("materialRef", "")}
            for item in blocking_questions
        ],
        "recommendedNextAction": "Answer required setup questions." if blocking_questions else "Review discovered company material and start task discovery.",
    }


def _dev_summary(intake: dict[str, Any], artifacts: list[dict[str, Any]], questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "intakeId": intake.get("intakeId", ""),
        "artifactKinds": sorted({str(item.get("kind") or "") for item in artifacts if item.get("kind")}),
        "plannedPipeline": [key for key, _, _ in HARVEST_STEPS],
        "questionCodes": [str(item.get("code") or "") for item in questions or []],
    }


def _slug(value: str, fallback: str = "item") -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    clean = "_".join(part for part in clean.split("_") if part)
    return clean[:72] or fallback


def _executor_slug(value: str, fallback: str = "tool") -> str:
    return _slug(value.replace(".", "_"), fallback=fallback)


def _host(value: str) -> str:
    try:
        return (urlparse(value).hostname or "").lower()
    except Exception:
        return ""


def _connector_name(material: dict[str, Any], default: str) -> str:
    return str(material.get("name") or material.get("title") or _host(str(material.get("url") or "")) or default).strip()


def _auth_material_for(intake: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    target_kind = str(material.get("kind") or "")
    target_codes = {f"{target_kind}_auth_required"}
    for item in intake.get("materials") or []:
        if not isinstance(item, dict) or str(item.get("kind") or "") != "auth_note":
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        target_code = str(metadata.get("targetCode") or "")
        if target_code in target_codes:
            return item
    for item in intake.get("materials") or []:
        if not isinstance(item, dict) or str(item.get("kind") or "") != "auth_note":
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if metadata.get("authConfigured") or metadata.get("credentialRef") or metadata.get("authInstructions"):
            return item
    return {}


def _auth_state_for(intake: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    auth_note = _auth_material_for(intake, material)
    metadata = auth_note.get("metadata") if isinstance(auth_note.get("metadata"), dict) else {}
    credential_ref = str(metadata.get("credentialRef") or "").strip()
    auth_configured = bool(metadata.get("authConfigured") or credential_ref or metadata.get("authInstructions"))
    return {
        "configured": auth_configured,
        "credentialRef": credential_ref,
        "credentialRefs": {"default": credential_ref} if credential_ref else {},
        "source": metadata.get("source", ""),
    }


def _connector_spec_items(materials: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for material in materials:
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        for key in ("connector", "connectors", "system", "systems"):
            raw = metadata.get(key)
            if isinstance(raw, dict):
                items.append((material, dict(raw)))
            elif isinstance(raw, list):
                items.extend((material, dict(item)) for item in raw if isinstance(item, dict))
    return items


def _connector_spec_name(spec: dict[str, Any], material: dict[str, Any]) -> str:
    return str(spec.get("name") or spec.get("title") or spec.get("systemName") or material.get("name") or "Custom System").strip()


def _connector_spec_surface(spec: dict[str, Any], material: dict[str, Any]) -> str:
    raw = str(spec.get("surface") or spec.get("type") or spec.get("kind") or "").strip().lower()
    material_kind = str(material.get("kind") or "")
    if raw in {"api", "rest", "graphql", "webhook"}:
        return "api"
    if raw in {"web", "website", "webapp", "browser"}:
        return "webapp"
    if raw in {"email", "mail", "imap", "smtp", "gmail"}:
        return "email"
    if raw in {"knowledge", "docs", "document"}:
        return "knowledge"
    if raw in {"code", "repo", "repository", "source"}:
        return "code"
    if material_kind in {"api_docs", "openapi"}:
        return "api"
    if material_kind == "website":
        return "webapp"
    if material_kind in {"code_repository", "code_file"}:
        return "code"
    return "custom"


def _connector_type_for_surface(surface: str) -> str:
    return {
        "api": "api",
        "webapp": "web",
        "knowledge": "knowledge",
        "email": "email",
        "code": "code",
    }.get(surface, "custom")


def _connector_runtime_requirements(surface: str, spec: dict[str, Any]) -> list[str]:
    explicit = [str(item) for item in spec.get("runtimeRequirements") or [] if str(item or "").strip()]
    if explicit:
        return explicit
    return {
        "api": ["connector_runtime", "network"],
        "webapp": ["browser", "network"],
        "email": ["connector_runtime", "approval_gate"],
        "knowledge": ["vectorstore", "embedding_model"],
        "code": ["repository_read"],
    }.get(surface, ["connector_runtime"])


def _connector_id_from_spec(company_id: str, material: dict[str, Any], spec: dict[str, Any], index: int) -> str:
    name = _connector_spec_name(spec, material)
    url = str(spec.get("url") or spec.get("baseUrl") or spec.get("docsUrl") or material.get("url") or "").strip()
    return str(spec.get("connectorId") or f"{company_id}:custom:{_slug(name or url or str(index))}")


async def _upsert_custom_connector_candidate(*, intake: dict[str, Any], material: dict[str, Any], spec: dict[str, Any], index: int) -> dict[str, Any] | None:
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return None
    now = now_iso()
    name = _connector_spec_name(spec, material)
    surface = _connector_spec_surface(spec, material)
    connector_type = _connector_type_for_surface(surface)
    url = str(spec.get("url") or spec.get("baseUrl") or spec.get("docsUrl") or material.get("url") or "").strip()
    auth_state = _auth_state_for(intake, material)
    auth_required = bool(spec.get("authRequired") or (material.get("metadata") if isinstance(material.get("metadata"), dict) else {}).get("authRequired"))
    connector_status = "connected" if auth_required and auth_state["configured"] else "needs_auth" if auth_required else "not_connected"
    connector_id = _connector_id_from_spec(company_id, material, spec, index)
    config = spec.get("config") if isinstance(spec.get("config"), dict) else {}
    config = {
        **config,
        **({"baseUrl": url} if url and surface in {"api", "webapp"} else {}),
        **({"docsUrl": str(spec.get("docsUrl") or material.get("url") or "")} if surface == "api" else {}),
    }
    doc = {
        "connectorId": connector_id,
        "email": email,
        "companyId": company_id,
        "name": name,
        "type": connector_type,
        "category": str(spec.get("category") or "software"),
        "description": str(spec.get("description") or f"Custom connector candidate discovered from company material for {name}."),
        "status": connector_status,
        "config": config,
        "credentialRefs": auth_state["credentialRefs"],
        "provider": str(spec.get("provider") or "custom"),
        "generationStatus": "connector_spec_provided",
        "surface": surface,
        "authRequired": auth_required,
        "authConfigured": bool(auth_state["configured"]),
        "discoveryStatus": "pending",
        "discoveryMode": "company_harvest",
        "runtimeRequirements": _connector_runtime_requirements(surface, spec),
        "connectorSpec": spec,
        "source": "company_harvester",
        "sourceIntakeId": intake.get("intakeId", ""),
        "sourceMaterialRef": _material_ref(index, material),
        "updatedAt": now,
    }
    existing = await connectors_collection.find_one({"connectorId": doc["connectorId"]}, {"_id": 0})
    doc["createdAt"] = (existing or {}).get("createdAt") or now
    await connectors_collection.update_one({"connectorId": doc["connectorId"]}, {"$set": doc}, upsert=True)
    return doc


async def _upsert_connector_candidate(*, intake: dict[str, Any], material: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(material.get("kind") or "")
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return None
    now = now_iso()
    url = str(material.get("url") or "").strip()
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    auth_state = _auth_state_for(intake, material)
    auth_required = bool(metadata.get("authRequired"))
    connector_status = "connected" if auth_required and auth_state["configured"] else "needs_auth" if auth_required else "not_connected"
    if kind == "website":
        name = _connector_name(material, "Company Web App")
        connector_type = "web"
        connector_id = f"{company_id}:web:{_slug(url or name)}"
        config = {"baseUrl": url, "startUrl": url}
        doc = {
            "connectorId": connector_id,
            "email": email,
            "companyId": company_id,
            "name": name,
            "type": connector_type,
            "category": "software",
            "description": f"Company web surface discovered from intake material {name}.",
            "status": connector_status,
            "config": config,
            "credentialRefs": auth_state["credentialRefs"],
            "provider": "custom",
            "generationStatus": "start_url_provided" if url else "needs_start_url",
            "surface": "webapp",
            "authRequired": auth_required,
            "authConfigured": bool(auth_state["configured"]),
            "discoveryStatus": "pending",
            "discoveryMode": "company_harvest",
            "runtimeRequirements": ["browser", "network"],
            "source": "company_harvester",
            "sourceIntakeId": intake.get("intakeId", ""),
            "updatedAt": now,
        }
    elif kind in {"api_docs", "openapi"}:
        name = _connector_name(material, "Company API")
        connector_id = f"{company_id}:api:{_slug(url or name)}"
        config_key = "openApiUrl" if kind == "openapi" else "docsUrl"
        doc = {
            "connectorId": connector_id,
            "email": email,
            "companyId": company_id,
            "name": name,
            "type": "api",
            "category": "software",
            "description": f"Custom API candidate discovered from intake material {name}.",
            "status": connector_status,
            "config": {config_key: url},
            "credentialRefs": auth_state["credentialRefs"],
            "provider": "custom",
            "generationStatus": "docs_provided" if url else "needs_docs",
            "surface": "api",
            "authRequired": auth_required,
            "authConfigured": bool(auth_state["configured"]),
            "discoveryStatus": "pending",
            "discoveryMode": "company_harvest",
            "runtimeRequirements": ["api_docs_or_openapi", "network"],
            "source": "company_harvester",
            "sourceIntakeId": intake.get("intakeId", ""),
            "updatedAt": now,
        }
    elif kind in {"code_repository", "code_file"}:
        name = _connector_name(material, "Company Code")
        connector_id = f"{company_id}:code:{_slug(url or name)}"
        doc = {
            "connectorId": connector_id,
            "email": email,
            "companyId": company_id,
            "name": name,
            "type": "code",
            "category": "development",
            "description": f"Company source code discovered from intake material {name}.",
            "status": "not_connected",
            "config": {"sourceUrl": url, "materialKind": kind},
            "credentialRefs": auth_state["credentialRefs"],
            "provider": "custom",
            "generationStatus": "source_provided" if url or material.get("content") else "needs_source",
            "surface": "code",
            "authRequired": auth_required,
            "authConfigured": bool(auth_state["configured"]),
            "discoveryStatus": "pending",
            "discoveryMode": "company_harvest",
            "runtimeRequirements": ["repository_read"],
            "source": "company_harvester",
            "sourceIntakeId": intake.get("intakeId", ""),
            "updatedAt": now,
        }
    else:
        return None
    existing = await connectors_collection.find_one({"connectorId": doc["connectorId"]}, {"_id": 0})
    if existing:
        doc["createdAt"] = existing.get("createdAt")
    else:
        doc["createdAt"] = now
    await connectors_collection.update_one({"connectorId": doc["connectorId"]}, {"$set": doc}, upsert=True)
    return doc


async def _ensure_knowledge_connector(intake: dict[str, Any], materials: list[dict[str, Any]]) -> dict[str, Any] | None:
    knowledge_materials = [item for item in materials if str(item.get("kind") or "") in {"document_url", "file", "knowledge_note"}]
    if not knowledge_materials:
        return None
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return None
    now = now_iso()
    connector_id = f"{company_id}:knowledge:company"
    doc = {
        "connectorId": connector_id,
        "email": email,
        "companyId": company_id,
        "name": "Company Knowledge",
        "type": "knowledge",
        "category": "data",
        "description": "Company knowledge source assembled from intake documents, URLs and notes.",
        "status": "not_connected",
        "config": {
            "collectionName": f"company-{company_id}",
            "sourceMaterialCount": len(knowledge_materials),
        },
        "credentialRefs": {},
        "provider": "official",
        "generationStatus": "material_provided",
        "surface": "knowledge",
        "authRequired": False,
        "discoveryStatus": "pending_indexing",
        "discoveryMode": "company_harvest",
        "runtimeRequirements": ["vectorstore", "embedding_model"],
        "source": "company_harvester",
        "sourceIntakeId": intake.get("intakeId", ""),
        "updatedAt": now,
    }
    existing = await connectors_collection.find_one({"connectorId": connector_id}, {"_id": 0})
    if existing:
        doc["createdAt"] = existing.get("createdAt")
    else:
        doc["createdAt"] = now
    await connectors_collection.update_one({"connectorId": connector_id}, {"$set": doc}, upsert=True)
    return doc


def _knowledge_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in materials if str(item.get("kind") or "") in {"document_url", "file", "knowledge_note"}]


async def _upsert_knowledge_documents(intake: dict[str, Any], materials: list[dict[str, Any]], connector: dict[str, Any] | None) -> list[dict[str, Any]]:
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return []
    now = now_iso()
    connector_id = str((connector or {}).get("connectorId") or f"{company_id}:knowledge:company")
    docs: list[dict[str, Any]] = []
    for index, material in enumerate(_knowledge_materials(materials), start=1):
        title = str(material.get("name") or material.get("url") or material.get("documentId") or f"Knowledge {index}").strip()
        url = str(material.get("url") or "").strip()
        content = str(material.get("content") or "").strip()
        document_id = str(material.get("documentId") or f"{company_id}:knowledge:{_slug(url or title or str(index))}")
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        content_type = str(metadata.get("contentType") or ("text/uri-list" if url and not content else "text/plain"))
        size = int(metadata.get("size") or (len(content.encode("utf-8")) if content else 0))
        doc = {
            "documentId": document_id,
            "resourceId": document_id,
            "email": email,
            "companyId": company_id,
            "connectorId": connector_id,
            "filename": title,
            "source": "company_harvester",
            "sourceUrl": url,
            "contentType": content_type,
            "size": size,
            "status": "pending_indexing",
            "metadata": {
                **metadata,
                "materialKind": material.get("kind", ""),
                "sourceIntakeId": intake.get("intakeId", ""),
                "sourceUrl": url,
            },
            "acl": metadata.get("acl") if isinstance(metadata.get("acl"), dict) else {"visibility": "company", "allowedRoles": ["owner"]},
            "createdAt": now,
            "updatedAt": now,
        }
        doc["resourceContract"] = build_resource_contract(doc)
        existing = await knowledge_documents_collection.find_one({"documentId": document_id}, {"_id": 0})
        doc["createdAt"] = (existing or {}).get("createdAt") or now
        await knowledge_documents_collection.update_one({"documentId": document_id}, {"$set": doc}, upsert=True)
        docs.append(doc)
    return docs


def _tool_prefix(connector: dict[str, Any]) -> str:
    raw = str(connector.get("name") or connector.get("connectorId") or connector.get("type") or "company")
    return _slug(raw, fallback="company").replace("_", ".")


def _tool_prefix_from_material(material: dict[str, Any], default: str) -> str:
    raw = str(material.get("name") or material.get("title") or _host(str(material.get("url") or "")) or default)
    return _slug(raw, fallback=default).replace("_", ".")


def _material_for_connector(connector: dict[str, Any], materials: list[dict[str, Any]]) -> dict[str, Any]:
    source_id = str(connector.get("sourceIntakeId") or "")
    source_ref = str(connector.get("sourceMaterialRef") or "")
    connector_type = str(connector.get("type") or "")
    for index, material in enumerate(materials, start=1):
        if source_ref and _material_ref(index, material) == source_ref:
            return material
        kind = str(material.get("kind") or "")
        if connector_type == "api" and kind in {"api_docs", "openapi"}:
            return material
        if connector_type == "web" and kind == "website":
            return material
        if connector_type == "knowledge" and kind in {"document_url", "file", "knowledge_note"}:
            return material
        if connector_type == "code" and kind in {"code_repository", "code_file"}:
            return material
    return {"metadata": {"sourceIntakeId": source_id}}


def _openapi_spec_from_material(material: dict[str, Any]) -> dict[str, Any]:
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    for key in ("openapi", "openapiSpec", "spec"):
        value = metadata.get(key)
        if isinstance(value, dict):
            return value
    content = str(material.get("content") or "").strip()
    if content.startswith("{"):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _openapi_operation_name(prefix: str, method: str, path: str, operation: dict[str, Any]) -> str:
    operation_id = str(operation.get("operationId") or "").strip()
    if operation_id:
        return f"{prefix}.{_slug(operation_id).replace('_', '.')}"
    path_slug = _slug(path.strip("/") or "root").replace("_", ".")
    return f"{prefix}.{method.lower()}.{path_slug}"


def _openapi_request_schema(operation: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in operation.get("parameters") or []:
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name") or "").strip()
        if not name:
            continue
        schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {"type": "string"}
        properties[name] = schema
        if parameter.get("required"):
            required.append(name)
    request_body = operation.get("requestBody") if isinstance(operation.get("requestBody"), dict) else {}
    content = request_body.get("content") if isinstance(request_body.get("content"), dict) else {}
    json_body = content.get("application/json") if isinstance(content.get("application/json"), dict) else {}
    body_schema = json_body.get("schema") if isinstance(json_body.get("schema"), dict) else {}
    if body_schema:
        properties["body"] = body_schema
        if request_body.get("required"):
            required.append("body")
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _openapi_response_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") if isinstance(operation.get("responses"), dict) else {}
    for status in ("200", "201", "202", "default"):
        response = responses.get(status) if isinstance(responses.get(status), dict) else {}
        content = response.get("content") if isinstance(response.get("content"), dict) else {}
        json_response = content.get("application/json") if isinstance(content.get("application/json"), dict) else {}
        schema = json_response.get("schema") if isinstance(json_response.get("schema"), dict) else {}
        if schema:
            return schema if schema.get("type") == "object" else {"type": "object", "properties": {"result": schema}}
    return {"type": "object", "additionalProperties": True}


def _entity_name_from_schema_ref(schema: dict[str, Any], fallback: str) -> str:
    ref = str(schema.get("$ref") or "").strip()
    if ref:
        return _slug(ref.rstrip("/").rsplit("/", 1)[-1], fallback=fallback).replace("_", " ").title().replace(" ", "")
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return _entity_name_from_schema_ref(schema["items"], fallback)
    title = str(schema.get("title") or "").strip()
    return title or fallback


def _openapi_tools_from_spec(connector: dict[str, Any], material: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _openapi_spec_from_material(material)
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
    if not paths:
        return []
    prefix = _tool_prefix(connector)
    tools: list[dict[str, Any]] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_lower = str(method or "").lower()
            if method_lower not in {"get", "post", "put", "patch", "delete"} or not isinstance(operation, dict):
                continue
            output_schema = _openapi_response_schema(operation)
            read = method_lower == "get"
            tools.append(
                {
                    "name": _openapi_operation_name(prefix, method_lower, str(path), operation),
                    "description": str(operation.get("summary") or operation.get("description") or f"{method_lower.upper()} {path}"),
                    "sideEffects": "reads" if read else "writes",
                    "inputSchema": _openapi_request_schema(operation),
                    "outputSchema": output_schema,
                    "inputEntities": ["ApiOperation"],
                    "outputEntity": _entity_name_from_schema_ref(output_schema, "ApiResult"),
                    "metadata": {
                        "openapiPath": str(path),
                        "openapiMethod": method_lower,
                        "operationId": str(operation.get("operationId") or ""),
                        "sourceUrl": str(material.get("url") or ""),
                    },
                }
            )
    return tools


def _raw_tool_candidates_for_connector(connector: dict[str, Any], material: dict[str, Any]) -> list[dict[str, Any]]:
    connector_type = str(connector.get("type") or "")
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    connector_spec = connector.get("connectorSpec") if isinstance(connector.get("connectorSpec"), dict) else {}
    spec_tools = connector_spec.get("tools")
    if isinstance(spec_tools, list) and spec_tools:
        return [
            {
                **dict(item),
                "metadata": {
                    **(dict(item).get("metadata") if isinstance(dict(item).get("metadata"), dict) else {}),
                    "customConnector": True,
                    "connectorSpecProvided": True,
                },
            }
            for item in spec_tools
            if isinstance(item, dict)
        ]
    explicit_tools = metadata.get("tools")
    if isinstance(explicit_tools, list) and explicit_tools:
        return [dict(item) for item in explicit_tools if isinstance(item, dict)]

    prefix = _tool_prefix(connector)
    if connector_type == "knowledge":
        return [
            {
                "name": "knowledge.company_docs.search",
                "description": "Search indexed company knowledge sources gathered during onboarding.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
                    "required": ["query"],
                },
                "outputSchema": {"type": "object", "properties": {"results": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputEntities": ["KnowledgeQuery"],
                "outputEntity": "KnowledgeSource",
            }
        ]
    if connector_type == "api":
        openapi_tools = _openapi_tools_from_spec(connector, material)
        if openapi_tools:
            return openapi_tools
        return [
            {
                "name": f"{prefix}.discover_operations",
                "description": "Inspect API documentation and propose typed atomic tools for this company connector.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"operationHint": {"type": "string"}},
                },
                "outputSchema": {"type": "object", "properties": {"tools": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputEntities": ["ApiDocumentation"],
                "outputEntity": "ToolCandidate",
            }
        ]
    if connector_type == "web":
        return [
            {
                "name": f"{prefix}.explore_workflows",
                "description": "Explore the company web app and identify business workflows that can become tasks or skills.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"instruction": {"type": "string"}, "startUrl": {"type": "string"}},
                    "required": ["instruction"],
                },
                "outputSchema": {"type": "object", "properties": {"workflows": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputEntities": ["WebApp"],
                "outputEntity": "WorkflowCandidate",
            }
        ]
    if connector_type == "code":
        return [
            {
                "name": f"{prefix}.code.inspect",
                "description": "Inspect company source code to discover routes, workflows, domain entities and automation surfaces.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "pathHint": {"type": "string"}},
                    "required": ["query"],
                },
                "outputSchema": {"type": "object", "properties": {"findings": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputEntities": ["SourceCode"],
                "outputEntity": "CodeFinding",
            }
        ]
    if connector_type == "email":
        return [
            {
                "name": f"{prefix}.discover_email_workflows",
                "description": "Inspect email connector requirements and propose safe read, draft, and approval-gated send workflows.",
                "inputSchema": {"type": "object", "properties": {"workflowHint": {"type": "string"}}},
                "outputSchema": {"type": "object", "properties": {"workflows": {"type": "array"}, "tools": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "medium",
                "inputEntities": ["EmailMailbox"],
                "outputEntity": "WorkflowCandidate",
                "metadata": {"customConnector": True},
            }
        ]
    if connector_type == "custom":
        return [
            {
                "name": f"{prefix}.discover_tools",
                "description": "Inspect this custom company system and propose typed atomic tools, auth requirements, task candidates, and approval boundaries.",
                "inputSchema": {"type": "object", "properties": {"systemHint": {"type": "string"}}},
                "outputSchema": {"type": "object", "properties": {"tools": {"type": "array"}, "tasks": {"type": "array"}, "authRequirements": {"type": "array"}}},
                "sideEffects": "reads",
                "riskLevel": "low",
                "inputEntities": ["CustomSystem"],
                "outputEntity": "ToolCandidate",
                "metadata": {"customConnector": True},
            }
        ]
    return []


def _custom_connector_executor_blueprint(connector: dict[str, Any], raw_tool: dict[str, Any], tool_name: str) -> dict[str, Any]:
    connector_name = str(connector.get("name") or connector.get("connectorId") or "custom")
    executor_name = str(raw_tool.get("runtimeExecutor") or raw_tool.get("executor") or "").strip()
    if not executor_name:
        executor_name = f"custom.{_executor_slug(connector_name, fallback='connector')}.{_executor_slug(tool_name.split('.')[-1], fallback='tool')}"
    registered = has_custom_connector_executor({"runtimeExecutor": executor_name})
    return {
        "schemaVersion": "custom_connector_executor_blueprint/v1",
        "executorName": executor_name,
        "registrationStatus": "registered" if registered else "missing",
        "connectorId": str(connector.get("connectorId") or ""),
        "connectorName": connector_name,
        "toolName": tool_name,
        "inputSchema": raw_tool.get("inputSchema") if isinstance(raw_tool.get("inputSchema"), dict) else {"type": "object", "properties": {}},
        "outputSchema": raw_tool.get("outputSchema") if isinstance(raw_tool.get("outputSchema"), dict) else {"type": "object", "additionalProperties": True},
        "sideEffects": str(raw_tool.get("sideEffects") or "reads"),
        "authRequired": bool(connector.get("authRequired")),
        "credentialRefsConfigured": bool(connector.get("credentialRefs")),
        "nextAction": "Register this executor in custom_connector_executors or implement an external connector runtime for this tool.",
    }


async def _upsert_tool_candidates(*, intake: dict[str, Any], connectors: list[dict[str, Any]], materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return []
    now = now_iso()
    tool_docs: list[dict[str, Any]] = []
    for connector in connectors:
        material = _material_for_connector(connector, materials)
        surface = str(connector.get("surface") or connector.get("type") or "")
        execution_type = {
            "api": "api_call",
            "web": "browser_automation",
            "knowledge": "knowledge_search",
            "email": "connector_tool",
            "custom": "connector_tool",
        }.get(str(connector.get("type") or ""), "connector_tool")
        requirements = connector.get("runtimeRequirements") if isinstance(connector.get("runtimeRequirements"), list) else []
        for raw_tool in _raw_tool_candidates_for_connector(connector, material):
            tool_name = str(raw_tool.get("name") or "").strip()
            if not tool_name:
                continue
            tool_id = f"{company_id}:tool:{_slug(tool_name)}"
            governed = apply_tool_contract(
                {
                    **raw_tool,
                    "toolId": tool_id,
                    "name": tool_name,
                    "connectorId": connector.get("connectorId", ""),
                    "source": "company_harvester",
                    "status": "candidate",
                },
                connector=connector,
                execution_type=execution_type,
                surface=surface,
                runtime_requirements=requirements,
            )
            doc = {
                **governed,
                "toolId": tool_id,
                "email": email,
                "companyId": company_id,
                "connectorId": str(connector.get("connectorId") or ""),
                "connectorType": str(connector.get("type") or ""),
                "executionType": execution_type,
                "status": "candidate",
                "generationStatus": "candidate",
                "discoveryMode": "company_harvest",
                "source": "company_harvester",
                "sourceIntakeId": intake.get("intakeId", ""),
                "updatedAt": now,
            }
            if str(connector.get("type") or "") == "custom":
                blueprint = _custom_connector_executor_blueprint(connector, raw_tool, tool_name)
                doc["executorBlueprint"] = blueprint
                doc["metadata"] = {
                    **(doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}),
                    "customConnector": True,
                    "executorBlueprintStatus": blueprint["registrationStatus"],
                    "suggestedRuntimeExecutor": blueprint["executorName"],
                }
            existing = await tools_collection.find_one({"toolId": tool_id}, {"_id": 0})
            doc["createdAt"] = (existing or {}).get("createdAt") or now
            await tools_collection.update_one({"toolId": tool_id}, {"$set": doc}, upsert=True)
            tool_docs.append(doc)
    return tool_docs


def _entity_slug(value: str) -> str:
    return _slug(value, fallback="entity")


def _entity_field(name: str, field_type: str = "string", *, role: str = "", description: str = "", required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "type": field_type,
        "description": description,
        "role": role,
        "required": required,
        "ref": "",
        "target": "",
        "sourcePath": "",
        "examples": [],
    }


def _entity_candidate_from_name(
    *,
    name: str,
    connector_id: str = "",
    source: str = "tool_contract",
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    fields = [
        _entity_field("id", role="identifier", description=f"Stable identifier for {clean_name}."),
        _entity_field("name", role="display", description=f"Human readable label for {clean_name}."),
    ]
    return {
        "name": clean_name,
        "description": description or f"Inferred business entity from CompanyHarvester {source.replace('_', ' ')}.",
        "fields": fields,
        "relationships": [],
        "sourceConnectorId": connector_id,
        "source": "company_harvester",
        "metadata": {"inferenceSource": source, **(metadata or {})},
    }


def _explicit_entity_candidates(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for material in materials:
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        entities = metadata.get("entities")
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name") or entity.get("entity") or "").strip()
            if not name:
                continue
            candidates.append(
                {
                    **entity,
                    "name": name,
                    "source": entity.get("source") or "company_harvester",
                    "metadata": {
                        **(entity.get("metadata") if isinstance(entity.get("metadata"), dict) else {}),
                        "inferenceSource": "material_metadata",
                        "sourceMaterialKind": material.get("kind", ""),
                        "sourceUrl": material.get("url", ""),
                    },
                }
            )
    return candidates


def _tool_entity_candidates(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for tool in tools:
        connector_id = str(tool.get("connectorId") or "")
        names = [str(item) for item in tool.get("inputEntities") or [] if str(item or "").strip()]
        output_entity = str(tool.get("outputEntity") or "").strip()
        if output_entity:
            names.append(output_entity)
        for name in names:
            candidates.append(
                _entity_candidate_from_name(
                    name=name,
                    connector_id=connector_id,
                    source="tool_contract",
                    metadata={
                        "toolId": tool.get("toolId", ""),
                        "toolName": tool.get("name", ""),
                        "connectorId": connector_id,
                    },
                )
            )
    return candidates


def _material_entity_candidates(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for material in materials:
        kind = str(material.get("kind") or "")
        name = str(material.get("name") or material.get("url") or "").strip()
        if kind in {"api_docs", "openapi"}:
            candidates.append(
                _entity_candidate_from_name(
                    name="ApiOperation",
                    source="api_material",
                    description="API operation or endpoint discovered from company API documentation.",
                    metadata={"sourceMaterialKind": kind, "sourceUrl": material.get("url", ""), "materialName": name},
                )
            )
        elif kind == "website":
            candidates.append(
                _entity_candidate_from_name(
                    name="WorkflowCandidate",
                    source="web_material",
                    description="Business workflow candidate discovered from the company web app.",
                    metadata={"sourceMaterialKind": kind, "sourceUrl": material.get("url", ""), "materialName": name},
                )
            )
        elif kind in {"document_url", "file", "knowledge_note"}:
            candidates.append(
                _entity_candidate_from_name(
                    name="KnowledgeSource",
                    source="knowledge_material",
                    description="Company knowledge source available for grounded answers.",
                    metadata={"sourceMaterialKind": kind, "sourceUrl": material.get("url", ""), "materialName": name},
                )
            )
        elif kind in {"code_repository", "code_file"}:
            candidates.append(
                _entity_candidate_from_name(
                    name="CodeFinding",
                    source="code_material",
                    description="Source code surface available for route, workflow and entity discovery.",
                    metadata={"sourceMaterialKind": kind, "sourceUrl": material.get("url", ""), "materialName": name},
                )
            )
    return candidates


async def _upsert_entity_candidates(*, intake: dict[str, Any], tools: list[dict[str, Any]], materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    if not email or not company_id:
        return []
    now = now_iso()
    raw_candidates = [*_explicit_entity_candidates(materials)]
    if any((material.get("metadata") if isinstance(material.get("metadata"), dict) else {}).get("inferEntities") for material in materials):
        raw_candidates.extend([*_tool_entity_candidates(tools), *_material_entity_candidates(materials)])
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        name = str(candidate.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        entity_id = str(candidate.get("entityId") or f"{company_id}:entity:{_entity_slug(name)}")
        fields = candidate.get("fields") if isinstance(candidate.get("fields"), list) else []
        relationships = candidate.get("relationships") if isinstance(candidate.get("relationships"), list) else []
        metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        doc = {
            "entityId": entity_id,
            "email": email,
            "companyId": company_id,
            "name": name,
            "description": str(candidate.get("description") or f"Inferred {name} entity during company harvesting."),
            "fields": fields or [_entity_field("id", role="identifier"), _entity_field("name", role="display")],
            "relationships": relationships,
            "sourceConnectorId": str(candidate.get("sourceConnectorId") or metadata.get("connectorId") or ""),
            "source": str(candidate.get("source") or "company_harvester"),
            "metadata": {
                **metadata,
                "companyHarvest": True,
                "sourceIntakeId": intake.get("intakeId", ""),
            },
            "updatedAt": now,
        }
        existing = await entities_collection.find_one({"entityId": entity_id}, {"_id": 0})
        doc["createdAt"] = (existing or {}).get("createdAt") or now
        await entities_collection.update_one({"entityId": entity_id}, {"$set": doc}, upsert=True)
        docs.append(doc)
    return docs


def _task_expected_tools(task: dict[str, Any]) -> list[str]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return [str(item) for item in metadata.get("expectedTools") or [] if str(item or "").strip()]


def _task_matches_connector(task: dict[str, Any], connector: dict[str, Any], connector_tool_names: set[str]) -> bool:
    if connector_tool_names & set(_task_expected_tools(task)):
        return True
    config = connector.get("config") if isinstance(connector.get("config"), dict) else {}
    connector_urls = {str(config.get(key) or "").strip() for key in ("openApiUrl", "docsUrl", "startUrl", "baseUrl", "sourceUrl")}
    connector_urls = {url for url in connector_urls if url}
    allowed_systems = {str(item) for item in task.get("allowedSystems") or [] if str(item or "").strip()}
    return bool(connector_urls & allowed_systems)


def _connector_typed_tool_count(connector: dict[str, Any]) -> int:
    discovery = connector.get("capabilityDiscovery") if isinstance(connector.get("capabilityDiscovery"), dict) else {}
    synthesis = discovery.get("toolSynthesis") if isinstance(discovery.get("toolSynthesis"), dict) else {}
    try:
        return int(synthesis.get("typedToolCount") or 0)
    except (TypeError, ValueError):
        return 0


async def _refresh_connector_discovery(
    *,
    connectors: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tools_by_connector: dict[str, list[dict[str, Any]]] = {}
    entities_by_connector: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        connector_id = str(tool.get("connectorId") or "")
        if connector_id:
            tools_by_connector.setdefault(connector_id, []).append(tool)
    for entity in entities:
        connector_id = str(entity.get("sourceConnectorId") or "")
        if connector_id:
            entities_by_connector.setdefault(connector_id, []).append(entity)

    refreshed: list[dict[str, Any]] = []
    for connector in connectors:
        connector_id = str(connector.get("connectorId") or "")
        connector_tools = tools_by_connector.get(connector_id, [])
        connector_entities = entities_by_connector.get(connector_id, [])
        connector_tool_names = {str(tool.get("name") or "") for tool in connector_tools if str(tool.get("name") or "")}
        connector_tasks = [task for task in tasks if _task_matches_connector(task, connector, connector_tool_names)]
        toolkit = {
            "tools": connector_tools,
            "runtimeRequirements": connector.get("runtimeRequirements") if isinstance(connector.get("runtimeRequirements"), list) else [],
        }
        discovery_input = {
            **connector,
            "discoveryStatus": "ready" if connector_tools else connector.get("discoveryStatus", "pending"),
            "entityCandidates": [{"name": entity.get("name", "")} for entity in connector_entities],
        }
        discovery = connector_capability_discovery(discovery_input, toolkit)
        discovery = {
            **discovery,
            "source": "company_harvester",
            "toolIds": [tool.get("toolId") for tool in connector_tools],
            "entityIds": [entity.get("entityId") for entity in connector_entities],
            "candidateTasks": {
                **(discovery.get("candidateTasks") if isinstance(discovery.get("candidateTasks"), dict) else {}),
                "count": len(connector_tasks),
                "taskIds": [task.get("taskId") for task in connector_tasks],
            },
        }
        update = {
            "capabilityDiscovery": discovery,
            "discoveredEntities": [{"entityId": entity.get("entityId"), "name": entity.get("name")} for entity in connector_entities],
            "toolIds": [tool.get("toolId") for tool in connector_tools],
            "taskIds": [task.get("taskId") for task in connector_tasks],
            "discoveryStatus": discovery.get("status") or connector.get("discoveryStatus", "pending"),
            "updatedAt": now_iso(),
        }
        await connectors_collection.update_one({"connectorId": connector_id}, {"$set": update})
        refreshed.append({**connector, **update})
    return refreshed


def _tool_has_runtime_executor(tool: dict[str, Any]) -> bool:
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    connector_type = str(tool.get("connectorType") or metadata.get("connectorType") or "").lower()
    is_custom = connector_type == "custom" or bool(metadata.get("customConnector"))
    status = str(tool.get("implementationStatus") or metadata.get("implementationStatus") or "").lower()
    if is_custom:
        return has_custom_connector_executor(tool)
    return status in {"ready", "implemented", "active"} or bool(tool.get("executor") or tool.get("runtimeExecutor") or metadata.get("executor"))


def _connector_implementation_gaps(connectors: list[dict[str, Any]], tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools_by_connector: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        connector_id = str(tool.get("connectorId") or "")
        if connector_id:
            tools_by_connector.setdefault(connector_id, []).append(tool)
    gaps: list[dict[str, Any]] = []
    for connector in connectors:
        if str(connector.get("type") or "") != "custom":
            continue
        connector_id = str(connector.get("connectorId") or "")
        connector_tools = tools_by_connector.get(connector_id, [])
        if any(_tool_has_runtime_executor(tool) for tool in connector_tools):
            continue
        gaps.append(
            {
                "connectorId": connector_id,
                "name": str(connector.get("name") or connector_id),
                "toolIds": [str(tool.get("toolId") or "") for tool in connector_tools if tool.get("toolId")],
                "toolNames": [str(tool.get("name") or "") for tool in connector_tools if tool.get("name")],
                "nextAction": "Implement or attach a connector executor, then rerun the benchmark tasks for this system.",
            }
        )
    return gaps


def _custom_connector_executor_blueprints_from_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blueprints: list[dict[str, Any]] = []
    for tool in tools:
        blueprint = tool.get("executorBlueprint") if isinstance(tool.get("executorBlueprint"), dict) else {}
        if not blueprint:
            continue
        executor_name = str(blueprint.get("executorName") or custom_connector_executor_name(tool) or "").strip()
        registration_status = "registered" if executor_name and has_custom_connector_executor({"runtimeExecutor": executor_name}) else str(blueprint.get("registrationStatus") or "missing")
        if registration_status not in {"registered", "missing"}:
            registration_status = "missing"
        blueprints.append(
            {
                "toolId": str(tool.get("toolId") or ""),
                "toolName": str(tool.get("name") or blueprint.get("toolName") or ""),
                "connectorId": str(tool.get("connectorId") or blueprint.get("connectorId") or ""),
                "executorName": executor_name,
                "registrationStatus": registration_status,
                "authRequired": bool(blueprint.get("authRequired")),
                "credentialRefsConfigured": bool(blueprint.get("credentialRefsConfigured")),
                "nextAction": str(blueprint.get("nextAction") or "Register or implement this custom connector executor."),
            }
        )
    blueprints.sort(key=lambda item: (item["registrationStatus"] != "missing", item["executorName"]))
    return blueprints


def _task_from_material(material: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(material.get("kind") or "")
    name = str(material.get("name") or material.get("url") or kind or "Company material").strip()
    url = str(material.get("url") or "").strip()
    if kind == "website":
        expected_tool = f"{_tool_prefix_from_material(material, 'web')}.explore_workflows"
        return {
            "name": f"Explore {name}",
            "prompt": f"Explore the {name} web app and identify a useful business workflow that can be automated.",
            "successCriteria": "A trajectory identifies the web workflow, required inputs, and whether browser automation is needed.",
            "allowedSystems": [url] if url else [],
            "expectedArtifacts": ["workflow_summary", "trajectory_trace"],
            "riskClass": "read",
            "metadata": {"sourceMaterialKind": kind, "sourceUrl": url, "requiresBrowser": True, "expectedTools": [expected_tool]},
        }
    if kind in {"api_docs", "openapi"}:
        expected_tool = f"{_tool_prefix_from_material(material, 'api')}.discover_operations"
        return {
            "name": f"Inspect {name}",
            "prompt": f"Inspect the {name} API documentation and identify useful API-backed operations for this company.",
            "successCriteria": "The result lists candidate tools/endpoints, required auth, and safe read/write boundaries.",
            "allowedSystems": [url] if url else [],
            "expectedArtifacts": ["tool_candidates"],
            "riskClass": "read",
            "metadata": {"sourceMaterialKind": kind, "sourceUrl": url, "prefersApi": True, "expectedTools": [expected_tool]},
        }
    if kind in {"document_url", "file", "knowledge_note"}:
        return {
            "name": f"Answer from {name}",
            "prompt": f"Use the company knowledge in {name} to answer an operational question with cited sources.",
            "successCriteria": "The answer is grounded in company knowledge and cites the source material.",
            "allowedSystems": [url] if url else ["company_knowledge"],
            "expectedArtifacts": ["grounded_answer"],
            "riskClass": "read",
            "metadata": {"sourceMaterialKind": kind, "sourceUrl": url, "usesKnowledge": True, "expectedTools": ["knowledge.company_docs.search"]},
        }
    if kind in {"code_repository", "code_file"}:
        expected_tool = f"{_tool_prefix_from_material(material, 'code')}.code.inspect"
        return {
            "name": f"Inspect {name}",
            "prompt": f"Inspect the source code in {name} and identify useful business workflows, API routes, UI actions and connector gaps.",
            "successCriteria": "The result cites source code evidence and proposes concrete tasks/tools/skills that can be built from it.",
            "allowedSystems": [url] if url else ["company_code"],
            "expectedArtifacts": ["code_findings", "task_candidates", "tool_candidates"],
            "riskClass": "read",
            "metadata": {"sourceMaterialKind": kind, "sourceUrl": url, "usesCode": True, "expectedTools": [expected_tool]},
        }
    return None


def _tasks_from_website_ui_hints(material: dict[str, Any]) -> list[dict[str, Any]]:
    if str(material.get("kind") or "") != "website":
        return []
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    raw_hints = metadata.get("uiTaskHints") or metadata.get("workflowHints") or metadata.get("workflows")
    if not isinstance(raw_hints, list):
        return []
    name = str(material.get("name") or material.get("url") or "Web app").strip()
    url = str(material.get("url") or "").strip()
    default_tool = f"{_tool_prefix_from_material(material, 'web')}.explore_workflows"
    tasks: list[dict[str, Any]] = []
    for index, raw_hint in enumerate(raw_hints, start=1):
        if isinstance(raw_hint, str):
            raw_task: dict[str, Any] = {"prompt": raw_hint}
        elif isinstance(raw_hint, dict):
            raw_task = dict(raw_hint)
        else:
            continue
        prompt = str(raw_task.get("prompt") or raw_task.get("description") or raw_task.get("name") or "").strip()
        if not prompt:
            continue
        raw_metadata = raw_task.get("metadata") if isinstance(raw_task.get("metadata"), dict) else {}
        expected_tools = [str(item) for item in raw_metadata.get("expectedTools") or raw_task.get("expectedTools") or [] if str(item or "").strip()]
        if not expected_tools:
            expected_tools = [default_tool]
        allowed_systems = raw_task.get("allowedSystems") if isinstance(raw_task.get("allowedSystems"), list) else ([url] if url else [])
        tasks.append(
            {
                **raw_task,
                "name": str(raw_task.get("name") or f"{name} UI workflow {index}"),
                "prompt": prompt,
                "successCriteria": str(raw_task.get("successCriteria") or "The UI workflow is completed or converted into a reusable browser trajectory."),
                "allowedSystems": [str(item) for item in allowed_systems if str(item or "").strip()],
                "expectedArtifacts": raw_task.get("expectedArtifacts") if isinstance(raw_task.get("expectedArtifacts"), list) else ["workflow_summary", "trajectory_trace"],
                "riskClass": str(raw_task.get("riskClass") or "read"),
                "metadata": {
                    **raw_metadata,
                    "sourceMaterialKind": "website",
                    "sourceUrl": url,
                    "uiTaskHint": True,
                    "requiresBrowser": True,
                    "expectedTools": expected_tools,
                },
                "source": raw_task.get("source") or "company_harvester_ui_hint",
            }
        )
    return tasks


def _tasks_from_explicit_tools(material: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    raw_tools = metadata.get("tools")
    if not isinstance(raw_tools, list):
        return []
    kind = str(material.get("kind") or "")
    url = str(material.get("url") or "").strip()
    tasks: list[dict[str, Any]] = []
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict):
            continue
        tool_name = str(raw_tool.get("name") or raw_tool.get("toolName") or "").strip()
        if not tool_name:
            continue
        side_effects = str(raw_tool.get("sideEffects") or "reads").strip().lower()
        risk_class = "send" if side_effects in {"send", "sends"} or "send" in tool_name.lower() else "write" if side_effects not in {"", "none", "read", "reads"} else "read"
        task_metadata: dict[str, Any] = {
            "sourceMaterialKind": kind,
            "sourceUrl": url,
            "expectedTools": [tool_name],
            "connectorToolCandidate": True,
        }
        if kind in {"api_docs", "openapi"}:
            task_metadata["prefersApi"] = True
        elif kind == "website":
            task_metadata["requiresBrowser"] = True
        elif kind in {"document_url", "file", "knowledge_note"} or "knowledge" in tool_name.lower():
            task_metadata["usesKnowledge"] = True
        elif kind in {"code_repository", "code_file"} or ".code." in tool_name.lower():
            task_metadata["usesCode"] = True
        tasks.append(
            {
                "name": f"Validate {tool_name}",
                "prompt": f"Use the {tool_name} tool candidate to complete a representative company workflow and capture its result.",
                "successCriteria": "The tool candidate is invoked with valid inputs, returns a useful business result, and records any required approval boundary.",
                "allowedSystems": [url] if url else [],
                "expectedArtifacts": ["tool_result", "trajectory_trace"],
                "riskClass": risk_class,
                "metadata": task_metadata,
            }
        )
    return tasks


def _tasks_from_openapi_tool_docs(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for tool in tools:
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
        path = str(metadata.get("openapiPath") or "").strip()
        method = str(metadata.get("openapiMethod") or "").strip().upper()
        if not path or not method:
            continue
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            continue
        side_effects = str(tool.get("sideEffects") or "reads").lower()
        risk_class = "read" if side_effects in {"read", "reads"} else "write"
        source_url = str(metadata.get("sourceUrl") or "").strip()
        tasks.append(
            {
                "name": f"Validate {tool_name}",
                "prompt": f"Use the {tool_name} API tool for {method} {path} and capture the business result.",
                "successCriteria": "The API-backed tool is invoked with valid inputs, returns a useful business result, and records any required approval boundary.",
                "allowedSystems": [source_url] if source_url else [],
                "expectedArtifacts": ["tool_result", "trajectory_trace"],
                "riskClass": risk_class,
                "metadata": {
                    "sourceMaterialKind": "openapi",
                    "sourceUrl": source_url,
                    "expectedTools": [tool_name],
                    "connectorToolCandidate": True,
                    "prefersApi": True,
                    "openapiPath": path,
                    "openapiMethod": method.lower(),
                },
                "source": "company_harvester_openapi_operation",
            }
        )
    return tasks


def _tasks_from_custom_connector_tool_docs(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for tool in tools:
        if str(tool.get("connectorType") or "") not in {"custom", "email"}:
            continue
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            continue
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
        side_effects = str(tool.get("sideEffects") or "reads").lower()
        risk_class = "read" if side_effects in {"read", "reads"} else "send" if "send" in side_effects else "write"
        tasks.append(
            {
                "name": f"Validate {tool_name}",
                "prompt": f"Use the {tool_name} connector tool candidate to complete a representative company workflow and capture its result.",
                "successCriteria": "The custom connector tool is invoked or specified with valid inputs, returns a useful business result, and records any missing implementation or approval boundary.",
                "allowedSystems": [str(tool.get("connectorId") or "")],
                "expectedArtifacts": ["tool_result", "connector_gap_report", "trajectory_trace"],
                "riskClass": risk_class,
                "metadata": {
                    "sourceMaterialKind": metadata.get("sourceMaterialKind", "custom_connector"),
                    "expectedTools": [tool_name],
                    "connectorToolCandidate": True,
                    "customConnector": True,
                    "connectorId": tool.get("connectorId", ""),
                },
                "source": "company_harvester_custom_connector_tool",
            }
        )
    return tasks


def _tasks_from_connector_specs(intake: dict[str, Any], materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    company_id = str(intake.get("companyId") or "")
    tasks: list[dict[str, Any]] = []
    for index, (material, spec) in enumerate(_connector_spec_items(materials), start=1):
        raw_tasks = spec.get("tasks") or spec.get("taskCandidates") or spec.get("workflows")
        if not isinstance(raw_tasks, list):
            continue
        connector_id = _connector_id_from_spec(company_id, material, spec, index) if company_id else ""
        connector_name = _connector_spec_name(spec, material)
        surface = _connector_spec_surface(spec, material)
        spec_tool_names = [
            str(tool.get("name") or tool.get("toolName") or "").strip()
            for tool in spec.get("tools") or []
            if isinstance(tool, dict) and str(tool.get("name") or tool.get("toolName") or "").strip()
        ]
        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            prompt = str(raw_task.get("prompt") or raw_task.get("description") or raw_task.get("name") or "").strip()
            if not prompt:
                continue
            raw_metadata = raw_task.get("metadata") if isinstance(raw_task.get("metadata"), dict) else {}
            expected_tools = [str(item) for item in raw_metadata.get("expectedTools") or raw_task.get("expectedTools") or [] if str(item or "").strip()]
            tool_name = str(raw_task.get("toolName") or raw_task.get("tool") or "").strip()
            if tool_name and tool_name not in expected_tools:
                expected_tools.append(tool_name)
            if not expected_tools and len(spec_tool_names) == 1:
                expected_tools = list(spec_tool_names)
            tasks.append(
                {
                    **raw_task,
                    "name": str(raw_task.get("name") or f"Validate {connector_name} workflow"),
                    "prompt": prompt,
                    "successCriteria": str(raw_task.get("successCriteria") or "The workflow is completed or its connector implementation gap is captured with evidence."),
                    "allowedSystems": [connector_id] if connector_id else [],
                    "expectedArtifacts": raw_task.get("expectedArtifacts") if isinstance(raw_task.get("expectedArtifacts"), list) else ["tool_result", "connector_gap_report", "trajectory_trace"],
                    "riskClass": str(raw_task.get("riskClass") or "read"),
                    "metadata": {
                        **raw_metadata,
                        "sourceMaterialKind": material.get("kind", ""),
                        "connectorSpecTask": True,
                        "customConnector": surface == "custom",
                        "connectorName": connector_name,
                        "connectorSurface": surface,
                        "connectorId": connector_id,
                        **({"expectedTools": expected_tools} if expected_tools else {}),
                    },
                    "source": raw_task.get("source") or "company_harvester_connector_spec_task",
                }
            )
    return tasks


def _tasks_from_material_task_list(material: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    raw_tasks = metadata.get("tasks")
    if isinstance(raw_tasks, list):
        return [task for task in raw_tasks if isinstance(task, dict)]
    content = str(material.get("content") or "").strip()
    tasks = []
    for index, line in enumerate(content.splitlines(), start=1):
        prompt = line.strip(" -\t")
        if prompt:
            tasks.append({"name": f"User task {index}", "prompt": prompt, "successCriteria": "Task can be completed and verified."})
    return tasks


def _task_candidates(intake: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for task in intake.get("userTasks") or []:
        if isinstance(task, dict) and str(task.get("prompt") or task.get("name") or "").strip():
            candidates.append({**task, "source": task.get("source") or "user_provided"})
    for material in intake.get("materials") or []:
        if not isinstance(material, dict):
            continue
        if str(material.get("kind") or "") == "task_list":
            candidates.extend({**task, "source": "user_task_list"} for task in _tasks_from_material_task_list(material))
            continue
        candidates.extend(_tasks_from_website_ui_hints(material))
        candidates.extend({**task, "source": "company_harvester_tool_candidate"} for task in _tasks_from_explicit_tools(material))
        inferred = _task_from_material(material)
        if inferred:
            candidates.append({**inferred, "source": "company_harvester_inferred"})
    materials = [item for item in intake.get("materials") or [] if isinstance(item, dict)]
    candidates.extend(_tasks_from_connector_specs(intake, materials))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.get("prompt") or candidate.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


async def _ensure_company_benchmark_and_tasks(intake: dict[str, Any], tasks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    email = str(intake.get("email") or "")
    company_id = str(intake.get("companyId") or "")
    benchmark_id = f"{company_id}:company_harvest:{intake.get('intakeId')}"
    now = now_iso()
    benchmark = {
        "benchmarkId": benchmark_id,
        "email": email,
        "companyId": company_id,
        "agentId": "",
        "agentName": "",
        "name": f"{intake.get('companyName') or 'Company'} Harvest Benchmark",
        "description": "Tasks discovered during company harvesting.",
        "websiteUrl": "",
        "source": "company_harvester",
        "status": "draft",
        "taskCount": len(tasks),
        "updatedAt": now,
    }
    existing_benchmark = await benchmarks_collection.find_one({"benchmarkId": benchmark_id}, {"_id": 0})
    benchmark["createdAt"] = (existing_benchmark or {}).get("createdAt") or now
    await benchmarks_collection.update_one({"benchmarkId": benchmark_id}, {"$set": benchmark}, upsert=True)

    task_docs: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        prompt = str(task.get("prompt") or task.get("name") or "").strip()
        if not prompt:
            continue
        task_id = f"{benchmark_id}:task:{index}:{_slug(prompt)}"
        website_url = ""
        allowed_systems = [str(item) for item in task.get("allowedSystems") or [] if item]
        for system in allowed_systems:
            if str(system).startswith(("http://", "https://")):
                website_url = str(system)
                break
        metadata = task_metadata_with_contract(task, website_url=website_url, allowed_systems=allowed_systems)
        doc = {
            "taskId": task_id,
            "email": email,
            "companyId": company_id,
            "agentId": "",
            "benchmarkId": benchmark_id,
            "name": str(task.get("name") or prompt[:80]),
            "taskName": str(task.get("taskName") or task.get("name") or prompt[:80]),
            "prompt": prompt,
            "successCriteria": str(task.get("successCriteria") or metadata.get("successCriteria") or ""),
            "metadata": {
                **metadata,
                "source": task.get("source") or "company_harvester",
                "companyHarvest": True,
                "intakeId": intake.get("intakeId", ""),
            },
            "businessIntent": metadata["businessIntent"],
            "initialState": metadata["initialState"],
            "allowedSystems": metadata["allowedSystems"],
            "expectedArtifacts": metadata["expectedArtifacts"],
            "riskClass": metadata["riskClass"],
            "status": "needs_harvest",
            "trajectoryId": "",
            "source": task.get("source") or "company_harvester",
            "updatedAt": now,
        }
        existing = await benchmark_tasks_collection.find_one({"taskId": task_id}, {"_id": 0})
        doc["createdAt"] = (existing or {}).get("createdAt") or now
        await benchmark_tasks_collection.update_one({"taskId": task_id}, {"$set": doc}, upsert=True)
        task_docs.append(doc)
    return benchmark, task_docs


def _set_step(steps: list[dict[str, Any]], key: str, status: str, message: str) -> list[dict[str, Any]]:
    now = now_iso()
    updated = []
    for step in steps:
        if step.get("key") == key:
            updated.append({**step, "status": status, "message": message, "updatedAt": now})
        else:
            updated.append(step)
    return updated


async def create_company_intake(
    *,
    email: str,
    company_id: str,
    company_name: str = "",
    description: str = "",
    materials: list[dict[str, Any]] | None = None,
    user_tasks: list[dict[str, Any]] | None = None,
    mode: str = "normal",
) -> dict[str, Any]:
    now = now_iso()
    intake = CompanyIntake(
        intakeId=str(uuid.uuid4()),
        email=email,
        companyId=company_id,
        companyName=company_name,
        description=description,
        materials=materials or [],
        userTasks=user_tasks or [],
        mode="dev" if mode == "dev" else "normal",
        status="ready_for_harvest",
        createdAt=now,
        updatedAt=now,
    ).model_dump()
    await company_intakes_collection.insert_one(dict(intake))
    return intake


async def start_company_harvest(intake_id: str, *, mode: str = "", email: str = "") -> dict[str, Any]:
    query: dict[str, Any] = {"intakeId": intake_id}
    if email:
        query["email"] = email
    intake = await company_intakes_collection.find_one(query, {"_id": 0})
    if not intake:
        raise ValueError("Company intake not found")
    run_mode = mode or str(intake.get("mode") or "normal")
    artifacts = [
        _material_artifact(intake_id, index, material)
        for index, material in enumerate(intake.get("materials") or [], start=1)
        if isinstance(material, dict)
    ]
    artifacts.extend(
        _task_artifact(intake_id, index, task)
        for index, task in enumerate(intake.get("userTasks") or [], start=1)
        if isinstance(task, dict)
    )
    questions = _company_harvest_questions(intake)
    artifacts.extend(_question_artifact(intake_id, question) for question in questions)
    blocking_questions = [item for item in questions if item.get("severity") == "blocking"]
    steps = _new_steps()
    if steps:
        steps[0]["status"] = "done"
        steps[0]["message"] = "Company intake captured."
        steps[0]["updatedAt"] = now_iso()
        if blocking_questions:
            steps[1]["status"] = "blocked"
            steps[1]["message"] = "Waiting for required company setup answers."
        else:
            steps[1]["status"] = "in_progress" if artifacts else "pending"
            steps[1]["message"] = "Ready to index company knowledge." if artifacts else "Waiting for company material."
        steps[1]["updatedAt"] = now_iso()
    now = now_iso()
    run = CompanyHarvestRun(
        runId=str(uuid.uuid4()),
        intakeId=intake_id,
        email=str(intake.get("email") or ""),
        companyId=str(intake.get("companyId") or ""),
        status="needs_user_input" if blocking_questions else ("indexing_knowledge" if artifacts else "needs_user_input"),
        mode="dev" if run_mode == "dev" else "normal",
        currentStep="needs_user_input" if blocking_questions else ("indexing_knowledge" if artifacts else "needs_user_input"),
        steps=steps,
        artifacts=artifacts,
        normalSummary=_normal_summary(intake, artifacts, questions),
        devSummary=_dev_summary(intake, artifacts, questions),
        questions=questions,
        nextAction={
            "kind": "answer_questions" if questions else ("review_material" if artifacts else "add_company_material"),
            "label": "Answer required setup questions" if questions else ("Review discovered material" if artifacts else "Add company docs, app URL, API docs or task examples"),
            "questionIds": [item.get("questionId") for item in questions],
        },
        createdAt=now,
        updatedAt=now,
    ).model_dump()
    await company_harvest_runs_collection.insert_one(dict(run))
    await company_intakes_collection.update_one(
        {"intakeId": intake_id},
        {"$set": {"status": "harvesting", "updatedAt": now}},
    )
    return run


async def answer_company_harvest_questions(
    run_id: str,
    *,
    answers: list[dict[str, Any]],
    email: str = "",
) -> dict[str, Any]:
    query: dict[str, Any] = {"runId": run_id}
    if email:
        query["email"] = email
    run = await company_harvest_runs_collection.find_one(query, {"_id": 0})
    if not run:
        raise ValueError("Company harvest run not found")
    intake_query: dict[str, Any] = {"intakeId": run.get("intakeId", "")}
    if email:
        intake_query["email"] = email
    intake = await company_intakes_collection.find_one(intake_query, {"_id": 0})
    if not intake:
        raise ValueError("Company intake not found")

    applied_answers = [dict(answer) for answer in answers if isinstance(answer, dict)]
    updated_intake = dict(intake)
    for answer in applied_answers:
        updated_intake = _apply_answer_to_intake(updated_intake, answer)
    now = now_iso()
    await company_intakes_collection.update_one(
        {"intakeId": intake.get("intakeId", "")},
        {
            "$set": {
                "materials": updated_intake.get("materials") or [],
                "userTasks": updated_intake.get("userTasks") or [],
                "description": updated_intake.get("description", intake.get("description", "")),
                "status": "harvesting",
                "updatedAt": now,
            }
        },
    )

    questions = _company_harvest_questions(updated_intake)
    blocking_questions = [item for item in questions if item.get("severity") == "blocking"]
    answered_ids = {str(item.get("questionId") or "") for item in applied_answers if item.get("questionId")}
    answered_codes = {str(item.get("code") or "") for item in applied_answers if item.get("code")}
    artifacts = _mark_answered_question_artifacts(list(run.get("artifacts") or []), answered_ids, answered_codes)
    existing_artifact_ids = {str(item.get("artifactId") or "") for item in artifacts if isinstance(item, dict)}
    for answer in applied_answers:
        artifact = _answer_artifact(run_id, answer)
        if artifact["artifactId"] not in existing_artifact_ids:
            artifacts.append(artifact)
            existing_artifact_ids.add(artifact["artifactId"])
    for question in questions:
        artifact = _question_artifact(str(updated_intake.get("intakeId") or ""), question)
        if artifact["artifactId"] not in existing_artifact_ids:
            artifacts.append(artifact)
            existing_artifact_ids.add(artifact["artifactId"])

    steps = list(run.get("steps") or _new_steps())
    if blocking_questions:
        steps = _set_step(steps, "indexing_knowledge", "blocked", "Waiting for required company setup answers.")
        status = "needs_user_input"
        current_step = "needs_user_input"
        next_action = {
            "kind": "answer_questions",
            "label": "Answer required setup questions",
            "questionIds": [item.get("questionId") for item in questions],
        }
    else:
        steps = _set_step(steps, "indexing_knowledge", "in_progress", "Required setup answers received. Ready to continue company harvesting.")
        status = "indexing_knowledge"
        current_step = "indexing_knowledge"
        next_action = {
            "kind": "continue_company_harvest",
            "label": "Continue company harvesting",
            "runId": run_id,
        }
    update = {
        "status": status,
        "currentStep": current_step,
        "steps": steps,
        "artifacts": artifacts,
        "questions": questions,
        "normalSummary": _normal_summary(updated_intake, artifacts, questions),
        "devSummary": {
            **_dev_summary(updated_intake, artifacts, questions),
            "answeredQuestionIds": sorted(answered_ids),
            "answeredQuestionCodes": sorted(answered_codes),
        },
        "nextAction": next_action,
        "updatedAt": now,
    }
    await company_harvest_runs_collection.update_one({"runId": run_id}, {"$set": update})
    return {**run, **update}


async def process_company_harvest_run(run_id: str) -> dict[str, Any]:
    run = await company_harvest_runs_collection.find_one({"runId": run_id}, {"_id": 0})
    if not run:
        raise ValueError("Company harvest run not found")
    intake = await company_intakes_collection.find_one({"intakeId": run.get("intakeId", ""), "email": run.get("email", "")}, {"_id": 0})
    if not intake:
        raise ValueError("Company intake not found")

    materials = [item for item in intake.get("materials") or [] if isinstance(item, dict)]
    questions = _company_harvest_questions(intake)
    blocking_questions = [item for item in questions if item.get("severity") == "blocking"]
    if blocking_questions:
        artifacts = list(run.get("artifacts") or [])
        existing_artifact_ids = {str(item.get("artifactId") or "") for item in artifacts if isinstance(item, dict)}
        for question in questions:
            artifact = _question_artifact(str(intake.get("intakeId") or ""), question)
            if artifact["artifactId"] not in existing_artifact_ids:
                artifacts.append(artifact)
        steps = list(run.get("steps") or _new_steps())
        steps = _set_step(steps, "indexing_knowledge", "blocked", "Waiting for required company setup answers.")
        normal_summary = _normal_summary(intake, artifacts, questions)
        dev_summary = _dev_summary(intake, artifacts, questions)
        update = {
            "status": "needs_user_input",
            "currentStep": "needs_user_input",
            "steps": steps,
            "artifacts": artifacts,
            "questions": questions,
            "normalSummary": normal_summary,
            "devSummary": dev_summary,
            "nextAction": {
                "kind": "answer_questions",
                "label": "Answer required setup questions",
                "questionIds": [item.get("questionId") for item in questions],
            },
            "updatedAt": now_iso(),
        }
        await company_harvest_runs_collection.update_one({"runId": run_id}, {"$set": update})
        return {**run, **update}

    connector_docs: list[dict[str, Any]] = []
    knowledge = await _ensure_knowledge_connector(intake, materials)
    if knowledge:
        connector_docs.append(knowledge)
    knowledge_docs = await _upsert_knowledge_documents(intake, materials, knowledge)
    for material in materials:
        connector = await _upsert_connector_candidate(intake=intake, material=material)
        if connector:
            connector_docs.append(connector)
    for index, (material, spec) in enumerate(_connector_spec_items(materials), start=1):
        connector = await _upsert_custom_connector_candidate(intake=intake, material=material, spec=spec, index=index)
        if connector and str(connector.get("connectorId") or "") not in {str(doc.get("connectorId") or "") for doc in connector_docs}:
            connector_docs.append(connector)
    tool_docs = await _upsert_tool_candidates(intake=intake, connectors=connector_docs, materials=materials)
    entity_docs = await _upsert_entity_candidates(intake=intake, tools=tool_docs, materials=materials)

    task_candidates = [*_task_candidates(intake), *_tasks_from_openapi_tool_docs(tool_docs), *_tasks_from_custom_connector_tool_docs(tool_docs)]
    benchmark, task_docs = await _ensure_company_benchmark_and_tasks(intake, task_candidates)
    connector_docs = await _refresh_connector_discovery(connectors=connector_docs, tools=tool_docs, entities=entity_docs, tasks=task_docs)
    connector_gaps = _connector_implementation_gaps(connector_docs, tool_docs)
    executor_blueprints = _custom_connector_executor_blueprints_from_tools(tool_docs)

    artifacts = list(run.get("artifacts") or [])
    existing_artifact_ids = {str(item.get("artifactId") or "") for item in artifacts if isinstance(item, dict)}
    now = now_iso()
    for doc in knowledge_docs:
        artifact_id = f"{run_id}:knowledge:{doc['documentId']}"
        if artifact_id not in existing_artifact_ids:
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="knowledge_document",
                    title=str(doc.get("filename") or doc.get("documentId") or "Knowledge document"),
                    refId=str(doc.get("documentId") or ""),
                    status="persisted",
                    visibility="normal",
                    summary="Registered company knowledge document for indexing.",
                    payload={
                        "documentId": doc.get("documentId"),
                        "status": doc.get("status"),
                        "sourceUrl": doc.get("sourceUrl"),
                        "connectorId": doc.get("connectorId"),
                    },
                    createdAt=now,
                ).model_dump()
            )
    for connector in connector_docs:
        artifact_id = f"{run_id}:connector:{connector['connectorId']}"
        if artifact_id not in existing_artifact_ids:
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="connector_candidate",
                    title=str(connector.get("name") or connector.get("connectorId") or "Connector"),
                    refId=str(connector.get("connectorId") or ""),
                    status="persisted",
                    visibility="normal" if connector.get("type") in {"web", "knowledge"} else "dev",
                    summary=f"Persisted {connector.get('type', 'connector')} connector candidate.",
                    payload={
                        "connectorId": connector.get("connectorId"),
                        "type": connector.get("type"),
                        "status": connector.get("status"),
                        "discoveryStatus": connector.get("discoveryStatus"),
                        "toolIds": connector.get("toolIds", []),
                        "entityIds": connector.get("capabilityDiscovery", {}).get("entityIds", []) if isinstance(connector.get("capabilityDiscovery"), dict) else [],
                    },
                    createdAt=now,
                ).model_dump()
            )
    for tool in tool_docs:
        artifact_id = f"{run_id}:tool:{tool['toolId']}"
        if artifact_id not in existing_artifact_ids:
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="tool_candidate",
                    title=str(tool.get("name") or tool.get("toolId") or "Tool"),
                    refId=str(tool.get("toolId") or ""),
                    status="persisted",
                    visibility="dev",
                    summary=f"Persisted {tool.get('executionType', 'tool')} candidate.",
                    payload={
                        "toolId": tool.get("toolId"),
                        "name": tool.get("name"),
                        "connectorId": tool.get("connectorId"),
                        "policyBoundary": tool.get("policyBoundary"),
                        "riskLevel": tool.get("riskLevel"),
                        "executorBlueprint": tool.get("executorBlueprint") if isinstance(tool.get("executorBlueprint"), dict) else None,
                    },
                    createdAt=now,
                ).model_dump()
            )
    for entity in entity_docs:
        artifact_id = f"{run_id}:entity:{entity['entityId']}"
        if artifact_id not in existing_artifact_ids:
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="entity_candidate",
                    title=str(entity.get("name") or entity.get("entityId") or "Entity"),
                    refId=str(entity.get("entityId") or ""),
                    status="persisted",
                    visibility="dev",
                    summary="Persisted inferred business entity candidate.",
                    payload={
                        "entityId": entity.get("entityId"),
                        "name": entity.get("name"),
                        "sourceConnectorId": entity.get("sourceConnectorId"),
                        "fieldCount": len(entity.get("fields") or []),
                    },
                    createdAt=now,
                ).model_dump()
            )
    if benchmark and f"{run_id}:benchmark:{benchmark['benchmarkId']}" not in existing_artifact_ids:
        artifacts.append(
            CompanyHarvestArtifact(
                artifactId=f"{run_id}:benchmark:{benchmark['benchmarkId']}",
                kind="benchmark",
                title=str(benchmark.get("name") or "Company Harvest Benchmark"),
                refId=str(benchmark.get("benchmarkId") or ""),
                status="persisted",
                visibility="dev",
                summary=f"Created benchmark with {len(task_docs)} task candidate(s).",
                payload={"benchmarkId": benchmark.get("benchmarkId"), "taskIds": [task.get("taskId") for task in task_docs]},
                createdAt=now,
            ).model_dump()
        )

    steps = list(run.get("steps") or _new_steps())
    steps = _set_step(steps, "indexing_knowledge", "done", f"Prepared {len(knowledge_docs)} knowledge document(s) and {1 if knowledge else 0} knowledge connector candidate(s).")
    steps = _set_step(steps, "discovering_systems", "done", f"Discovered {len(connector_docs)} system connector candidate(s).")
    steps = _set_step(steps, "discovering_connectors", "done", f"Persisted {len(connector_docs)} connector candidate(s).")
    steps = _set_step(steps, "discovering_tools", "done", f"Persisted {len(tool_docs)} tool candidate(s).")
    steps = _set_step(steps, "discovering_entities", "done", f"Persisted {len(entity_docs)} business entity candidate(s).")
    steps = _set_step(steps, "discovering_tasks", "done", f"Discovered {len(task_docs)} task candidate(s).")
    steps = _set_step(steps, "building_benchmarks", "done", f"Created company harvest benchmark {benchmark.get('benchmarkId', '')}.")
    steps = _set_step(steps, "solving_tasks", "pending", "Ready for TaskHarvester to solve benchmark tasks.")

    normal_summary = {
        **_normal_summary(intake, artifacts, questions),
        "systemsFound": len(connector_docs),
        "knowledgeSourcesFound": 1 if knowledge else 0,
        "knowledgeDocumentsFound": len(knowledge_docs),
        "taskCandidatesFound": len(task_docs),
        "toolCandidatesFound": len(tool_docs),
        "entityCandidatesFound": len(entity_docs),
        "benchmarkId": benchmark.get("benchmarkId", ""),
        "connectorIds": [doc.get("connectorId") for doc in connector_docs],
        "connectorsReadyForFactory": sum(1 for doc in connector_docs if _connector_typed_tool_count(doc) > 0),
        "connectorImplementationGaps": len(connector_gaps),
        "connectorImplementationGapIds": [gap.get("connectorId") for gap in connector_gaps],
        "customConnectorExecutorBlueprints": len(executor_blueprints),
        "missingCustomConnectorExecutors": sum(1 for item in executor_blueprints if item.get("registrationStatus") == "missing"),
        "customConnectorExecutorNames": [item.get("executorName") for item in executor_blueprints],
        "knowledgeDocumentIds": [doc.get("documentId") for doc in knowledge_docs],
        "recommendedNextAction": "Run TaskHarvester for discovered benchmark tasks.",
    }
    dev_summary = {
        **_dev_summary(intake, artifacts, questions),
        "connectorIds": [doc.get("connectorId") for doc in connector_docs],
        "toolIds": [doc.get("toolId") for doc in tool_docs],
        "entityIds": [doc.get("entityId") for doc in entity_docs],
        "benchmarkId": benchmark.get("benchmarkId", ""),
        "taskIds": [task.get("taskId") for task in task_docs],
        "knowledgeDocumentIds": [doc.get("documentId") for doc in knowledge_docs],
        "connectorImplementationGaps": connector_gaps,
        "customConnectorExecutorBlueprints": executor_blueprints,
    }
    benchmark_id = str(benchmark.get("benchmarkId") or "")
    missing_executor_blueprints = [
        item for item in executor_blueprints if str(item.get("registrationStatus") or "") == "missing"
    ]
    if missing_executor_blueprints:
        next_action = {
            "kind": "implement_connectors",
            "label": "Implement missing connector executors",
            "benchmarkId": benchmark_id,
            "executorNames": [
                str(item.get("executorName") or "")
                for item in missing_executor_blueprints
                if item.get("executorName")
            ],
            "toolNames": [
                str(item.get("toolName") or "")
                for item in missing_executor_blueprints
                if item.get("toolName")
            ],
            "afterAction": {
                "kind": "run_task_harvester",
                "label": "Solve discovered benchmark tasks",
                "benchmarkId": benchmark_id,
            },
        }
    else:
        next_action = {
            "kind": "run_task_harvester",
            "label": "Solve discovered benchmark tasks",
            "benchmarkId": benchmark_id,
        }
    normal_summary["recommendedNextAction"] = str(next_action.get("label") or "")
    update = {
        "status": "solving_tasks",
        "currentStep": "solving_tasks",
        "steps": steps,
        "artifacts": artifacts,
        "questions": questions,
        "normalSummary": normal_summary,
        "devSummary": dev_summary,
        "nextAction": next_action,
        "updatedAt": now,
    }
    await company_harvest_runs_collection.update_one({"runId": run_id}, {"$set": update})
    await company_intakes_collection.update_one(
        {"intakeId": intake.get("intakeId", "")},
        {"$set": {"status": "harvesting", "updatedAt": now}},
    )
    return {**run, **update}


def _artifact_exists(artifacts: list[dict[str, Any]], artifact_id: str) -> bool:
    return any(str(item.get("artifactId") or "") == artifact_id for item in artifacts if isinstance(item, dict))


def _agent_delivery_summary(agent_build: dict[str, Any], *, include_raw_surfaces: bool = False) -> dict[str, Any]:
    agents = []
    ready_agents = 0
    top_level_missing_executor_count = int(agent_build.get("missingToolExecutorCount") or 0)
    missing_tool_names = [str(item) for item in agent_build.get("missingToolNames") or [] if item]
    for agent in agent_build.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("agentId") or "")
        if not agent_id:
            continue
        runtime_readiness = agent.get("runtimeReadiness") if isinstance(agent.get("runtimeReadiness"), dict) else {}
        agent_missing_executors = int(runtime_readiness.get("missingToolExecutorCount") or 0)
        agent_missing_tools = [str(item) for item in runtime_readiness.get("missingToolNames") or [] if item]
        for tool_name in agent_missing_tools:
            if tool_name not in missing_tool_names:
                missing_tool_names.append(tool_name)
        is_ready = str(agent.get("status") or "") == "ready" and agent_missing_executors == 0
        if is_ready:
            ready_agents += 1
        delivery_surfaces = agent.get("deliverySurfaces") if isinstance(agent.get("deliverySurfaces"), dict) else {}
        api_surface = delivery_surfaces.get("api") if isinstance(delivery_surfaces.get("api"), dict) else {}
        widget_surface = delivery_surfaces.get("widget") if isinstance(delivery_surfaces.get("widget"), dict) else {}
        chat_surface = delivery_surfaces.get("chat") if isinstance(delivery_surfaces.get("chat"), dict) else {}
        widget_payload = widget_surface or {"available": True, "agentId": agent_id, "embedScript": "/embed/v1/widget.js"}
        payload = {
            "agentId": agent_id,
            "name": str(agent.get("name") or agent_id),
            "runtimeKind": str(agent.get("runtimeKind") or "model_agent"),
            "status": str(agent.get("status") or ""),
            "trainingStatus": str(agent.get("trainingStatus") or ""),
            "ready": is_ready,
            "chatAvailable": is_ready and bool(chat_surface.get("available", True)),
            "apiEndpoint": str(api_surface.get("endpoint") or f"/runtime/agents/{agent_id}/step"),
            "widgetAvailable": is_ready and bool(widget_payload.get("available", True)),
            "widgetEmbedScript": str(widget_payload.get("embedScript") or "/embed/v1/widget.js"),
        }
        if include_raw_surfaces:
            payload["deliverySurfaces"] = delivery_surfaces
            payload["runtimeReadiness"] = runtime_readiness
        agents.append(payload)
    if not agents:
        for agent_id in [str(item) for item in agent_build.get("agentIds") or [] if item]:
            ready_agents += 1
            agents.append(
                {
                    "agentId": agent_id,
                    "name": agent_id,
                    "runtimeKind": agent_id.rsplit(":", 1)[-1] if ":" in agent_id else "model_agent",
                    "status": "ready",
                    "trainingStatus": "",
                    "ready": True,
                    "chatAvailable": True,
                    "apiEndpoint": f"/runtime/agents/{agent_id}/step",
                    "widget": {"available": True, "agentId": agent_id, "embedScript": "/embed/v1/widget.js"},
                }
            )
    missing_executor_count = max(top_level_missing_executor_count, len(missing_tool_names))
    state = "ready" if agents and ready_agents == len(agents) and missing_executor_count == 0 else "blocked" if agents else "empty"
    return {
        "state": state,
        "agentCount": len(agents),
        "readyAgentCount": ready_agents,
        "blockedAgentCount": max(0, len(agents) - ready_agents),
        "missingToolExecutorCount": missing_executor_count,
        "missingToolNames": missing_tool_names,
        "agents": agents,
        "surfaces": {
            "chat": bool(agents) and ready_agents > 0,
            "api": bool(agents) and ready_agents > 0,
            "widget": bool(agents) and ready_agents > 0,
        },
    }


def _task_harvest_implementation_gaps(task_harvest: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for result in task_harvest.get("results") or []:
        if not isinstance(result, dict):
            continue
        strategy = result.get("strategy") if isinstance(result.get("strategy"), dict) else {}
        for gap in strategy.get("implementationGaps") or []:
            if not isinstance(gap, dict):
                continue
            connector_id = str(gap.get("connectorId") or "")
            tool_id = str(gap.get("toolId") or "")
            tool_name = str(gap.get("toolName") or "")
            key = (connector_id, tool_id, tool_name)
            if key in seen:
                continue
            seen.add(key)
            gaps.append(
                {
                    "kind": str(gap.get("kind") or "connector_tool_executor_missing"),
                    "taskId": str(result.get("taskId") or ""),
                    "trajectoryId": str(result.get("trajectoryId") or ""),
                    "connectorId": connector_id,
                    "toolId": tool_id,
                    "toolName": tool_name,
                    "strategy": str(strategy.get("strategy") or ""),
                    "executionReadiness": str(strategy.get("executionReadiness") or ""),
                    "nextAction": str(gap.get("nextAction") or "Implement or attach a connector executor before this task can be executed end to end."),
                }
            )
    return gaps


async def record_company_harvest_results(
    run_id: str,
    *,
    knowledge_index_jobs: list[dict[str, Any]] | None = None,
    harvester_output: dict[str, Any] | CompanyHarvesterOutput | None = None,
    task_harvest: dict[str, Any] | None = None,
    promotion: dict[str, Any] | None = None,
    agent_build: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = await company_harvest_runs_collection.find_one({"runId": run_id}, {"_id": 0})
    if not run:
        raise ValueError("Company harvest run not found")
    artifacts = list(run.get("artifacts") or [])
    steps = list(run.get("steps") or _new_steps())
    now = now_iso()
    normal_summary = dict(run.get("normalSummary") or {})
    dev_summary = dict(run.get("devSummary") or {})

    if harvester_output is not None:
        output = normalize_company_harvester_output(harvester_output)
        summary = company_harvester_output_summary(output)
        artifact_id = f"{run_id}:company_harvester_output"
        if not _artifact_exists(artifacts, artifact_id):
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="company_harvester_output",
                    title="Company harvester output",
                    refId=str(output.benchmarkId or normal_summary.get("benchmarkId") or ""),
                    status="persisted",
                    visibility="dev",
                    summary=f"Validated {summary['proposedTaskCount']} task proposal(s) and {summary['taskSolutionCount']} task solution(s).",
                    payload={"companyHarvesterOutput": output.model_dump()},
                    createdAt=now,
                ).model_dump()
            )
        normal_summary["companyHarvesterOutput"] = {
            "proposedTaskCount": summary["proposedTaskCount"],
            "taskSolutionCount": summary["taskSolutionCount"],
            "agentConfigCount": summary["agentConfigCount"],
            "runtimeKinds": summary["runtimeKinds"],
            "confidence": summary["confidence"],
        }
        dev_summary["companyHarvesterOutput"] = output.model_dump()

    if knowledge_index_jobs is not None:
        jobs = [dict(item) for item in knowledge_index_jobs if isinstance(item, dict)]
        document_ids = [str((job.get("payload") or {}).get("documentId") or "") for job in jobs if isinstance(job.get("payload"), dict)]
        artifact_id = f"{run_id}:knowledge_index"
        if jobs and not _artifact_exists(artifacts, artifact_id):
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="knowledge_document",
                    title="Knowledge indexing jobs",
                    refId=str(run.get("intakeId") or ""),
                    status="queued",
                    visibility="dev",
                    summary=f"Queued {len(jobs)} knowledge indexing job(s).",
                    payload={"documentIds": document_ids, "jobIds": [job.get("jobId") for job in jobs if job.get("jobId")]},
                    createdAt=now,
                ).model_dump()
            )
        normal_summary["knowledgeIndexJobsQueued"] = len(jobs)
        normal_summary["knowledgeIndexDocumentIds"] = document_ids
        dev_summary["knowledgeIndexJobs"] = jobs

    if task_harvest:
        if "harvestedCount" in task_harvest:
            harvested_count = int(task_harvest.get("harvestedCount") or 0)
        elif "harvested" in task_harvest:
            harvested_count = int(task_harvest.get("harvested") or 0)
        else:
            harvested_count = sum(1 for item in task_harvest.get("results") or [] if isinstance(item, dict) and item.get("status") in {"harvested", "approved"})
        failed_count = int(task_harvest.get("failedCount") or 0)
        implementation_required_count = int(
            task_harvest.get("implementationRequiredCount")
            or sum(1 for item in task_harvest.get("results") or [] if isinstance(item, dict) and item.get("status") == "implementation_required")
        )
        implementation_gaps = _task_harvest_implementation_gaps(task_harvest)
        artifact_id = f"{run_id}:task_harvest:{task_harvest.get('benchmarkId') or normal_summary.get('benchmarkId') or 'benchmark'}"
        if not _artifact_exists(artifacts, artifact_id):
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="trajectory",
                    title="Task harvest results",
                    refId=str(task_harvest.get("benchmarkId") or normal_summary.get("benchmarkId") or ""),
                    status="persisted",
                    visibility="dev",
                    summary=f"TaskHarvester generated {harvested_count} trajectory result(s).",
                    payload={"taskHarvest": task_harvest},
                    createdAt=now,
                ).model_dump()
            )
        steps = _set_step(steps, "solving_tasks", "done", f"Solved {harvested_count} benchmark task(s); {failed_count} failed.")
        normal_summary["tasksSolved"] = harvested_count
        normal_summary["taskHarvestFailures"] = failed_count
        normal_summary["tasksImplementationRequired"] = implementation_required_count
        normal_summary["taskImplementationGaps"] = len(implementation_gaps)
        normal_summary["taskImplementationGapToolNames"] = [gap.get("toolName") for gap in implementation_gaps if gap.get("toolName")]
        dev_summary["taskHarvest"] = task_harvest
        dev_summary["taskImplementationGaps"] = implementation_gaps

    if promotion:
        promoted_count = int(
            promotion.get("promotedCount")
            or promotion.get("promoted")
            or promotion.get("skillCount")
            or len(promotion.get("promotedSkillIds") or promotion.get("skillIds") or [])
        )
        artifact_id = f"{run_id}:promotion:{promotion.get('benchmarkId') or normal_summary.get('benchmarkId') or 'benchmark'}"
        if not _artifact_exists(artifacts, artifact_id):
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="skill",
                    title="Skill promotion results",
                    refId=str(promotion.get("benchmarkId") or normal_summary.get("benchmarkId") or ""),
                    status="persisted",
                    visibility="normal",
                    summary=f"Promoted {promoted_count} approved trajectory result(s) to skill(s).",
                    payload={"promotion": promotion},
                    createdAt=now,
                ).model_dump()
            )
        steps = _set_step(steps, "judging_trajectories", "done", "Judged harvested trajectories.")
        steps = _set_step(steps, "promoting_skills", "done", f"Promoted {promoted_count} skill(s).")
        normal_summary["skillsReady"] = promoted_count
        dev_summary["promotion"] = promotion

    if agent_build:
        agent_ids = [str(item) for item in agent_build.get("agentIds") or [] if item]
        normal_delivery_summary = _agent_delivery_summary(agent_build)
        dev_delivery_summary = _agent_delivery_summary(agent_build, include_raw_surfaces=True)
        artifact_id = f"{run_id}:agent_build:{agent_build.get('companyId') or run.get('companyId') or 'company'}"
        if not _artifact_exists(artifacts, artifact_id):
            artifacts.append(
                CompanyHarvestArtifact(
                    artifactId=artifact_id,
                    kind="agent_config",
                    title="Generated company agents",
                    refId=str(agent_build.get("companyId") or run.get("companyId") or ""),
                    status="persisted",
                    visibility="normal",
                    summary=f"Built {len(agent_ids)} company agent config(s).",
                    payload={"agentIds": agent_ids, "agentCount": agent_build.get("agentCount"), "skillCount": agent_build.get("skillCount"), "toolCount": agent_build.get("toolCount")},
                    createdAt=now,
                ).model_dump()
            )
        steps = _set_step(steps, "building_agents", "done", f"Built {len(agent_ids)} company agent config(s).")
        normal_summary["agentsReady"] = int(normal_delivery_summary.get("readyAgentCount") or 0)
        normal_summary["agentsBlocked"] = int(normal_delivery_summary.get("blockedAgentCount") or 0)
        normal_summary["missingAgentToolExecutors"] = int(normal_delivery_summary.get("missingToolExecutorCount") or 0)
        normal_summary["missingAgentToolExecutorNames"] = normal_delivery_summary.get("missingToolNames") or []
        normal_summary["agentIds"] = agent_ids
        normal_summary["delivery"] = normal_delivery_summary
        dev_summary["agentBuild"] = agent_build
        dev_summary["delivery"] = dev_delivery_summary

    agent_delivery_state = str((normal_summary.get("delivery") if isinstance(normal_summary.get("delivery"), dict) else {}).get("state") or "")
    pending_task_gaps = int(normal_summary.get("taskImplementationGaps") or 0)
    if agent_build and agent_delivery_state == "ready" and pending_task_gaps == 0:
        status = "ready"
        current_step = "ready"
        next_action = {
            "kind": "use_agents",
            "label": "Use generated company agents",
            "agentIds": normal_summary.get("agentIds", []),
            "delivery": normal_summary.get("delivery", {}),
        }
    elif agent_build:
        status = "building_agents"
        current_step = "building_agents"
        missing_tool_names = [
            str(item)
            for item in [
                *(normal_summary.get("missingAgentToolExecutorNames") or []),
                *(normal_summary.get("taskImplementationGapToolNames") or []),
            ]
            if item
        ]
        next_action = {
            "kind": "implement_connectors",
            "label": "Implement missing connector executors",
            "benchmarkId": normal_summary.get("benchmarkId", ""),
            "toolNames": list(dict.fromkeys(missing_tool_names)),
            "agentIds": normal_summary.get("agentIds", []),
        }
    elif promotion:
        status = "building_agents"
        current_step = "building_agents"
        next_action = {"kind": "build_agents", "label": "Build company agents", "benchmarkId": normal_summary.get("benchmarkId", "")}
    elif task_harvest:
        if int(normal_summary.get("taskImplementationGaps") or 0) > 0:
            status = "solving_tasks"
            current_step = "solving_tasks"
            next_action = {
                "kind": "implement_connectors",
                "label": "Implement missing connector executors",
                "benchmarkId": normal_summary.get("benchmarkId", ""),
                "toolNames": normal_summary.get("taskImplementationGapToolNames", []),
            }
        else:
            status = "judging_trajectories"
            current_step = "judging_trajectories"
            next_action = {"kind": "judge_trajectories", "label": "Judge harvested trajectories", "benchmarkId": normal_summary.get("benchmarkId", "")}
    else:
        status = str(run.get("status") or "solving_tasks")
        current_step = str(run.get("currentStep") or status)
        next_action = run.get("nextAction") or {}

    normal_summary["recommendedNextAction"] = str(next_action.get("label") or normal_summary.get("recommendedNextAction") or "")
    update = {
        "status": status,
        "currentStep": current_step,
        "steps": steps,
        "artifacts": artifacts,
        "normalSummary": normal_summary,
        "devSummary": dev_summary,
        "nextAction": next_action,
        "updatedAt": now,
    }
    await company_harvest_runs_collection.update_one({"runId": run_id}, {"$set": update})
    return {**run, **update}


async def company_harvest_status(run_id: str, *, mode: str = "normal", email: str = "") -> dict[str, Any]:
    query: dict[str, Any] = {"runId": run_id}
    if email:
        query["email"] = email
    run = await company_harvest_runs_collection.find_one(query, {"_id": 0})
    if not run:
        raise ValueError("Company harvest run not found")
    if mode == "dev":
        return run
    return {
        "runId": run.get("runId", ""),
        "intakeId": run.get("intakeId", ""),
        "companyId": run.get("companyId", ""),
        "status": run.get("status", ""),
        "currentStep": run.get("currentStep", ""),
        "steps": [step for step in run.get("steps") or [] if step.get("visibility") == "normal"],
        "summary": run.get("normalSummary") or {},
        "delivery": (run.get("normalSummary") or {}).get("delivery") or {},
        "questions": [
            {
                "questionId": question.get("questionId", ""),
                "code": question.get("code", ""),
                "prompt": question.get("prompt", ""),
                "severity": question.get("severity", ""),
                "expectedAnswerType": question.get("expectedAnswerType", ""),
            }
            for question in run.get("questions") or []
            if question.get("visibility", "normal") == "normal"
        ],
        "nextAction": run.get("nextAction") or {},
        "errors": run.get("errors") or [],
    }
