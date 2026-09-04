"""Temporal worker entrypoint for the `cpu-tasks` task queue — lightweight metadata
generation, separate from `gpu-tasks` so it never queues behind in-flight GPU
synthesis (design.md). Run via `uv run python -m worker.cpu_main` (see
`deploy/docker-compose.yml`'s `cpu-worker` service)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from worker.activities import (
    approve_metadata,
    correctness_check,
    generate_metadata,
    render_video,
    reset_manually_uploaded,
    save_metadata_draft,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")
TASK_QUEUE = "cpu-tasks"


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    logger.info("connected to temporal at %s", TEMPORAL_ADDRESS)

    # generate_metadata is async/I/O-bound (design.md) — no cap needed. correctness_check,
    # render_video, save_metadata_draft, approve_metadata, and reset_manually_uploaded
    # are sync/CPU-bound — Temporal's Python SDK requires an activity_executor for any
    # sync activity, same reason gpu-worker has one.
    with concurrent.futures.ThreadPoolExecutor() as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[],
            activities=[
                generate_metadata,
                correctness_check,
                render_video,
                save_metadata_draft,
                approve_metadata,
                reset_manually_uploaded,
            ],
            activity_executor=activity_executor,
        )
        logger.info("worker polling task queue %r", TASK_QUEUE)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
