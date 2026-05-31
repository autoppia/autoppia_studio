import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import (
    companies_collection,
    connectors_collection,
    evals_collection,
    onboarding_sessions_collection,
    operator_webs_collection,
    operators_collection,
    trajectories_collection,
)

router = APIRouter()


KNOWN_CONNECTORS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail",
        "type": "gmail",
        "category": "email",
        "description": "Gmail connector for reading, searching and drafting email responses.",
    },
    "smtp": {
        "name": "SMTP",
        "type": "smtp",
        "category": "email",
        "description": "SMTP connector for sending approved emails.",
    },
    "email": {
        "name": "SMTP",
        "type": "smtp",
        "category": "email",
        "description": "Email connector for sending approved emails.",
    },
    "telegram": {
        "name": "Telegram",
        "type": "telegram",
        "category": "communication",
        "description": "Telegram connector for sending approved messages.",
    },
    "holded": {
        "name": "Holded",
        "type": "holded",
        "category": "software",
        "description": "Holded connector for clients, contacts and invoices.",
    },
    "bopa": {
        "name": "BOPA",
        "type": "web",
        "category": "web",
        "description": "BOPA public website connector.",
        "config": {"baseUrl": "https://www.bopa.ad/"},
    },
    "documents": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded documents and internal sources.",
    },
    "docs": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded documents and internal sources.",
    },
    "pdf": {
        "name": "Documents",
        "type": "knowledge",
        "category": "knowledge",
        "description": "Company knowledge connector for uploaded PDFs and internal sources.",
    },
}

GENERIC_SOFTWARE_HINTS = ("crm", "erp", "saas", "dashboard", "stripe", "salesforce", "hubspot", "notion")
GENERIC_BROWSER_HINTS = ("website", "web", "portal", "government", "gobierno", "bopa.ad", "url")


class OnboardingStartRequest(BaseModel):
    email: str
    companyId: str = ""
    seedPrompt: str = ""


class OnboardingMessageRequest(BaseModel):
    email: str
    message: str


class OnboardingFinalizeRequest(BaseModel):
    email: str
    draft: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom"


def _env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _known_connector(keyword: str) -> dict[str, Any]:
    connector = dict(KNOWN_CONNECTORS[keyword])
    connector["config"] = dict(connector.get("config") or {})
    if connector["type"] == "smtp":
        connector["config"].update(
            {
                key: value
                for key, value in {
                    "email": _env("SMTP_EMAIL", "EMAIL_HOST_USERNAME", "EMAIL_USER", "EMAIL_HOST_USER"),
                    "password": _env("SMTP_PASSWORD", "SMTP_PASS", "EMAIL_HOST_PASSWORD"),
                    "smtpServer": _env("SMTP_SERVER", "EMAIL_HOST"),
                    "smtpPort": _env("SMTP_PORT", "EMAIL_PORT"),
                    "imapServer": _env("IMAP_SERVER"),
                    "imapPort": _env("IMAP_PORT"),
                }.items()
                if value
            }
        )
        connector["status"] = "connected" if connector["config"].get("email") and connector["config"].get("password") and connector["config"].get("smtpServer") else "needs_auth"
    elif connector["type"] == "gmail":
        connector["config"].update(
            {
                key: value
                for key, value in {
                    "clientId": _env("GMAIL_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
                    "clientSecret": _env("GMAIL_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
                    "refreshToken": _env("GMAIL_REFRESH_TOKEN", "GOOGLE_OAUTH_REFRESH_TOKEN"),
                    "userEmail": _env("GMAIL_USER_EMAIL", "EMAIL_HOST_USERNAME", "SMTP_EMAIL"),
                    "scopes": _env("GMAIL_SCOPES") or "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send",
                }.items()
                if value
            }
        )
        connector["status"] = "connected" if connector["config"].get("refreshToken") else "needs_auth"
    elif connector["type"] in {"web", "knowledge"}:
        connector["status"] = "connected"
    else:
        connector["status"] = "needs_auth"
    return connector


def _default_draft() -> dict[str, Any]:
    return {
        "company": {
            "name": "",
            "industry": "",
            "description": "",
        },
        "agent": {
            "name": "",
            "websiteUrl": "",
            "successCriteria": "The user confirms the result, cited sources are correct, and sensitive write actions require approval.",
            "customInstructions": "",
        },
        "connectors": [],
        "tasks": [],
        "questions": [
            "What company or workflow are we automating?",
            "Which systems do you use? For example Gmail, SMTP, Holded, Telegram, BOPA, CRM, ERP, dashboards or APIs.",
            "List 3-10 tasks you want the agent to handle.",
        ],
    }


def _connector_key(connector: dict[str, Any]) -> str:
    return f"{connector.get('type')}:{str(connector.get('name') or '').lower()}"


def _merge_connector(draft: dict[str, Any], connector: dict[str, Any]) -> None:
    existing = {_connector_key(item): item for item in draft["connectors"]}
    key = _connector_key(connector)
    if key in existing:
        existing[key].update({k: v for k, v in connector.items() if v not in ("", None, {})})
        return
    draft["connectors"].append(
        {
            "name": connector.get("name", "Custom Connector"),
            "type": connector.get("type", "api"),
            "category": connector.get("category", "software"),
            "description": connector.get("description", ""),
            "config": connector.get("config", {}),
            "status": connector.get("status", "not_connected"),
        }
    )


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s,)]+", text)


