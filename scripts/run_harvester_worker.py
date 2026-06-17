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

from app.services.queue import claim_next_job, complete_job, fail_job  # noqa: E402
from app.services.workers import execute_job  # noqa: E402


async def main() -> int:
    while True:
        job = await claim_next_job(job_types=["agent_harvest"])
        if not job:
            await asyncio.sleep(2)
            continue
        try:
            result = await execute_job(job)
            await complete_job(str(job.get("jobId") or ""), result)
        except Exception as exc:
            await fail_job(job, str(exc))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
