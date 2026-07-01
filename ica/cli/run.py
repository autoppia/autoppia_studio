from __future__ import annotations

import argparse
import asyncio
import json

from ica.company_harvesters.runners import CompanyHarvesterEngineIcaRunner
from ica.demo_companies.loader import load_demo_project
from ica.demo_companies.materializer import materialize_project
from ica.evaluation.benchmark import evaluate_project_company_harvest


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run an Infinite Company Arena benchmark evaluation.")
    parser.add_argument("--company", default="autoclaims", help="Demo company id under demo_companies/.")
    parser.add_argument("--mode", default="all_sources", help="Benchmark mode/source combination.")
    parser.add_argument("--harvester", default="agentic", help="CompanyHarvester engine name: agentic, claude_code, codex, local_heuristic.")
    parser.add_argument("--email", default="ica-benchmark@autoppia.com")
    parser.add_argument("--company-id", default="", help="Evaluation company id. Defaults to ica-{company}.")
    parser.add_argument("--base-url", default="", help="Override demo company base URL.")
    parser.add_argument("--inventory-only", action="store_true", help="Print materialized company input without running the harvester.")
    args = parser.parse_args()

    project = load_demo_project(args.company)
    if args.inventory_only:
        materialized = materialize_project(project, base_url=args.base_url, mode=args.mode)
        print(json.dumps(materialized.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    result = await evaluate_project_company_harvest(
        project,
        email=args.email,
        company_id=args.company_id or f"ica-{project.projectId}",
        base_url=args.base_url,
        mode=args.mode,
        runner=CompanyHarvesterEngineIcaRunner(args.harvester),
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

