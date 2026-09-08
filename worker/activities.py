"""Temporal Activities for AudioGenerationWorkflow.

`synthesize` is a plain sync function (not `async def`) — see design.md's Decisions:
`render_job()` is itself blocking, GPU-bound work, so Temporal's Python SDK runs it in
a thread pool automatically; a background thread calls `activity.heartbeat()` every 15s
for the duration of the call rather than instrumenting mx_narrator's own code.
"""

from __future__ import annotations

import contextvars
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import torch
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from temporalio import activity

from mx_narrator.batch import RenderJob, render_job
from mx_narrator.prep import prepare
from worker.align import align_captions as align_captions_fn
from worker.diff import check_correctness
from worker.id3 import apply_id3
from worker.llm import VideoMetadataSchema, generate_structured
from worker.media import media_relative_url, slugify_filename
from worker.transcription import transcribe_audio
from worker.video import render_video as render_video_ffmpeg
from worker.voice_storage import voice_family_path
from worker.types import (
    AlignCaptionsInput,
    AlignCaptionsResult,
    ApproveMetadataInput,
    CorrectnessCheckInput,
    CorrectnessCheckResult,
    GenerateMetadataInput,
    GenerateMetadataResult,
    Mismatch,
    RenderVideoInput,
    RenderVideoResult,
    SaveMetadataDraftInput,
    SynthesizeInput,
    SynthesizeResult,
    TranscribeInput,
    TranscribeResult,
    VideoMetadataFields,
)

MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://mongo:27017/?replicaSet=rs0")
# The database itself is still literally named narrator_studio — renaming it would mean
# a real migration of live production data (dump/restore, or recreate + copy every
# collection) for a purely cosmetic payoff, since nothing external reads this name.
# Decoupled into an env var instead, same pattern as MONGODB_URL, so it's configurable
# without a code change even though today's default keeps the current value untouched.
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "narrator_studio")
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/data/media"))
HEARTBEAT_INTERVAL_SECONDS = 15
SERIES_CONTEXT_LIMIT = 10

_mongo_client: MongoClient | None = None
_async_mongo_client: AsyncIOMotorClient | None = None


def _db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGODB_URL)
    return _mongo_client[MONGODB_DATABASE]


def _async_db():
    # generate_metadata is async (I/O-bound, unlike synthesize's sync+heartbeat-thread
    # pattern) — its Mongo reads use Motor, not pymongo, so they don't block the event
    # loop other activities on the same worker process may be sharing.
    global _async_mongo_client
    if _async_mongo_client is None:
        _async_mongo_client = AsyncIOMotorClient(MONGODB_URL)
    return _async_mongo_client[MONGODB_DATABASE]


@activity.defn
def synthesize(input: SynthesizeInput) -> SynthesizeResult:
    stop_heartbeat = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop_heartbeat.wait(HEARTBEAT_INTERVAL_SECONDS):
            activity.heartbeat()

    # Temporal's activity context is thread-local, set up only for the thread the SDK
    # itself runs the activity callable on. A plain `threading.Thread` doesn't inherit
    # it (raises "Not in activity context" on `activity.heartbeat()`), so the current
    # context is captured and run explicitly in the new thread.
    ctx = contextvars.copy_context()
    heartbeat_thread = threading.Thread(target=lambda: ctx.run(_heartbeat_loop), daemon=True)
    heartbeat_thread.start()

    try:
        job_dir = MEDIA_ROOT / input.render_job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        script_path = job_dir / "script.txt"
        script_path.write_text(input.script_text, encoding="utf-8")

        out_path = job_dir / f"{slugify_filename(input.unit_id)}.{input.lang}.mp3"

        job = RenderJob(
            unit_id=input.unit_id,
            lang=input.lang,
            script_path=script_path,
            out_path=out_path,
            engine_name=input.engine_name,
            speed=input.speed,
            exaggeration=input.exaggeration,
            cfg_weight=input.cfg_weight,
            seed=input.seed,
            series_album=input.series_album,
            title=input.title,
            voice_family=voice_family_path(MEDIA_ROOT, input.voice_id) if input.voice_id else None,
        )

        def _on_progress(current: int, total: int) -> None:
            _db()["render_jobs"].update_one(
                {"_id": input.render_job_id}, {"$set": {"progress": {"current": current, "total": total}}}
            )

        result = render_job(job, progress_callback=_on_progress)
        if not result.ok:
            raise RuntimeError(result.message)

        apply_id3(out_path, input.id3)

        return SynthesizeResult(audio_path=str(out_path))
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        # This process handles synthesize/transcribe/align_captions across many jobs
        # over its lifetime (one long-lived gpu-worker); PyTorch's caching allocator
        # keeps Chatterbox's VRAM reserved for itself even after the model object is
        # gone, so a later activity in this same process (transcribe's ctranslate2
        # allocator, in particular) can fail with a CUDA OOM despite the GPU actually
        # being idle. Confirmed as the real cause of a stuck video_job: ~10GB resident
        # at 0% utilization. empty_cache() returns PyTorch's unused reserved memory to
        # the driver so other allocators can actually use it.
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


