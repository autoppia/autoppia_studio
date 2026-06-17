from __future__ import annotations

import asyncio
import logging

from app.database import ensure_indexes
from app.services.workers import job_worker_loop, notification_cleanup_worker_loop, scheduled_work_worker_loop


logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await ensure_indexes()
    await asyncio.gather(
        job_worker_loop(),
        scheduled_work_worker_loop(),
        notification_cleanup_worker_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
