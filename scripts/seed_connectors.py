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

from app.database import companies_collection, connectors_collection, ensure_indexes  # noqa: E402
from app.routes.connectors import CONNECTOR_TOOLKIT_DEFAULTS  # noqa: E402


DEFAULT_EMAIL = "demo@autoppia.com"
DEFAULT_COMPANY = "Celeris"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def compact_config(config: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in config.items() if value}


def connector_specs(email: str, company_id: str) -> list[dict[str, Any]]:
    gmail_email = env("GMAIL_USER_EMAIL") or env("SMTP_EMAIL")
    return [
        {
            "name": "Gmail",
            "type": "gmail",
            "category": "email",
            "description": "Gmail connector seeded from Studio-style OAuth env vars.",
            "config": compact_config({
                "clientId": env("GMAIL_CLIENT_ID"),
                "clientSecret": env("GMAIL_CLIENT_SECRET"),
                "refreshToken": env("GMAIL_REFRESH_TOKEN"),
                "accessToken": env("GMAIL_ACCESS_TOKEN"),
                "scopes": env("GMAIL_SCOPES", "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send"),
                "userEmail": gmail_email,
                "apiVersion": env("GMAIL_API_VERSION", "v1"),
                "defaultFrom": gmail_email,
                "signature": env("GMAIL_SIGNATURE", "Celeris"),
            }),
        },
        {
            "name": "SMTP",
            "type": "api",
            "category": "email",
            "description": "SMTP connector seeded from Studio SMTP env vars.",
            "config": compact_config({
                "apiKey": env("SMTP_PASSWORD"),
                "baseUrl": env("SMTP_SERVER"),
                "openApiUrl": "",
                "port": env("SMTP_PORT"),
                "email": env("SMTP_EMAIL"),
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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Automata Cloud local connectors from Studio-style env vars.")
    parser.add_argument("--email", default=env("AUTOMATA_SEED_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--company", default=env("AUTOMATA_SEED_COMPANY", DEFAULT_COMPANY))
    parser.add_argument("--test", action="store_true", help="Apply connector test status after seeding.")
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

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