@activity.defn
def mark_render_job(render_job_id: str, status: str, audio_path: str = "", error: str = "") -> None:
    """Small, reliable Mongo write, separate from the long-running `synthesize`
    Activity — called by the workflow before/after synthesis to record status
    transitions (queued -> rendering -> complete/failed) per RFC §10.1."""
    update: dict = {"status": status}
    if audio_path:
        update["audio_path"] = audio_path
        # Computed once here rather than in api/main.py, so it reaches both the
        # render_jobs SSE stream and the /dashboard listing without recomputing it
        # in two places (Path(...).relative_to(...) matching the /media static mount).
        update["audio_url"] = media_relative_url(audio_path, MEDIA_ROOT)
    if error:
        update["error"] = error
    _db()["render_jobs"].update_one({"_id": render_job_id}, {"$set": update})


async def _fetch_series_context(script_id: str) -> list[str]:
    """Prior human-approved episode titles for the same series, most recent first,
    capped at SERIES_CONTEXT_LIMIT — prompt context for consistency (design.md).
    Draft/unapproved titles are excluded. Returns [] for a script with no
    `series_name` set, rather than erroring — Phase 2's `POST /scripts` doesn't
    currently collect `series_name` at all (a real gap between the RFC's data model
    and what's actually implemented, out of this change's declared scope to fix), so
    this is the common case today, not just an edge case."""
    db = _async_db()
    script = await db["scripts"].find_one({"_id": script_id})
    if script is None or not script.get("series_name"):
        return []

    series_name = script["series_name"]
    titles: list[tuple] = []
    async for sibling in db["scripts"].find({"series_name": series_name, "_id": {"$ne": script_id}}):
        render_job_doc = await db["render_jobs"].find_one(
            {"script_id": sibling["_id"]}, sort=[("created_at", -1)]
        )
        if render_job_doc is None:
            continue
        video_job = await db["video_jobs"].find_one(
            {"render_job_id": render_job_doc["_id"]}, sort=[("created_at", -1)]
        )
        if video_job is None:
            continue
        metadata = await db["video_metadata"].find_one(
            {"video_job_id": video_job["_id"], "human_approved_at": {"$ne": None}}
        )
        if metadata is None:
            continue
        titles.append((metadata["human_approved_at"], metadata["generated_title"]))

    titles.sort(key=lambda t: t[0], reverse=True)
    return [title for _, title in titles[:SERIES_CONTEXT_LIMIT]]