def _extract_tasks(text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines()]
    tasks: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\).:-]\s*", "", line).strip()
        if len(cleaned) < 18:
            continue
        if any(word in cleaned.lower() for word in ("task", "tarea", "necesito", "quiero", "recibo", "buscar", "leer", "enviar", "responder", "download", "summar")):
            tasks.append(cleaned)
    if not tasks and any(word in text.lower() for word in ("tasks", "tareas", "automate", "automatizar")):
        chunks = re.split(r"[.;]\s+", text)
        tasks = [chunk.strip() for chunk in chunks if len(chunk.strip()) > 28][:10]
    return tasks[:10]


def _apply_message(draft: dict[str, Any], message: str) -> dict[str, Any]:
    text = message.strip()
    lower = text.lower()

    if not draft["company"]["name"]:
        name_match = re.search(r"(?:company|empresa|compañ[ií]a|asesor[ií]a)\s+(?:is|es|called|llamada?)?\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ -]{2,40})", text)
        if name_match:
            draft["company"]["name"] = name_match.group(1).strip(" .")
    if "celeris" in lower:
        draft["company"]["name"] = "Celeris"
        draft["company"]["industry"] = "Labor advisory, Andorra"
        draft["company"]["description"] = "Asesoría laboral en Andorra que automatiza emails, facturas, comunicaciones y seguimiento del BOPA."

    if not draft["company"]["description"] and len(text) > 40:
        draft["company"]["description"] = text[:500]

    if any(term in lower for term in ("andorra", "laboral", "asesoria", "asesoría")) and not draft["company"]["industry"]:
        draft["company"]["industry"] = "Labor advisory, Andorra"

    for url in _extract_urls(text):
        if "bopa.ad" in url:
            _merge_connector(draft, _known_connector("bopa"))
        elif not draft["agent"]["websiteUrl"]:
            draft["agent"]["websiteUrl"] = url
            _merge_connector(
                draft,
                {
                    "name": re.sub(r"^https?://", "", url).split("/")[0],
                    "type": "web",
                    "category": "web",
                    "description": f"Browser/web connector for {url}",
                    "config": {"baseUrl": url},
                    "status": "connected",
                },
            )

    for keyword in KNOWN_CONNECTORS:
        if keyword in lower:
            _merge_connector(draft, _known_connector(keyword))

    if "swagger" in lower or "openapi" in lower or "api docs" in lower:
        url = next(iter(_extract_urls(text)), "")
        _merge_connector(
            draft,
            {
                "name": "OpenAPI",
                "type": "api",
                "category": "api",
                "description": "Custom API connector generated from OpenAPI or Swagger documentation.",
                "config": {"openApiUrl": url} if url else {},
                "status": "not_connected",
            },
        )

    for hint in GENERIC_SOFTWARE_HINTS:
        if hint in lower and not any(hint in str(item.get("name", "")).lower() for item in draft["connectors"]):
            _merge_connector(
                draft,
                {
                    "name": hint.upper() if len(hint) <= 4 else hint.title(),
                    "type": "api",
                    "category": "software",
                    "description": f"Custom software connector for {hint}. Add API docs or auth to generate a richer toolkit.",
                    "status": "not_connected",
                },
            )

    if any(hint in lower for hint in GENERIC_BROWSER_HINTS) and "bopa" not in lower and not draft["agent"]["websiteUrl"]:
        _merge_connector(
            draft,
            {
                "name": "Browser",
                "type": "web",
                "category": "web",
                "description": "Browser runtime connector for web tasks without a structured API.",
                "status": "connected",
            },
        )

    for task in _extract_tasks(text):
        if not any(existing["prompt"].lower() == task.lower() for existing in draft["tasks"]):
            draft["tasks"].append(
                {
                    "name": f"Task {len(draft['tasks']) + 1}",
                    "prompt": task,
                    "successCriteria": "The user approves the result and all sensitive writes are confirmed before execution.",
                    "status": "draft",
                }
            )

    if draft["company"]["name"] and not draft["agent"]["name"]:
        draft["agent"]["name"] = f"{draft['company']['name']} Agent"
    if any(item.get("name") == "BOPA" for item in draft["connectors"]) and not draft["agent"]["websiteUrl"]:
        draft["agent"]["websiteUrl"] = "https://www.bopa.ad/"

    missing: list[str] = []
    if not draft["company"]["name"]:
        missing.append("company name")
    if not draft["connectors"]:
        missing.append("connectors or systems")
    if not draft["tasks"]:
        missing.append("tasks")
    draft["questions"] = _questions_for_missing(missing)
    return draft


