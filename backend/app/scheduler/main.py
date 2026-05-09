"""Scheduler entry point — run with: make run-scheduler

Starts APScheduler 4 with SQLAlchemy data store (Postgres) and registers
all recurring jobs. Runs until Ctrl-C.

Leave this running in a terminal tab while doing local development.
Jobs fire on their cron/interval schedule regardless of whether the
FastAPI server is running.
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from app.core.logging import configure_logging

configure_logging()
log = structlog.get_logger(__name__)


async def main() -> None:
    from app.scheduler.runner import get_scheduler, register_jobs

    scheduler = await get_scheduler()
    await register_jobs(scheduler)

    log.info("scheduler_starting", job_count=len(await scheduler.get_jobs()))

    # Graceful shutdown on SIGINT / SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async with scheduler:
        log.info("scheduler_running", hint="Ctrl-C to stop")
        await stop_event.wait()

    log.info("scheduler_stopped")


if __name__ == "__main__":
    asyncio.run(main())
