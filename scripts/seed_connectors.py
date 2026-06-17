#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

from app.database import (  # noqa: E402
    capabilities_collection,
    companies_collection,
    connectors_collection,
    ensure_indexes,
    evals_collection,
    onboarding_sessions_collection,
    agent_webs_collection,
    agents_collection,
    tools_collection,
    trajectories_collection,
)
from app.harvesters.toolkit import ToolkitHarvester  # noqa: E402
from app.routes.agent_creation import ensure_agent_creation_job  # noqa: E402
from app.routes.connectors import CONNECTOR_TOOLKIT_DEFAULTS  # noqa: E402
from app.routes.onboarding import DEFAULT_OPERATOR_RUNTIME_ENDPOINT, DEFAULT_OPERATOR_RUNTIME_TYPE, DEFAULT_RUNTIME_PROXY_BASE, task_name_from_prompt  # noqa: E402


DEFAULT_EMAIL = "demo@autoppia.com"
DEFAULT_COMPANY = "Celeris"

CELERIS_TASKS = [
    {
        "name": "Summarize BOPA update for client email",
        "prompt": "Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.",
        "successCriteria": "The BOPA update is summarized accurately and the client email draft is ready for approval.",
    },
    {
        "name": "Classify client email request",
        "prompt": "Buscar una peticion de un cliente en email y clasificarla como nomina, contrato, factura o consulta laboral.",
        "successCriteria": "The client request is found and classified into the correct business category.",
    },
    {
        "name": "Find Holded invoice and draft reply",
        "prompt": "Encontrar la ultima factura de un cliente en Holded y preparar una respuesta por email.",
        "successCriteria": "The latest client invoice is found in Holded and an email reply is drafted for approval.",
    },
    {
        "name": "Answer from internal documents",
        "prompt": "Revisar documentos internos y responder una consulta laboral basica con fuentes.",
        "successCriteria": "The answer cites the relevant internal document sources and avoids unsupported claims.",
    },
    {
        "name": "Send Telegram team update",
        "prompt": "Enviar por Telegram un resumen breve de una novedad laboral importante para el equipo.",
        "successCriteria": "A concise Telegram update is prepared or sent only after required approval.",
    },
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = env(name)
        if value:
            return value
    return default.strip()


def compact_config(config: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in config.items() if value}


def connector_specs(email: str, company_id: str) -> list[dict[str, Any]]:
    gmail_email = first_env("GMAIL_USER_EMAIL", "EMAIL_USER", "EMAIL_HOST_USERNAME", "EMAIL_HOST_USER", "SMTP_EMAIL")
    smtp_email = first_env("SMTP_EMAIL", "EMAIL_HOST_USERNAME", "EMAIL_USER", "EMAIL_HOST_USER")
    return [
        {
            "name": "Gmail",
            "type": "gmail",
            "category": "email",
            "description": "Gmail connector seeded from Studio-style OAuth env vars.",
            "config": compact_config({
                "clientId": first_env("GMAIL_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
                "clientSecret": first_env("GMAIL_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
                "refreshToken": first_env("GMAIL_REFRESH_TOKEN", "GOOGLE_OAUTH_REFRESH_TOKEN"),
                "accessToken": first_env("GMAIL_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN"),
                "scopes": env("GMAIL_SCOPES", "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send"),
                "userEmail": gmail_email,
                "apiVersion": env("GMAIL_API_VERSION", "v1"),
                "defaultFrom": gmail_email,
                "signature": env("GMAIL_SIGNATURE", "Celeris"),
            }),
        },
        {
            "name": "SMTP",
            "type": "smtp",
            "category": "email",
            "description": "SMTP connector seeded from Studio SMTP env vars.",
            "config": compact_config({
                "password": first_env("SMTP_PASSWORD", "SMTP_PASS", "EMAIL_HOST_PASSWORD"),
                "smtpServer": first_env("SMTP_SERVER", "EMAIL_HOST"),
                "smtpPort": first_env("SMTP_PORT", "EMAIL_PORT"),
                "email": smtp_email,
                "imapServer": env("IMAP_SERVER"),
                "imapPort": env("IMAP_PORT"),
            }),
        },
        {
            "name": "Telegram",
            "type": "telegram",
            "category": "communication",
            "description": "Telegram connector seeded from bot token env vars.",
            "config": compact_config({
                "botToken": env("TELEGRAM_BOT_TOKEN"),
                "chatId": env("TELEGRAM_CHAT_ID"),
                "defaultChatId": env("TELEGRAM_CHAT_ID"),
            }),
        },
        {
            "name": "Holded",
            "type": "holded",
            "category": "software",
            "description": "Holded connector seeded from API key env vars.",
            "config": compact_config({
                "apiKey": env("HOLDED_API_KEY"),
                "workspaceId": env("HOLDED_WORKSPACE_ID"),
            }),
        },
        {
            "name": "BOPA",
            "type": "web",
            "category": "web",
            "description": "BOPA public website connector.",
            "config": compact_config({
                "baseUrl": env("BOPA_BASE_URL", "https://www.bopa.ad/"),
            }),
        },
        {
            "name": "Documents",
            "type": "knowledge",
            "category": "knowledge",
            "description": "Company document knowledge connector.",
            "config": compact_config({
                "collectionName": env("KNOWLEDGE_COLLECTION", "celeris"),
                "sourceUrl": env("KNOWLEDGE_SOURCE_URL"),
            }),
        },
    ]


def test_result(connector_type: str, config: dict[str, Any]) -> tuple[bool, str, str]:
    if connector_type in {"web", "knowledge"}:
        return True, "connected", "Connector is ready."
    defaults = CONNECTOR_TOOLKIT_DEFAULTS.get(connector_type, CONNECTOR_TOOLKIT_DEFAULTS["api"])
    missing = [field for field in defaults.get("authFields", []) if not str(config.get(field) or "").strip()]
    if missing:
        return False, "needs_auth", f"Missing auth fields: {', '.join(missing)}"
    return True, "connected", "Connector test passed. Toolkit is ready for agents."


async def ensure_company(email: str, company_name: str) -> dict[str, Any]:
    company = await companies_collection.find_one({"email": email, "name": company_name}, {"_id": 0})
    if company:
        return company

    timestamp = now()
    company = {
        "companyId": str(uuid.uuid4()),
        "email": email,
        "name": company_name,
        "description": "Local seeded company for connector testing.",
        "industry": "Labor advisory, Andorra",
        "status": "active",
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    await companies_collection.insert_one(company)
    return company


async def upsert_connector(email: str, company_id: str, spec: dict[str, Any], run_tests: bool) -> dict[str, Any]:
    timestamp = now()
    success, status, message = test_result(spec["type"], spec["config"]) if run_tests else (False, "not_connected", "")
    if spec["type"] in {"web", "knowledge"} and not run_tests:
        status = "connected"

    update = {
        "email": email,
        "companyId": company_id,
        "name": spec["name"],
        "type": spec["type"],
        "category": spec["category"],
        "description": spec["description"],
        "config": spec["config"],
        "status": status,
        "updatedAt": timestamp,
    }
    if run_tests:
        update.update({
            "lastTestAt": timestamp,
            "lastTestStatus": "pass" if success else "fail",
            "lastTestMessage": message,
        })

    existing = await connectors_collection.find_one({"email": email, "companyId": company_id, "name": spec["name"]}, {"_id": 0})
    if existing:
        await connectors_collection.update_one({"connectorId": existing["connectorId"]}, {"$set": update})
        update["connectorId"] = existing["connectorId"]
        update["createdAt"] = existing.get("createdAt", timestamp)
        return update

    doc = {"connectorId": str(uuid.uuid4()), "createdAt": timestamp, **update}
    await connectors_collection.insert_one(doc)
    return doc


async def publish_connector_tools(company_id: str) -> int:
    count = 0
    harvester = ToolkitHarvester(source="seed_toolkit")
    cursor = connectors_collection.find({"companyId": company_id}, {"_id": 0})
    async for connector in cursor:
        result = await harvester.harvest(connector)
        for tool in result.get("tools") or []:
            update = {key: value for key, value in tool.items() if key != "createdAt"}
            await tools_collection.update_one(
                {"toolId": tool["toolId"]},
                {"$set": update, "$setOnInsert": {"createdAt": tool.get("createdAt")}},
                upsert=True,
            )
            count += 1
    return count


def generic_task_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("task ") and text[5:].isdigit()


async def upsert_celeris_agent(email: str, company: dict[str, Any]) -> dict[str, Any]:
    timestamp = now()
    agent_name = f"{company['name']} Agent"
    agent_config = await agents_collection.find_one({"email": email, "companyId": company["companyId"], "name": agent_name}, {"_id": 0})
    agent_id = str(agent_config.get("agentId")) if agent_config else str(uuid.uuid4())
    website_url = env("BOPA_BASE_URL", "https://www.bopa.ad/")
    runtime_endpoint = f"{DEFAULT_RUNTIME_PROXY_BASE}/runtime/agents/{agent_id}/step" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else ""
    tasks = [{**task, "status": "draft", "trajectoryId": ""} for task in CELERIS_TASKS]
    update = {
        "email": email,
        "companyId": company["companyId"],
        "name": agent_name,
        "websiteUrl": website_url,
        "runtimeEndpoint": runtime_endpoint,
        "baseRuntimeEndpoint": DEFAULT_OPERATOR_RUNTIME_ENDPOINT,
        "runtimeType": DEFAULT_OPERATOR_RUNTIME_TYPE if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "pending",
        "status": "ready" if DEFAULT_OPERATOR_RUNTIME_ENDPOINT else "draft",
        "trainingStatus": "needs_trajectories",
        "harvester": "Automata Seeder",
        "runtimeCapabilities": {
            "browser": True,
            "apiCalls": True,
            "knowledge": True,
            "python": False,
            "humanApprovalForWrites": True,
        },
        "tasks": tasks,
        "successCriteria": "The user confirms the result, cited sources are correct, and sensitive write actions require approval.",
        "updatedAt": timestamp,
    }
    if agent_config:
        await agents_collection.update_one({"agentId": agent_id}, {"$set": update})
        doc = {**agent_config, **update}
    else:
        doc = {"agentId": agent_id, "createdAt": timestamp, "trajectories": [], **update}
        await agents_collection.insert_one(dict(doc))

    await ensure_agent_creation_job(doc)
    web_id = f"default-{agent_id}"
    await agent_webs_collection.update_one(
        {"webId": web_id},
        {
            "$set": {
                "agentId": agent_id,
                "email": email,
                "name": company["name"],
                "baseUrl": website_url,
                "authRequired": False,
                "updatedAt": timestamp,
            },
            "$setOnInsert": {"webId": web_id, "createdAt": timestamp},
        },
        upsert=True,
    )

    for task in tasks:
        await trajectories_collection.update_one(
            {"agentId": agent_id, "prompt": task["prompt"]},
            {
                "$set": {
                    "email": email,
                    "webId": web_id,
                    "taskName": task["name"],
                    "successCriteria": task["successCriteria"],
                    "source": "seed",
                    "status": "needs_harvest",
                    "updatedAt": timestamp,
                },
                "$setOnInsert": {
                    "trajectoryId": str(uuid.uuid4()),
                    "agentId": agent_id,
                    "prompt": task["prompt"],
                    "actions": [],
                    "screenshots": [],
                    "createdAt": timestamp,
                },
            },
            upsert=True,
        )
        await evals_collection.update_one(
            {"email": email, "agentId": agent_id, "prompt": task["prompt"]},
            {
                "$set": {
                    "benchmarkId": f"agent-{agent_id}",
                    "benchmarkName": f"{agent_name} Benchmark",
                    "initialUrl": website_url,
                    "agentName": agent_name,
                    "agentTaskName": task["name"],
                    "successCriteria": task["successCriteria"],
                },
                "$setOnInsert": {
                    "evalId": str(uuid.uuid4()),
                    "email": email,
                    "agentId": agent_id,
                    "prompt": task["prompt"],
                    "createdAt": timestamp,
                },
            },
            upsert=True,
        )
        skill_id = f"{agent_id}:{task['name'].lower().replace(' ', '_')}"
        await capabilities_collection.update_one(
            {"capabilityId": skill_id},
            {
                "$set": {
                    "capabilityKind": "skill",
                    "skillId": skill_id,
                    "agentId": agent_id,
                    "companyId": company["companyId"],
                    "email": email,
                    "name": task["name"],
                    "toolName": f"skill.{task['name'].lower().replace(' ', '_')}",
                    "description": task["prompt"],
                    "whenToUse": task["prompt"],
                    "inputSchema": {"type": "object", "properties": {"instruction": {"type": "string"}}},
                    "sideEffects": "writes" if "Enviar" in task["prompt"] or "preparar" in task["prompt"].lower() else "reads",
                    "riskLevel": "medium",
                    "riskPolicy": "human_approval_for_writes",
                    "runtime": "skill_tool",
                    "status": "draft",
                    "updatedAt": timestamp,
                },
                "$setOnInsert": {"createdAt": timestamp},
            },
            upsert=True,
        )
    return doc


async def rename_generic_tasks(email: str, company_id: str = "") -> dict[str, int]:
    counts = {"agents": 0, "trajectories": 0, "evals": 0, "skills": 0, "onboarding_sessions": 0}
    query: dict[str, Any] = {"email": email}
    if company_id:
        query["companyId"] = company_id

    eval_names_by_id: dict[str, str] = {}
    eval_names_by_prompt: dict[str, str] = {}
    async for eval_doc in evals_collection.find({"email": email}, {"_id": 0}):
        if company_id:
            agent_config = await agents_collection.find_one({"agentId": eval_doc.get("agentId"), "companyId": company_id}, {"_id": 1})
            if not agent_config:
                continue
        prompt = str(eval_doc.get("prompt") or "")
        current_name = str(eval_doc.get("agentTaskName") or "")
        if generic_task_name(current_name):
            current_name = task_name_from_prompt(prompt, 1)
        if eval_doc.get("evalId"):
            eval_names_by_id[str(eval_doc["evalId"])] = current_name or task_name_from_prompt(prompt, 1)
        if prompt:
            eval_names_by_prompt[prompt.strip().lower()] = current_name or task_name_from_prompt(prompt, 1)

    async for agent_config in agents_collection.find(query, {"_id": 0}):
        changed = False
        tasks = []
        for index, task in enumerate(agent_config.get("tasks") or [], start=1):
            next_task = dict(task)
            if generic_task_name(next_task.get("name")):
                next_task["name"] = task_name_from_prompt(str(next_task.get("prompt") or ""), index)
                changed = True
            tasks.append(next_task)
        if changed:
            await agents_collection.update_one({"agentId": agent_config["agentId"]}, {"$set": {"tasks": tasks, "updatedAt": now()}})
            counts["agents"] += 1

    async for trajectory in trajectories_collection.find({"email": email}, {"_id": 0}):
        if company_id:
            agent_config = await agents_collection.find_one({"agentId": trajectory.get("agentId"), "companyId": company_id}, {"_id": 1})
            if not agent_config and trajectory.get("companyId") != company_id:
                continue
        current_name = trajectory.get("taskName") or trajectory.get("name")
        if generic_task_name(current_name):
            prompt = str(trajectory.get("prompt") or trajectory.get("intent") or "").strip()
            eval_id = str(trajectory.get("evalId") or "")
            next_name = eval_names_by_id.get(eval_id) or eval_names_by_prompt.get(prompt.lower()) or task_name_from_prompt(prompt, 1)
            update = {"updatedAt": now()}
            if trajectory.get("taskName") is not None:
                update["taskName"] = next_name
            if trajectory.get("name") is not None:
                update["name"] = next_name
            await trajectories_collection.update_one(
                {"trajectoryId": trajectory["trajectoryId"]},
                {"$set": update},
            )
            counts["trajectories"] += 1

    async for eval_doc in evals_collection.find({"email": email}, {"_id": 0}):
        if company_id:
            agent_config = await agents_collection.find_one({"agentId": eval_doc.get("agentId"), "companyId": company_id}, {"_id": 1})
            if not agent_config:
                continue
        if generic_task_name(eval_doc.get("agentTaskName")):
            await evals_collection.update_one(
                {"evalId": eval_doc["evalId"]},
                {"$set": {"agentTaskName": task_name_from_prompt(str(eval_doc.get("prompt") or ""), 1)}},
            )
            counts["evals"] += 1

    async for skill in capabilities_collection.find({**query, "capabilityKind": "skill"}, {"_id": 0}):
        if not generic_task_name(skill.get("name")):
            continue
        prompt = str(skill.get("description") or skill.get("whenToUse") or "").strip()
        eval_id = str(skill.get("evalId") or "")
        next_name = eval_names_by_id.get(eval_id) or eval_names_by_prompt.get(prompt.lower()) or task_name_from_prompt(prompt, 1)
        await capabilities_collection.update_one(
            {"capabilityId": skill["capabilityId"]},
            {"$set": {"name": next_name, "updatedAt": now()}},
        )
        counts["skills"] += 1

    async for session in onboarding_sessions_collection.find(query, {"_id": 0}):
        draft = dict(session.get("draft") or {})
        changed = False
        tasks = []
        for index, task in enumerate(draft.get("tasks") or [], start=1):
            next_task = dict(task)
            if generic_task_name(next_task.get("name")):
                next_task["name"] = task_name_from_prompt(str(next_task.get("prompt") or ""), index)
                changed = True
            tasks.append(next_task)
        if changed:
            draft["tasks"] = tasks
            await onboarding_sessions_collection.update_one({"sessionId": session["sessionId"]}, {"$set": {"draft": draft, "updatedAt": now()}})
            counts["onboarding_sessions"] += 1
    return counts


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Automata Cloud local connectors from Studio-style env vars.")
    parser.add_argument("--email", default=env("AUTOMATA_SEED_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--company", default=env("AUTOMATA_SEED_COMPANY", DEFAULT_COMPANY))
    parser.add_argument("--test", action="store_true", help="Apply connector test status after seeding.")
    parser.add_argument("--seed-agent-tasks", action="store_true", help="Seed/update the Celeris demo agent, trajectories and benchmark tasks with descriptive names.")
    parser.add_argument("--rename-generic-tasks", action="store_true", help="Rename existing Task 1/Task 2 style tasks for this email/company.")
    args = parser.parse_args()

    await ensure_indexes()
    company = await ensure_company(args.email, args.company)
    specs = connector_specs(args.email, company["companyId"])

    print(f"company={company['name']} companyId={company['companyId']} email={args.email}")
    for spec in specs:
        doc = await upsert_connector(args.email, company["companyId"], spec, args.test)
        required = CONNECTOR_TOOLKIT_DEFAULTS.get(spec["type"], CONNECTOR_TOOLKIT_DEFAULTS["api"]).get("authFields", [])
        missing = [field for field in required if not str(spec["config"].get(field) or "").strip()]
        missing_text = ",".join(missing) if missing else "-"
        print(f"{doc['name']}: status={doc['status']} missing={missing_text}")

    if args.seed_agent_tasks:
        agent_config = await upsert_celeris_agent(args.email, company)
        print(f"agent={agent_config['name']} agentId={agent_config['agentId']} tasks={len(CELERIS_TASKS)}")

    if args.rename_generic_tasks:
        counts = await rename_generic_tasks(args.email, company["companyId"])
        print(
            "renamed="
            f"agents:{counts['agents']},"
            f"trajectories:{counts['trajectories']},"
            f"evals:{counts['evals']},"
            f"skills:{counts['skills']},"
            f"onboarding_sessions:{counts['onboarding_sessions']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