def _questions_for_missing(missing: list[str]) -> list[str]:
    if not missing:
        return [
            "Review the draft. If it looks right, create the agent. Otherwise tell me what to change.",
        ]
    questions = []
    if "company name" in missing:
        questions.append("What is the company or project name?")
    if "connectors or systems" in missing:
        questions.append("Which systems should this agent use? Examples: Gmail, SMTP, Holded, Telegram, BOPA, CRM, ERP, dashboard, API docs.")
    if "tasks" in missing:
        questions.append("List the tasks you want this agent to solve, one per line if possible.")
    return questions


def _assistant_message(draft: dict[str, Any]) -> str:
    connectors = ", ".join(item["name"] for item in draft["connectors"]) or "none yet"
    task_count = len(draft["tasks"])
    if draft["questions"] and "Review the draft" not in draft["questions"][0]:
        return f"I updated the onboarding draft. Current connectors: {connectors}. Tasks captured: {task_count}. {draft['questions'][0]}"
    return f"Draft is ready: {draft['company']['name']} with connectors {connectors} and {task_count} benchmark tasks. You can create the company agent now or tell me edits."


def _session_payload(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": doc.get("sessionId", ""),
        "email": doc.get("email", ""),
        "companyId": doc.get("companyId", ""),
        "messages": doc.get("messages", []),
        "draft": doc.get("draft", _default_draft()),
        "status": doc.get("status", "collecting"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


async def _create_eval(
    *,
    email: str,
    operator_id: str,
    operator_name: str,
    website_url: str,
    task: dict[str, Any],
) -> str:
    now = _now()
    eval_id = str(uuid.uuid4())
    await evals_collection.insert_one(
        {
            "evalId": eval_id,
            "email": email,
            "prompt": task["prompt"],
            "initialUrl": website_url,
            "benchmarkId": f"operator-{operator_id}",
            "benchmarkName": f"{operator_name} Benchmark",
            "operatorId": operator_id,
            "operatorName": operator_name,
            "operatorTaskName": task["name"],
            "successCriteria": task.get("successCriteria", ""),
            "createdAt": now,
        }
    )
    return eval_id


@router.post("/onboarding/sessions")
async def start_onboarding(body: OnboardingStartRequest):
    draft = _default_draft()
    messages = [
        {
            "role": "assistant",
            "content": "Tell me what company or workflow you want to automate, which systems it uses, and the tasks the agent should learn. I will turn that into connectors, toolkits, benchmark tasks and a company agent.",
            "createdAt": _now(),
        }
    ]
    if body.seedPrompt.strip():
        draft = _apply_message(draft, body.seedPrompt)
        messages.append({"role": "user", "content": body.seedPrompt.strip(), "createdAt": _now()})
        messages.append({"role": "assistant", "content": _assistant_message(draft), "createdAt": _now()})
    now = _now()
    status = "ready" if draft["company"]["name"] and draft["connectors"] and draft["tasks"] else "collecting"
    doc = {
        "sessionId": str(uuid.uuid4()),
        "email": body.email,
        "companyId": body.companyId,
        "messages": messages,
        "draft": draft,
        "status": status,
        "createdAt": now,
        "updatedAt": now,
    }
    await onboarding_sessions_collection.insert_one(doc)
    return {"session": _session_payload(doc)}


@router.post("/onboarding/sessions/{session_id}/messages")
async def send_onboarding_message(session_id: str, body: OnboardingMessageRequest):
    doc = await onboarding_sessions_collection.find_one({"sessionId": session_id, "email": body.email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    draft = _apply_message(doc.get("draft") or _default_draft(), body.message)
    messages = doc.get("messages", [])
    messages.append({"role": "user", "content": body.message.strip(), "createdAt": _now()})
    messages.append({"role": "assistant", "content": _assistant_message(draft), "createdAt": _now()})
    status = "ready" if draft["company"]["name"] and draft["connectors"] and draft["tasks"] else "collecting"
    await onboarding_sessions_collection.update_one(
        {"sessionId": session_id},
        {"$set": {"draft": draft, "messages": messages, "status": status, "updatedAt": _now()}},
    )
    return {"session": {**_session_payload(doc), "messages": messages, "draft": draft, "status": status, "updatedAt": _now()}}


@router.post("/onboarding/sessions/{session_id}/finalize")
async def finalize_onboarding(session_id: str, body: OnboardingFinalizeRequest):
    doc = await onboarding_sessions_collection.find_one({"sessionId": session_id, "email": body.email}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    draft = body.draft or doc.get("draft") or _default_draft()
    if not draft.get("company", {}).get("name"):
        raise HTTPException(status_code=400, detail="Company name is required")
    if not draft.get("tasks"):
        raise HTTPException(status_code=400, detail="At least one task is required")

    now = _now()
    company_id = str(uuid.uuid4())
    company = {
        "companyId": company_id,
        "email": body.email,
        "name": draft["company"].get("name", "Untitled Company").strip(),
        "description": draft["company"].get("description", "").strip(),
        "industry": draft["company"].get("industry", "").strip(),
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }
    await companies_collection.insert_one(dict(company))

    connectors = []
    for item in draft.get("connectors", []):
        connector_id = str(uuid.uuid4())
        status = item.get("status") or ("connected" if item.get("type") in ("web", "knowledge") else "not_connected")
        connector = {
            "connectorId": connector_id,
            "email": body.email,
            "companyId": company_id,
            "name": item.get("name", "Connector"),
            "type": item.get("type", "api"),
            "category": item.get("category", "software"),
            "description": item.get("description", ""),
            "status": status,
            "config": item.get("config", {}),
            "createdAt": now,
            "updatedAt": now,
        }
        await connectors_collection.insert_one(dict(connector))
        connectors.append(connector)

    operator_id = str(uuid.uuid4())
    agent = draft.get("agent", {})
    operator_name = agent.get("name") or f"{company['name']} Agent"
    website_url = agent.get("websiteUrl") or next(
        (str(connector.get("config", {}).get("baseUrl")) for connector in connectors if connector.get("config", {}).get("baseUrl")),
        "",
    )
    tasks = []
    for index, task in enumerate(draft.get("tasks", []), start=1):
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            continue
        tasks.append(
            {
                "name": task.get("name") or f"Task {index}",
                "prompt": prompt,
                "successCriteria": task.get("successCriteria", "The user confirms the result."),
                "status": "draft",
                "trajectoryId": "",
            }
        )

    operator = {
        "operatorId": operator_id,
        "email": body.email,
        "companyId": company_id,
        "name": operator_name,
        "websiteUrl": website_url,
        "runtimeEndpoint": "",
        "runtimeType": "pending",
        "status": "draft",
        "trainingStatus": "needs_trajectories",
        "harvester": "Automata Onboarding Agent",
        "runtimeCapabilities": {
            "browser": any(connector.get("type") == "web" for connector in connectors),
            "apiCalls": any(connector.get("type") in ("api", "holded", "gmail", "smtp", "telegram") for connector in connectors),
            "knowledge": any(connector.get("type") == "knowledge" for connector in connectors),
            "python": False,
            "humanApprovalForWrites": True,
        },
        "tasks": tasks,
        "trajectories": [],
        "successCriteria": agent.get("successCriteria", ""),
        "customInstructions": agent.get("customInstructions", ""),
        "createdAt": now,
        "updatedAt": now,
    }
    await operators_collection.insert_one(dict(operator))

    web_id = f"default-{operator_id}"
    await operator_webs_collection.insert_one(
        {
            "webId": web_id,
            "operatorId": operator_id,
            "email": body.email,
            "name": company["name"],
            "baseUrl": website_url,
            "authRequired": False,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    eval_ids = []
    trajectory_ids = []
    for task in tasks:
        trajectory_id = str(uuid.uuid4())
        trajectory_ids.append(trajectory_id)
        await trajectories_collection.insert_one(
            {
                "trajectoryId": trajectory_id,
                "operatorId": operator_id,
                "email": body.email,
                "webId": web_id,
                "taskName": task["name"],
                "prompt": task["prompt"],
                "successCriteria": task.get("successCriteria", ""),
                "source": "onboarding_agent",
                "status": "needs_harvest",
                "actions": [],
                "screenshots": [],
                "createdAt": now,
                "updatedAt": now,
            }
        )
        eval_ids.append(
            await _create_eval(
                email=body.email,
                operator_id=operator_id,
                operator_name=operator_name,
                website_url=website_url,
                task=task,
            )
        )

    await onboarding_sessions_collection.update_one(
        {"sessionId": session_id},
        {
            "$set": {
                "status": "finalized",
                "companyId": company_id,
                "operatorId": operator_id,
                "updatedAt": _now(),
            }
        },
    )
    return {
        "success": True,
        "company": company,
        "operatorId": operator_id,
        "connectorIds": [connector["connectorId"] for connector in connectors],
        "trajectoryIds": trajectory_ids,
        "evalIds": eval_ids,
    }
