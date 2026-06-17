#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

from app.database import harvester_runs_collection  # noqa: E402
from app.routes.agent_creation import _run_harvester_background  # noqa: E402


async def main() -> int:
    while True:
        run = await harvester_runs_collection.find_one_and_update(
            {"runKind": "agent_creation", "status": "queued"},
            {"$set": {"status": "claimed"}},
            sort=[("createdAt", 1)],
        )
        if not run:
            await asyncio.sleep(2)
            continue
        await _run_harvester_background(
            agent_id=str(run.get("agentId") or ""),
            job_id=str(run.get("jobId") or ""),
            harvester_run_id=str(run.get("harvesterRunId") or ""),
            harvester_name=str(run.get("harvesterType") or "autoppia_harvester"),
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