@activity.defn
async def generate_metadata(input: GenerateMetadataInput) -> GenerateMetadataResult:
    db = _async_db()
    render_job_doc = await db["render_jobs"].find_one({"_id": input.render_job_id})
    if render_job_doc is None:
        raise ValueError(f"no render_jobs document for {input.render_job_id!r}")

    script = await db["scripts"].find_one({"_id": render_job_doc["script_id"]})
    if script is None:
        raise ValueError(f"no scripts document for {render_job_doc['script_id']!r}")

    prior_titles = await _fetch_series_context(script["_id"])

    system = (
        "You write concise, accurate YouTube metadata for episodes of a devotional "
        "narration series. Titles are clear and specific, not clickbait. "
        "Descriptions summarize the episode's content in 2-4 sentences. "
        "Tags are short, relevant keywords."
    )
    prompt_parts = [f"Episode script ({script['lang']}):\n{script['text']}"]
    if prior_titles:
        prior_list = "\n".join(f"- {t}" for t in prior_titles)
        prompt_parts.append(f"Prior episode titles in this series (chronological, most recent first):\n{prior_list}")
    prompt_parts.append("Generate a title, description, and tags for this episode.")
    prompt = "\n\n".join(prompt_parts)

    result = await generate_structured(system=system, prompt=prompt, schema=VideoMetadataSchema)
    assert isinstance(result, VideoMetadataSchema)

    return GenerateMetadataResult(
        metadata=VideoMetadataFields(title=result.title, description=result.description, tags=result.tags)
    )


@activity.defn
def transcribe(input: TranscribeInput) -> TranscribeResult:
    """Sync + heartbeat thread, same shape as `synthesize` — faster-whisper inference
    is itself blocking, GPU-bound work (design.md)."""
    stop_heartbeat = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop_heartbeat.wait(HEARTBEAT_INTERVAL_SECONDS):
            activity.heartbeat()

    ctx = contextvars.copy_context()
    heartbeat_thread = threading.Thread(target=lambda: ctx.run(_heartbeat_loop), daemon=True)
    heartbeat_thread.start()

    try:
        job_dir = MEDIA_ROOT / input.video_job_id
        srt_path = job_dir / "captions.srt"
        output = transcribe_audio(Path(input.audio_path), input.lang, srt_path)
        return TranscribeResult(
            srt_path=str(output.srt_path),
            transcript_text=output.transcript_text,
            words=output.words,
        )
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        # See the matching comment in synthesize()'s finally block — same
        # cross-activity VRAM accumulation risk, same fix.
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


@activity.defn
def correctness_check(input: CorrectnessCheckInput) -> CorrectnessCheckResult:
    """CPU-only, deterministic given its inputs — runs on `cpu-tasks`
    (worker/cpu_main.py), not `gpu-tasks` (design.md)."""
    expected_text = prepare(input.script_text, input.lang).full_text
    return check_correctness(expected_text, input.lang, input.words)


def _mismatch_dict(m: Mismatch | dict) -> dict:
    # Temporal's default payload converter decodes a *nested* dataclass inside a
    # `list[...]` activity-result field back as a plain dict, not the real
    # `Mismatch` type — confirmed via a real Temporal server round trip (this
    # doesn't reproduce under `ActivityEnvironment`, which skips wire
    # serialization entirely). Accept either shape rather than assuming one.
    if isinstance(m, dict):
        return m
    return {"expected": m.expected, "actual": m.actual, "approx_time": m.approx_time}


@activity.defn
def mark_video_job(
    video_job_id: str,
    status: str,
    mismatches: list[Mismatch] | list[dict] | None = None,
    srt_path: str = "",
    video_path: str = "",
    error: str = "",
) -> None:
    """Small, reliable Mongo write, mirroring `mark_render_job` — status transitions
    per RFC §7.3's state machine (transcribing -> checking_correctness -> ...)."""
    update: dict = {"status": status}
    if mismatches is not None:
        update["correctness_check"] = {
            "status": "mismatch" if mismatches else "pass",
            "mismatches": [_mismatch_dict(m) for m in mismatches],
        }
    if srt_path:
        update["srt_path"] = srt_path
    if video_path:
        update["video_path"] = video_path
        # Same computation as mark_render_job's audio_url — stored once here so
        # neither the API layer nor the review UI need to recompute it.
        update["video_url"] = media_relative_url(video_path, MEDIA_ROOT)
        # video_url's path is identical across every re-render (same
        # video_job_id, same "output.mp4"), so a browser has no natural
        # signal to refetch after a revise — confirmed the hard way: a real
        # user re-rendered a video and the page kept showing the old one.
        # The review UI appends this as a cache-busting query param.
        update["video_rendered_at"] = datetime.now(timezone.utc)
    if error:
        update["error"] = error
    _db()["video_jobs"].update_one({"_id": video_job_id}, {"$set": update})


