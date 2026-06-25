#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

from app.database import connectors_collection, ensure_indexes  # noqa: E402
from app.services.connector_benchmarks import (  # noqa: E402
    audit_connector_benchmark_matrix,
    connector_benchmark_catalog,
    get_connector_benchmark,
    harvest_and_smoke_connector_benchmark,
    run_connector_runtime_smoke,
    seed_connector_benchmark,
)


DEFAULT_EMAIL = os.getenv("AUTOMATA_BENCHMARK_EMAIL", "demo@autoppia.com")
DEFAULT_COMPANY_ID = os.getenv("AUTOMATA_BENCHMARK_COMPANY_ID", "deae345c-8e98-42ec-a517-267b47f1488a")


async def find_connector(company_id: str, connector_id: str, benchmark_key: str) -> dict:
    if connector_id:
        connector = await connectors_collection.find_one({"connectorId": connector_id, "companyId": company_id}, {"_id": 0})
        if not connector:
            raise RuntimeError(f"Connector {connector_id!r} not found for company {company_id!r}.")
        return connector
    preferred_types = list(get_connector_benchmark(benchmark_key).get("connectorTypes") or [])
    for connector_type in preferred_types:
        connector = await connectors_collection.find_one({"companyId": company_id, "type": connector_type}, {"_id": 0})
        if connector:
            return connector
    raise RuntimeError(f"No connector found for benchmark {benchmark_key!r} in company {company_id!r}. Pass --connector-id.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed and smoke-test connector runtime benchmarks.")
    parser.add_argument("--catalog", action="store_true", help="Print available connector benchmark definitions.")
    parser.add_argument("--audit-matrix", action="store_true", help="Run connector benchmark matrix for every catalog connector in the company.")
    parser.add_argument("--benchmark", default="email", help="Connector benchmark key. Default: email.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    parser.add_argument("--connector-id", default="")
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--seed", action="store_true", help="Create/update benchmark and benchmark_tasks records.")
    parser.add_argument("--no-publish-tools", action="store_true", help="Do not publish toolkit tools while seeding.")
    parser.add_argument("--runtime-smoke", action="store_true", help="Run all seeded tasks against AgentRuntime /step.")
    parser.add_argument("--harvest-smoke", action="store_true", help="Run without-skill smoke, harvest approved skills, then run with-skill smoke.")
    parser.add_argument("--no-approve-skills", action="store_true", help="Harvest trajectories without approving skills for replay.")
    parser.add_argument("--task-key", action="append", default=[], help="Limit runtime smoke to a task key. May be repeated.")
    args = parser.parse_args()

    await ensure_indexes()

    if args.catalog:
        print(json.dumps({"benchmarks": connector_benchmark_catalog()}, ensure_ascii=False, indent=2))
        return

    if args.audit_matrix:
        report = await audit_connector_benchmark_matrix(email=args.email, company_id=args.company_id, publish_tools=not args.no_publish_tools)
        print(json.dumps({"connectorAudit": report}, ensure_ascii=False, indent=2))
        return

    connector = await find_connector(args.company_id, args.connector_id, args.benchmark)
    seeded = None
    if args.seed or args.runtime_smoke or args.harvest_smoke:
        seeded = await seed_connector_benchmark(
            benchmark_key=args.benchmark,
            email=args.email,
            company_id=args.company_id,
            connector_id=connector["connectorId"],
            agent_id=args.agent_id,
            publish_tools=not args.no_publish_tools,
        )
        print(
            json.dumps(
                {
                    "seeded": {
                        "benchmarkId": seeded["benchmark"]["benchmarkId"],
                        "agentId": seeded["agent"]["agentId"],
                        "connectorId": connector["connectorId"],
                        "tasks": [task["taskId"] for task in seeded["tasks"]],
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if args.runtime_smoke:
        assert seeded is not None
        report = await run_connector_runtime_smoke(
            benchmark_id=seeded["benchmark"]["benchmarkId"],
            agent_id=seeded["agent"]["agentId"],
            task_keys=args.task_key or None,
        )
        print(json.dumps({"runtimeSmoke": report}, ensure_ascii=False, indent=2))

    if args.harvest_smoke:
        assert seeded is not None
        report = await harvest_and_smoke_connector_benchmark(
            benchmark_id=seeded["benchmark"]["benchmarkId"],
            agent_id=seeded["agent"]["agentId"],
            task_keys=args.task_key or None,
            approve_skills=not args.no_approve_skills,
        )
        print(json.dumps({"harvestSmoke": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
