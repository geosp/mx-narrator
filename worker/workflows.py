"""`AudioGenerationWorkflow` — see specs/workflow/audio-generation/spec.md."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

from worker.types import (
    AlignCaptionsInput,
    ApproveMetadataInput,
    AudioGenerationWorkflowInput,
    CorrectnessCheckInput,
    GenerateMetadataInput,
    RenderVideoInput,
    ReviseCaptionsWorkflowInput,
    SaveMetadataDraftInput,
    SynthesizeInput,
    TranscribeInput,
    VideoProductionWorkflowInput,
)

with workflow.unsafe.imports_passed_through():
    from worker.activities import (
        align_captions,
        approve_metadata,
        correctness_check,
        finalize_srt,
        generate_metadata,
        mark_render_job,
        mark_video_job,
        render_video,
        reset_manually_uploaded,
        save_metadata_draft,
        synthesize,
        transcribe,
    )

# Long syntheses can legitimately run tens of minutes (RFC ballpark: 20-30 min of
# audio); the heartbeat (activities.py, every 15s) is what actually detects a stuck
# worker, so this timeout only needs to be generous, not tight.
SYNTHESIZE_START_TO_CLOSE_TIMEOUT = timedelta(hours=2)
SYNTHESIZE_HEARTBEAT_TIMEOUT = timedelta(seconds=45)
MARK_RENDER_JOB_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)
# A bad engine name, a malformed script, or a corrupt voice file fails the same way
# every time — retrying blindly (Temporal's default is unlimited retries) would just
# leave `render_jobs` stuck at "rendering" for up to the full start_to_close_timeout
# instead of surfacing the failure (spec.md: "Synthesis failures are recorded, not
# silently lost"). One attempt, no retry; transient infra hiccups are Temporal's own
# worker-restart/task-queue durability, not activity-level retry.
SYNTHESIZE_RETRY_POLICY = RetryPolicy(maximum_attempts=1)
# Small, idempotent Mongo/file writes ("mark_*", finalize_srt, save/approve
# metadata, reset_manually_uploaded) — cheap and safe to retry a handful of
# times against a transient Mongo hiccup, but must not retry forever if the
# failure is actually deterministic (a real bug, a bad query) — exactly the
# class of incident that bit this session three times already before this
# hardening pass.
MONGO_WRITE_RETRY_POLICY = RetryPolicy(maximum_attempts=5)


@workflow.defn
class AudioGenerationWorkflow:
    @workflow.run
    async def run(self, input: AudioGenerationWorkflowInput) -> None:
        await workflow.execute_activity(
            mark_render_job,
            args=[input.render_job_id, "rendering"],
            start_to_close_timeout=MARK_RENDER_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )

        try:
            result = await workflow.execute_activity(
                synthesize,
                SynthesizeInput(
                    render_job_id=input.render_job_id,
                    unit_id=input.unit_id,
                    lang=input.lang,
                    script_text=input.script_text,
                    id3=input.id3,
                    engine_name=input.engine_name,
                    speed=input.speed,
                    exaggeration=input.exaggeration,
                    cfg_weight=input.cfg_weight,
                    seed=input.seed,
                    series_album=input.series_album,
                    title=input.title,
                    voice_id=input.voice_id,
                ),
                start_to_close_timeout=SYNTHESIZE_START_TO_CLOSE_TIMEOUT,
                heartbeat_timeout=SYNTHESIZE_HEARTBEAT_TIMEOUT,
                retry_policy=SYNTHESIZE_RETRY_POLICY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                mark_render_job,
                args=[input.render_job_id, "failed", "", str(exc.cause or exc)],
                start_to_close_timeout=MARK_RENDER_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            return

        await workflow.execute_activity(
            mark_render_job,
            args=[input.render_job_id, "complete", result.audio_path, ""],
            start_to_close_timeout=MARK_RENDER_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )


TRANSCRIBE_START_TO_CLOSE_TIMEOUT = timedelta(hours=1)
TRANSCRIBE_HEARTBEAT_TIMEOUT = timedelta(seconds=45)
TRANSCRIBE_RETRY_POLICY = RetryPolicy(maximum_attempts=2)  # one CUDA-memory-pressure retry, not unlimited (design.md)
CORRECTNESS_CHECK_START_TO_CLOSE_TIMEOUT = timedelta(minutes=5)
CORRECTNESS_CHECK_RETRY_POLICY = RetryPolicy(maximum_attempts=1)  # deterministic given its inputs
MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)
FINALIZE_SRT_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)
# Forced alignment of the already-approved caption text (worker/align.py) — a real
# episode aligns in ~13s warm; generous headroom for a cold model download on the
# very first call. Best-effort by design (align_captions_fn catches its own
# exceptions and returns aligned=False rather than raising), so one retry here is
# only for genuine Temporal/infra hiccups (a lost worker mid-call), not for content
# problems — those already degrade gracefully inside the Activity itself.
ALIGN_CAPTIONS_START_TO_CLOSE_TIMEOUT = timedelta(minutes=5)
ALIGN_CAPTIONS_RETRY_POLICY = RetryPolicy(maximum_attempts=2)
# Muxing image+audio+subtitle is fast (no motion-video encoding), but generous
# rather than tight for a long episode, same philosophy as SYNTHESIZE's timeout.
RENDER_VIDEO_START_TO_CLOSE_TIMEOUT = timedelta(minutes=30)
RENDER_VIDEO_HEARTBEAT_TIMEOUT = timedelta(seconds=45)
RENDER_VIDEO_RETRY_POLICY = RetryPolicy(maximum_attempts=1)  # ffmpeg failures are deterministic given the same inputs
GENERATE_METADATA_START_TO_CLOSE_TIMEOUT = timedelta(minutes=5)
# generate_metadata's real-world failure mode, confirmed via journalctl on the
# deployment host: Ollama's model runner (this host's AMD iGPU, via ROCm) hits
# an intermittent "HW Exception ... GPU Hang" seconds after a fresh runner
# starts, dies, and the very next auto-relaunched runner often hangs again
# within seconds too — a persistent misconfiguration (bad model name, invalid
# API key) or a schema-validation failure on the LLM's own output is still
# deterministic and shouldn't retry indefinitely, but the GPU-hang case is
# exactly the opposite: it needs real wall-clock time to clear, not more
# attempts fired seconds apart. Widened well past a "genuinely transient
# network hiccup" one-retry policy to actually span that recovery window —
# shared by both VideoProductionWorkflow and ReviseCaptionsWorkflow.
GENERATE_METADATA_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=5,
)
SAVE_METADATA_DRAFT_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)
APPROVE_METADATA_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)


@workflow.defn
class VideoProductionWorkflow:
    def __init__(self) -> None:
        self._mismatch_acknowledged = False
        self._srt_approved = False
        self._approved_srt_text: str | None = None
        self._metadata_approved = False
        self._approved_title: str = ""
        self._approved_description: str = ""
        self._approved_tags: list[str] = []

    @workflow.signal
    async def acknowledge_mismatch(self) -> None:
        self._mismatch_acknowledged = True

    @workflow.signal
    async def approve_srt(self, srt_text: str) -> None:
        self._approved_srt_text = srt_text
        self._srt_approved = True

    @workflow.signal
    async def approve_metadata(self, title: str, description: str, tags: list[str]) -> None:
        self._approved_title = title
        self._approved_description = description
        self._approved_tags = tags
        self._metadata_approved = True

    @workflow.run
    async def run(self, input: VideoProductionWorkflowInput) -> None:
        # No workflow-level execution timeout — deliberate, unlike every other
        # timeout in this codebase (all Activity-scoped). This is the first workflow
        # that legitimately sits idle for human review timescales, not a bug.
        #
        # transcribe/correctness_check are unattended system work, same as
        # render_video/generate_metadata below — a failure here (confirmed for real:
        # a CUDA OOM in transcribe after both retry attempts) must be recorded, not
        # leave video_jobs.status stuck at "transcribing" forever with no error while
        # the workflow itself has already died.
        try:
            transcript = await workflow.execute_activity(
                transcribe,
                TranscribeInput(video_job_id=input.video_job_id, audio_path=input.audio_path, lang=input.lang),
                start_to_close_timeout=TRANSCRIBE_START_TO_CLOSE_TIMEOUT,
                heartbeat_timeout=TRANSCRIBE_HEARTBEAT_TIMEOUT,
                retry_policy=TRANSCRIBE_RETRY_POLICY,
            )

            # srt_path is recorded here, right after transcription — matches RFC's
            # diagram ("write srt_path" immediately after transcribe) and is what
            # makes GET /video_jobs/{id}/srt able to pre-fill the review textarea
            # before approval, not just after finalize_srt writes the approved
            # version over it.
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "checking_correctness", None, transcript.srt_path],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            check = await workflow.execute_activity(
                correctness_check,
                CorrectnessCheckInput(script_text=input.script_text, lang=input.lang, words=transcript.words),
                task_queue="cpu-tasks",  # pure CPU text processing — design.md
                start_to_close_timeout=CORRECTNESS_CHECK_START_TO_CLOSE_TIMEOUT,
                retry_policy=CORRECTNESS_CHECK_RETRY_POLICY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "failed", None, "", "", str(exc.cause or exc)],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            return

        if check.status == "mismatch":
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "mismatch_needs_review", check.mismatches],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            await workflow.wait_condition(lambda: self._mismatch_acknowledged)

        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "srt_review_pending"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.wait_condition(lambda: self._srt_approved)

        await workflow.execute_activity(
            finalize_srt,
            args=[input.video_job_id, transcript.srt_path, self._approved_srt_text],
            start_to_close_timeout=FINALIZE_SRT_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.execute_activity(
            align_captions,
            AlignCaptionsInput(
                video_job_id=input.video_job_id,
                audio_path=input.audio_path,
                lang=input.lang,
                srt_path=transcript.srt_path,
            ),
            start_to_close_timeout=ALIGN_CAPTIONS_START_TO_CLOSE_TIMEOUT,
            retry_policy=ALIGN_CAPTIONS_RETRY_POLICY,
        )
        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "srt_approved"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )

        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "rendering"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )

        # Unlike the human-review waits above, everything from here on is
        # unattended system work (ffmpeg, an LLM call) — a failure here must be
        # recorded, not leave the job silently stuck at "rendering" forever
        # (the exact gap AudioGenerationWorkflow already avoids for `synthesize`).
        try:
            video = await workflow.execute_activity(
                render_video,
                RenderVideoInput(
                    video_job_id=input.video_job_id,
                    image_path=input.image_path,
                    audio_path=input.audio_path,
                    srt_path=transcript.srt_path,
                ),
                task_queue="cpu-tasks",  # ffmpeg mux, no GPU involved — design.md
                start_to_close_timeout=RENDER_VIDEO_START_TO_CLOSE_TIMEOUT,
                heartbeat_timeout=RENDER_VIDEO_HEARTBEAT_TIMEOUT,
                retry_policy=RENDER_VIDEO_RETRY_POLICY,
            )
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "generating_metadata", None, "", video.video_path],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )

            metadata_result = await workflow.execute_activity(
                generate_metadata,
                GenerateMetadataInput(render_job_id=input.render_job_id),
                task_queue="cpu-tasks",
                start_to_close_timeout=GENERATE_METADATA_START_TO_CLOSE_TIMEOUT,
                retry_policy=GENERATE_METADATA_RETRY_POLICY,
            )
            await workflow.execute_activity(
                save_metadata_draft,
                SaveMetadataDraftInput(
                    video_job_id=input.video_job_id,
                    render_job_id=input.render_job_id,
                    metadata=metadata_result.metadata,
                ),
                task_queue="cpu-tasks",
                start_to_close_timeout=SAVE_METADATA_DRAFT_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "failed", None, "", "", str(exc.cause or exc)],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            return

        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "metadata_review_pending"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.wait_condition(lambda: self._metadata_approved)

        await workflow.execute_activity(
            approve_metadata,
            ApproveMetadataInput(
                video_job_id=input.video_job_id,
                title=self._approved_title,
                description=self._approved_description,
                tags=self._approved_tags,
            ),
            task_queue="cpu-tasks",
            start_to_close_timeout=APPROVE_METADATA_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "ready_for_manual_upload"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )


RESET_MANUALLY_UPLOADED_START_TO_CLOSE_TIMEOUT = timedelta(seconds=30)


@workflow.defn
class ReviseCaptionsWorkflow:
    """Started after captions have already been approved once (video_jobs at
    metadata_review_pending, ready_for_manual_upload, or failed) — re-renders the
    video against corrected caption text. Deliberately skips transcription and the
    correctness check (the human's edit *is* the correction now) and, when
    metadata was already approved, skips regenerating it too (caption wording
    doesn't change an LLM-generated title/description drawn from the script).

    Needs its own `approve_metadata` signal + wait — Temporal signals are scoped
    to one running execution, so this can't reuse VideoProductionWorkflow's. This
    duplicates that small signal + tail block rather than extracting a shared
    base class: cross-class signal-handler inheritance is unconfirmed in this
    codebase's temporalio version, and VideoProductionWorkflow is a real,
    currently-in-use workflow not worth risking a refactor of. Both copies call
    the exact same unchanged activities, so they can't drift on *what* happens,
    only orchestration order — easy to keep in sync by inspection (see
    design.md's Decisions in the archived `revise-approved-captions` change)."""

    def __init__(self) -> None:
        self._metadata_approved = False
        self._approved_title: str = ""
        self._approved_description: str = ""
        self._approved_tags: list[str] = []

    @workflow.signal
    async def approve_metadata(self, title: str, description: str, tags: list[str]) -> None:
        self._approved_title = title
        self._approved_description = description
        self._approved_tags = tags
        self._metadata_approved = True

    @workflow.run
    async def run(self, input: ReviseCaptionsWorkflowInput) -> None:
        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "rendering"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.execute_activity(
            finalize_srt,
            args=[input.video_job_id, input.srt_path, input.srt_text],
            start_to_close_timeout=FINALIZE_SRT_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.execute_activity(
            align_captions,
            AlignCaptionsInput(
                video_job_id=input.video_job_id,
                audio_path=input.audio_path,
                lang=input.lang,
                srt_path=input.srt_path,
            ),
            start_to_close_timeout=ALIGN_CAPTIONS_START_TO_CLOSE_TIMEOUT,
            retry_policy=ALIGN_CAPTIONS_RETRY_POLICY,
        )

        try:
            video = await workflow.execute_activity(
                render_video,
                RenderVideoInput(
                    video_job_id=input.video_job_id,
                    image_path=input.image_path,
                    audio_path=input.audio_path,
                    srt_path=input.srt_path,
                ),
                task_queue="cpu-tasks",
                start_to_close_timeout=RENDER_VIDEO_START_TO_CLOSE_TIMEOUT,
                heartbeat_timeout=RENDER_VIDEO_HEARTBEAT_TIMEOUT,
                retry_policy=RENDER_VIDEO_RETRY_POLICY,
            )
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "generating_metadata", None, "", video.video_path],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )

            if input.metadata_already_approved:
                if input.metadata is not None:
                    # Set only by the unified "revise-all" endpoint (metadata
                    # edited in the same submit as captions/image) — writes it
                    # here via the same Activity approve_metadata's signal
                    # handler already uses, rather than the API layer
                    # duplicating that write.
                    await workflow.execute_activity(
                        approve_metadata,
                        ApproveMetadataInput(
                            video_job_id=input.video_job_id,
                            title=input.metadata.title,
                            description=input.metadata.description,
                            tags=input.metadata.tags,
                        ),
                        task_queue="cpu-tasks",
                        start_to_close_timeout=APPROVE_METADATA_START_TO_CLOSE_TIMEOUT,
                        retry_policy=MONGO_WRITE_RETRY_POLICY,
                    )
                await workflow.execute_activity(
                    reset_manually_uploaded,
                    input.video_job_id,
                    task_queue="cpu-tasks",
                    start_to_close_timeout=RESET_MANUALLY_UPLOADED_START_TO_CLOSE_TIMEOUT,
                    retry_policy=MONGO_WRITE_RETRY_POLICY,
                )
                await workflow.execute_activity(
                    mark_video_job,
                    args=[input.video_job_id, "ready_for_manual_upload"],
                    start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                    retry_policy=MONGO_WRITE_RETRY_POLICY,
                )
                return

            metadata_result = await workflow.execute_activity(
                generate_metadata,
                GenerateMetadataInput(render_job_id=input.render_job_id),
                task_queue="cpu-tasks",
                start_to_close_timeout=GENERATE_METADATA_START_TO_CLOSE_TIMEOUT,
                retry_policy=GENERATE_METADATA_RETRY_POLICY,
            )
            await workflow.execute_activity(
                save_metadata_draft,
                SaveMetadataDraftInput(
                    video_job_id=input.video_job_id,
                    render_job_id=input.render_job_id,
                    metadata=metadata_result.metadata,
                ),
                task_queue="cpu-tasks",
                start_to_close_timeout=SAVE_METADATA_DRAFT_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                mark_video_job,
                args=[input.video_job_id, "failed", None, "", "", str(exc.cause or exc)],
                start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
                retry_policy=MONGO_WRITE_RETRY_POLICY,
            )
            return

        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "metadata_review_pending"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.wait_condition(lambda: self._metadata_approved)

        await workflow.execute_activity(
            approve_metadata,
            ApproveMetadataInput(
                video_job_id=input.video_job_id,
                title=self._approved_title,
                description=self._approved_description,
                tags=self._approved_tags,
            ),
            task_queue="cpu-tasks",
            start_to_close_timeout=APPROVE_METADATA_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
        await workflow.execute_activity(
            mark_video_job,
            args=[input.video_job_id, "ready_for_manual_upload"],
            start_to_close_timeout=MARK_VIDEO_JOB_START_TO_CLOSE_TIMEOUT,
            retry_policy=MONGO_WRITE_RETRY_POLICY,
        )
