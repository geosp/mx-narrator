"""Temporal worker entrypoint for the `gpu-tasks` task queue. Run via
`uv run python -m worker.main` (see `deploy/gpu-worker/Dockerfile`'s CMD)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from worker.activities import align_captions, finalize_srt, mark_render_job, mark_video_job, synthesize, transcribe
from worker.workflows import AudioGenerationWorkflow, ReviseCaptionsWorkflow, VideoProductionWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")
TASK_QUEUE = "gpu-tasks"


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    logger.info("connected to temporal at %s", TEMPORAL_ADDRESS)

    # max_workers=1 for the sync-activity thread pool matches
    # max_concurrent_activities=1 below — one GPU, one render at a time per worker
    # process (design.md; mx_narrator's own established constraint, see batch.py).
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[AudioGenerationWorkflow, VideoProductionWorkflow, ReviseCaptionsWorkflow],
            activities=[synthesize, mark_render_job, transcribe, mark_video_job, finalize_srt, align_captions],
            activity_executor=activity_executor,
            max_concurrent_activities=1,
        )
        logger.info("worker polling task queue %r", TASK_QUEUE)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
