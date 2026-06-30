#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

from app.database import ensure_indexes  # noqa: E402
from app.services.infinite_company_arena import evaluate_project_company_harvest, load_demo_project, materialize_project, seed_company_harvester_from_project  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an ICA demo project into CompanyHarvester benchmark inputs.")
    parser.add_argument("--project", default="autoclaims", help="Demo project id under demo_projects/.")
    parser.add_argument("--email", default="ica-benchmark@autoppia.com")
    parser.add_argument("--company-id", default="ica-autoclaims")
    parser.add_argument("--base-url", default="", help="Override project base URL, e.g. http://127.0.0.1:8123")
    parser.add_argument("--mode", choices=["api_only", "web_only", "hybrid"], default=None, help="Optional ICA benchmark mode.")
    parser.add_argument("--inventory-only", action="store_true", help="Print materialized project without writing to Mongo.")
    parser.add_argument("--evaluate", action="store_true", help="Run CompanyHarvester and print an ICA evaluation result.")
    parser.add_argument("--no-process", action="store_true", help="Create intake/run but do not process CompanyHarvester.")
    args = parser.parse_args()

    project = load_demo_project(args.project)
    materialized = materialize_project(project, base_url=args.base_url, mode=args.mode)
    if args.inventory_only:
        print(json.dumps(materialized.model_dump(), ensure_ascii=False, indent=2))
        return

    await ensure_indexes()
    if args.evaluate:
        result = await evaluate_project_company_harvest(
            project,
            email=args.email,
            company_id=args.company_id,
            base_url=args.base_url,
            mode=args.mode,
            process=not args.no_process,
        )
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        return

    result = await seed_company_harvester_from_project(
        project,
        email=args.email,
        company_id=args.company_id,
        base_url=args.base_url,
        mode=args.mode,
        process=not args.no_process,
    )
    run = result["run"]
    print(json.dumps({
        "projectId": project.projectId,
        "intakeId": result["intake"].get("intakeId"),
        "runId": run.get("runId"),
        "status": run.get("status"),
        "currentStep": run.get("currentStep"),
        "normalSummary": run.get("normalSummary"),
        "nextAction": run.get("nextAction"),
        "expectedHarvest": result["expectedHarvest"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
