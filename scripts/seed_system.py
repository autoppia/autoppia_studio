#!/usr/bin/env python3
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

from app.database import db, ensure_indexes  # noqa: E402
from seed_connectors import (  # noqa: E402
    DEFAULT_COMPANY,
    DEFAULT_EMAIL,
    connector_specs,
    ensure_company,
    publish_connector_tools,
    rename_generic_tasks,
    upsert_celeris_agent,
    upsert_connector,
)


PRODUCT_COLLECTIONS = [
    "agents",
    "agent_webs",
    "companies",
    "connectors",
    "credentials",
    "knowledge_documents",
    "onboarding_sessions",
    "evals",
    "eval_runs",
    "agent_creation_jobs",
    "trajectories",
    "capabilities",
    "tools",
    "harvester_runs",
    "tool_runs",
    "trajectory_runs",
    "capability_grants",
]

USER_COLLECTIONS = [
    "users",
    "sessions",
    "profiles",
    "api_keys",
    "skills",
]


async def reset_collections(drop_users: bool) -> list[str]:
    names = PRODUCT_COLLECTIONS + (USER_COLLECTIONS if drop_users else [])
    dropped: list[str] = []
    for name in names:
        if name in await db.list_collection_names():
            await db[name].drop()
            dropped.append(name)
    return dropped


async def seed(email: str, company_name: str, run_tests: bool) -> dict[str, object]:
    await ensure_indexes()
    company = await ensure_company(email, company_name)
    connectors = []
    for spec in connector_specs(email, company["companyId"]):
        connectors.append(await upsert_connector(email, company["companyId"], spec, run_tests))
    published_tools = await publish_connector_tools(company["companyId"])
    agent = await upsert_celeris_agent(email, company)
    renamed = await rename_generic_tasks(email, company["companyId"])
    return {"company": company, "connectors": connectors, "agent": agent, "renamed": renamed, "published_tools": published_tools}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Reset and seed the local Automata Agent system state.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--company", default=DEFAULT_COMPANY)
    parser.add_argument("--reset", action="store_true", help="Drop product-state collections before seeding.")
    parser.add_argument("--drop-users", action="store_true", help="Also drop users, sessions, profiles, API keys and legacy skills.")
    parser.add_argument("--test", action="store_true", help="Mark seeded connectors using simple credential checks.")
    args = parser.parse_args()

    if args.reset:
        dropped = await reset_collections(args.drop_users)
        print(f"reset_collections={','.join(dropped) if dropped else '-'}")

    result = await seed(args.email, args.company, args.test)
    connector_summary = ",".join(f"{item['name']}:{item['status']}" for item in result["connectors"])
    agent = result["agent"]
    print(f"company={result['company']['name']} companyId={result['company']['companyId']}")
    print(f"connectors={connector_summary}")
    print(f"tools={result['published_tools']}")
    print(f"agent={agent['name']} agentId={agent['agentId']} tasks={len(agent.get('tasks') or [])}")
    print(f"renamed={result['renamed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