@activity.defn
def finalize_srt(video_job_id: str, srt_path: str, srt_text: str) -> None:
    """Writes the human-approved SRT text over the draft file — the file on disk is
    always the current-best version (design.md)."""
    Path(srt_path).write_text(srt_text, encoding="utf-8")
    _db()["video_jobs"].update_one({"_id": video_job_id}, {"$set": {"srt_path": srt_path}})


@activity.defn
def align_captions(input: AlignCaptionsInput) -> AlignCaptionsResult:
    """GPU-bound forced alignment (design.md) — runs on `gpu-tasks`, always after the
    caption text is already trusted. No heartbeat: a full real episode aligns in
    ~13s once the model is warm; a cold first-ever call also downloads the model
    (cached in HF_HOME afterward), covered by this Activity's start_to_close_timeout
    rather than a heartbeat."""
    aligned = align_captions_fn(Path(input.audio_path), input.lang, Path(input.srt_path))
    return AlignCaptionsResult(aligned=aligned)


@activity.defn
def render_video(input: RenderVideoInput) -> RenderVideoResult:
    """CPU-only ffmpeg mux (image + audio + soft subtitle track) — no GPU involved,
    runs on `cpu-tasks` like `correctness_check`/`generate_metadata`. Heartbeats
    like `synthesize`/`transcribe` — a long episode's mux can run for a while, and
    without a heartbeat a worker that dies mid-run leaves Temporal unaware for the
    full `start_to_close_timeout` (confirmed the hard way: a worker container
    recreated mid-render left this activity showing "Started" for the better part
    of 30 minutes with no actual process running behind it)."""
    stop_heartbeat = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop_heartbeat.wait(HEARTBEAT_INTERVAL_SECONDS):
            activity.heartbeat()

    ctx = contextvars.copy_context()
    heartbeat_thread = threading.Thread(target=lambda: ctx.run(_heartbeat_loop), daemon=True)
    heartbeat_thread.start()

    try:
        job_dir = MEDIA_ROOT / input.video_job_id
        out_path = job_dir / "output.mp4"
        render_video_ffmpeg(Path(input.image_path), Path(input.audio_path), Path(input.srt_path), out_path)
        return RenderVideoResult(video_path=str(out_path))
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)


@activity.defn
def save_metadata_draft(input: SaveMetadataDraftInput) -> None:
    """First write to `video_metadata` — a draft, not yet human-approved. Separate
    from `generate_metadata` itself so that Activity stays a pure compute-and-return
    step, unchanged from how `llm-metadata-generation` built and verified it."""
    _db()["video_metadata"].update_one(
        {"video_job_id": input.video_job_id},
        {
            "$set": {
                "video_job_id": input.video_job_id,
                "render_job_id": input.render_job_id,
                "generated_title": input.metadata.title,
                "generated_description": input.metadata.description,
                "generated_tags": input.metadata.tags,
            },
            "$setOnInsert": {"human_approved_at": None, "manually_uploaded": False},
        },
        upsert=True,
    )


@activity.defn
def approve_metadata(input: ApproveMetadataInput) -> None:
    """Writes the (possibly human-edited) final title/description/tags and stamps
    `human_approved_at` — this is what `_fetch_series_context` looks for when
    finding prior episodes' approved titles."""
    _db()["video_metadata"].update_one(
        {"video_job_id": input.video_job_id},
        {
            "$set": {
                "generated_title": input.title,
                "generated_description": input.description,
                "generated_tags": input.tags,
                "human_approved_at": datetime.now(timezone.utc),
            }
        },
    )


@activity.defn
def reset_manually_uploaded(video_job_id: str) -> None:
    """Called by ReviseCaptionsWorkflow when metadata was already approved and the
    video is re-rendered: the previously-uploaded file is now stale, so any
    "manually uploaded" checkbox the user had already ticked needs to be cleared —
    the corrected video needs re-uploading."""
    _db()["video_metadata"].update_one(
        {"video_job_id": video_job_id},
        {"$set": {"manually_uploaded": False, "manually_uploaded_at": None}},
    )
