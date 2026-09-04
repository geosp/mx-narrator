"""Minimal FastAPI backend — see specs/api/scripts/spec.md.

`POST /scripts` persists a script + render job and starts `AudioGenerationWorkflow`;
the SSE endpoint pushes `render_jobs` status changes via a MongoDB change stream
(requires the replica set from group 1) rather than the UI polling.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import srt
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from temporalio.client import Client

from mx_narrator.prep.registry import available_languages
from worker.id3 import apply_id3
from worker.types import (
    AudioGenerationWorkflowInput,
    Id3Fields,
    ReviseCaptionsWorkflowInput,
    VideoMetadataFields,
    VideoProductionWorkflowInput,
)
from worker.voice_storage import DEFAULT_SAMPLE_KEY, sample_path, voice_dir

MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://mongo:27017/?replicaSet=rs0")
# The database itself is still literally named narrator_studio — see worker/activities.py's
# matching constant for why this isn't a migration, just decoupled into an env var.
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "narrator_studio")
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")
TASK_QUEUE = "gpu-tasks"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/data/media"))

logger = logging.getLogger(__name__)

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["mongo"] = AsyncIOMotorClient(MONGODB_URL)
    state["temporal"] = await Client.connect(TEMPORAL_ADDRESS)
    yield
    state["mongo"].close()


app = FastAPI(lifespan=lifespan)
# No auth yet (design.md Non-Goals — single-team, personal-scale per the RFC), so a
# wide-open CORS policy here isn't adding a real gap beyond that already-accepted one;
# it just lets the Vite dev server (and the eventual `web` container, different origin)
# call this API at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Lets the video-review UI point an <audio> tag at a render job's MP3 for playback
# during SRT review (RFC §8: review "before it becomes captions") — didn't exist
# before since Phase 2's UI never needed playback.
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")


# StaticFiles sets Last-Modified/ETag but no Cache-Control, so browsers apply
# their own heuristic freshness — for files that get overwritten in place by a
# revise (output.mp4 above all: same path every re-render), that can mean a
# stale copy gets reused without ever checking the server again. Confirmed
# the hard way: a real revise re-rendered correctly, but the browser kept
# showing the old video. no-cache (not no-store) still lets the browser keep
# a copy and validate it via the existing ETag/Last-Modified — just never
# skip that check.
@app.middleware("http")
async def _no_cache_media(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/media/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _db():
    return state["mongo"][MONGODB_DATABASE]


class Id3In(BaseModel):
    artist: str
    title: str
    album: str
    track: int = 1
    year: str = ""
    genre: str = ""
    comments: str = ""


class ScriptIn(BaseModel):
    unit_id: str
    lang: str
    script_text: str = Field(min_length=1)
    id3: Id3In
    engine_name: str = "chatterbox"
    speed: float = 0.95
    exaggeration: float = 0.3
    cfg_weight: float = 0.5
    seed: int = 0
    series_album: str = ""
    title: str | None = None
    # RFC §6.2's series identifier for grouping episodes — distinct from
    # `series_album` above (an MP3 ID3 tag default, unrelated). Used by
    # `generate_metadata` (llm-metadata-generation) to find prior approved episode
    # titles in the same series for prompt context.
    series_name: str = ""
    # References a `voices` document. None means "use the engine's built-in default
    # voice" — the only behavior that existed before voice management was added.
    voice_id: str | None = None


class ScriptOut(BaseModel):
    script_id: str
    render_job_id: str


async def _validate_script_in(body: ScriptIn) -> None:
    if body.lang not in available_languages():
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported language: {body.lang!r}. Supported: {', '.join(available_languages())}",
        )
    if body.voice_id is not None:
        voice = await _db()["voices"].find_one({"_id": body.voice_id})
        if voice is None:
            raise HTTPException(status_code=422, detail=f"no voices document for {body.voice_id!r}")


async def _start_render(script_id: str, body: ScriptIn) -> str:
    """Creates a render_jobs doc + starts AudioGenerationWorkflow for an
    (already-validated, already-persisted) script — shared by create_script (new
    script) and regenerate_script (same script, edited text/tags, fresh render)."""
    render_job_id = str(uuid.uuid4())
    id3 = Id3Fields(**body.id3.model_dump())
    now = datetime.now(timezone.utc)

    await _db()["render_jobs"].insert_one(
        {
            "_id": render_job_id,
            "script_id": script_id,
            "unit_id": body.unit_id,
            "lang": body.lang,
            "status": "queued",
            "engine_name": body.engine_name,
            "speed": body.speed,
            "exaggeration": body.exaggeration,
            "cfg_weight": body.cfg_weight,
            "seed": body.seed,
            "series_album": body.series_album,
            "title": body.title,
            "voice_id": body.voice_id,
            "id3": body.id3.model_dump(),
            "created_at": now,
        }
    )

    await state["temporal"].start_workflow(
        "AudioGenerationWorkflow",
        AudioGenerationWorkflowInput(
            render_job_id=render_job_id,
            unit_id=body.unit_id,
            lang=body.lang,
            script_text=body.script_text,
            id3=id3,
            engine_name=body.engine_name,
            speed=body.speed,
            exaggeration=body.exaggeration,
            cfg_weight=body.cfg_weight,
            seed=body.seed,
            series_album=body.series_album,
            title=body.title,
            voice_id=body.voice_id,
        ),
        id=f"audio-gen-{render_job_id}",
        task_queue=TASK_QUEUE,
    )

    return render_job_id


@app.post("/scripts", response_model=ScriptOut)
async def create_script(body: ScriptIn) -> ScriptOut:
    await _validate_script_in(body)

    now = datetime.now(timezone.utc)
    script_id = str(uuid.uuid4())

    await _db()["scripts"].insert_one(
        {
            "_id": script_id,
            "unit_id": body.unit_id,
            "lang": body.lang,
            "series_name": body.series_name,
            "text": body.script_text,
            "created_at": now,
        }
    )
    render_job_id = await _start_render(script_id, body)

    return ScriptOut(script_id=script_id, render_job_id=render_job_id)


def _media_url(absolute_path: str) -> str:
    # Relative to MEDIA_ROOT, matching the /media static mount.
    return f"/media/{Path(absolute_path).relative_to(MEDIA_ROOT)}"


def _serialize(doc: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in doc.items()}


async def _sse_stream(collection_name: str, doc_id: str):
    collection = _db()[collection_name]

    current = await collection.find_one({"_id": doc_id})
    if current is not None:
        yield f"data: {json.dumps(_serialize(current))}\n\n"

    pipeline = [{"$match": {"documentKey._id": doc_id}}]
    async with collection.watch(pipeline, full_document="updateLookup") as stream:
        async for change in stream:
            doc = change.get("fullDocument")
            if doc is not None:
                yield f"data: {json.dumps(_serialize(doc))}\n\n"


@app.get("/render_jobs/{render_job_id}/events")
async def render_job_events(render_job_id: str) -> StreamingResponse:
    return StreamingResponse(_sse_stream("render_jobs", render_job_id), media_type="text/event-stream")


_REPLACEABLE_RENDER_STATUSES = {"complete", "failed"}


@app.post("/render_jobs/{render_job_id}/audio/replace")
async def replace_render_audio(render_job_id: str, audio: UploadFile = File(...)) -> dict:
    """Lets the user swap in their own edited audio (e.g. with music added) as the
    render job's canonical file — used for video production and anywhere else
    `audio_path` is read. No Temporal involvement: by `complete`/`failed`,
    AudioGenerationWorkflow has already finished, so this is a pure file + Mongo
    write, unlike the video-side revise endpoints which restart a live workflow.
    Saved under a new `audio{ext}` name (not overwriting the original
    `{unit_id}.{lang}.mp3`) — matches revise_image/revise_all's `background{ext}`
    pattern; nothing downstream hardcodes the original synthesis naming."""
    render_job = await _db()["render_jobs"].find_one({"_id": render_job_id})
    if render_job is None:
        raise HTTPException(status_code=404, detail=f"no render_jobs document for {render_job_id!r}")
    if render_job.get("status") not in _REPLACEABLE_RENDER_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"audio can only be replaced once rendering has finished (current status: {render_job.get('status')!r})",
        )

    job_dir = MEDIA_ROOT / render_job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(audio.filename or "audio").suffix or ".mp3"
    audio_path = job_dir / f"audio{ext}"
    audio_path.write_bytes(await audio.read())

    await _db()["render_jobs"].update_one(
        {"_id": render_job_id},
        {
            "$set": {
                "status": "complete",
                "audio_path": str(audio_path),
                "audio_url": _media_url(str(audio_path)),
                "audio_replaced_at": datetime.now(timezone.utc),
            },
            "$unset": {"error": ""},
        },
    )
    return {"ok": True}


class RenderJobSummary(BaseModel):
    id: str
    status: str
    progress: dict | None = None
    audio_url: str | None = None
    error: str | None = None


class VideoJobSummary(BaseModel):
    id: str
    status: str


class EpisodeSummary(BaseModel):
    script_id: str
    unit_id: str
    series_name: str
    lang: str
    created_at: datetime
    render_job: RenderJobSummary | None = None
    video_job: VideoJobSummary | None = None


@app.get("/series")
async def list_series() -> dict:
    # Series aren't a stored entity — just distinct scripts.series_name values —
    # so a series "exists" exactly as long as some script references it, and
    # disappears on its own once the last one is deleted/edited away. No cleanup
    # code needed for that; this endpoint just reflects current script data.
    names = await _db()["scripts"].distinct("series_name")
    return {"series": sorted(n for n in names if n)}


@app.get("/dashboard")
async def get_dashboard() -> dict:
    # Plain per-script lookups, not an aggregation pipeline — same pattern as
    # worker/activities.py:_fetch_series_context, which already does this for a
    # harder case (every sibling script in a series). Not justified at this scale
    # (a personal tool, hundreds of episodes at the very most) to introduce $lookup.
    episodes: list[EpisodeSummary] = []
    async for script in _db()["scripts"].find().sort("created_at", -1):
        render_job = await _db()["render_jobs"].find_one(
            {"script_id": script["_id"]}, sort=[("created_at", -1)]
        )
        render_job_summary = None
        video_job_summary = None
        if render_job is not None:
            # Same fallback as create_video_job, for render_jobs docs written before
            # mark_render_job started computing audio_url itself.
            audio_url = render_job.get("audio_url")
            if audio_url is None and render_job.get("audio_path"):
                audio_url = _media_url(render_job["audio_path"])
            render_job_summary = RenderJobSummary(
                id=render_job["_id"],
                status=render_job["status"],
                progress=render_job.get("progress"),
                audio_url=audio_url,
                error=render_job.get("error"),
            )
            video_job = await _db()["video_jobs"].find_one(
                {"render_job_id": render_job["_id"]}, sort=[("created_at", -1)]
            )
            if video_job is not None:
                video_job_summary = VideoJobSummary(id=video_job["_id"], status=video_job["status"])

        episodes.append(
            EpisodeSummary(
                script_id=script["_id"],
                unit_id=script["unit_id"],
                series_name=script.get("series_name", ""),
                lang=script["lang"],
                created_at=script["created_at"],
                render_job=render_job_summary,
                video_job=video_job_summary,
            )
        )

    return {"episodes": [e.model_dump(mode="json") for e in episodes]}


async def _terminate_workflow(workflow_id: str) -> None:
    # Best-effort: the workflow may already be complete (nothing to terminate) or
    # never started — either way, it must not block deleting the Mongo docs/files,
    # since this is cleanup for data the user explicitly asked to remove.
    try:
        handle = state["temporal"].get_workflow_handle(workflow_id)
        await handle.terminate(reason="deleted from Mx Narrator Studio dashboard")
    except Exception:
        logger.info("no running workflow to terminate for %r (already finished, or never started)", workflow_id)


async def _delete_render_jobs_for_script(script_id: str) -> None:
    """Terminates any in-flight workflows, removes media files, and deletes the
    render_jobs/video_jobs docs for a script — leaves the scripts doc itself alone.
    Shared by delete_script (which also removes the script) and regenerate_script
    (which keeps the script but discards its now-stale render/video, per the user's
    own stated requirement: editing a script's audio invalidates any transcription/
    video work done against the old audio)."""
    render_jobs = await _db()["render_jobs"].find({"script_id": script_id}).to_list(length=None)
    for render_job in render_jobs:
        video_jobs = await _db()["video_jobs"].find({"render_job_id": render_job["_id"]}).to_list(length=None)
        for video_job in video_jobs:
            await _terminate_workflow(f"video-prod-{video_job['_id']}")
            shutil.rmtree(MEDIA_ROOT / video_job["_id"], ignore_errors=True)
            await _db()["video_jobs"].delete_one({"_id": video_job["_id"]})

        await _terminate_workflow(f"audio-gen-{render_job['_id']}")
        shutil.rmtree(MEDIA_ROOT / render_job["_id"], ignore_errors=True)
        await _db()["render_jobs"].delete_one({"_id": render_job["_id"]})


@app.delete("/scripts/{script_id}")
async def delete_script(script_id: str) -> dict:
    script = await _db()["scripts"].find_one({"_id": script_id})
    if script is None:
        raise HTTPException(status_code=404, detail=f"no scripts document for {script_id!r}")

    await _delete_render_jobs_for_script(script_id)
    await _db()["scripts"].delete_one({"_id": script_id})
    return {"ok": True}


class ScriptDetailOut(BaseModel):
    script_id: str
    unit_id: str
    lang: str
    series_name: str
    script_text: str
    id3: Id3In
    engine_name: str
    speed: float
    exaggeration: float
    cfg_weight: float
    seed: int
    series_album: str
    title: str | None
    voice_id: str | None
    has_video_job: bool


@app.get("/scripts/{script_id}", response_model=ScriptDetailOut)
async def get_script(script_id: str) -> ScriptDetailOut:
    script = await _db()["scripts"].find_one({"_id": script_id})
    if script is None:
        raise HTTPException(status_code=404, detail=f"no scripts document for {script_id!r}")

    # Render/engine params (id3, speed, exaggeration, ...) aren't stored on the
    # scripts doc — they live on render_jobs, submitted once at creation time. Pull
    # them from the latest render_job so the edit form can be pre-filled with
    # whatever was last used, defaulting to ScriptIn's own defaults if this script
    # somehow has no render_job yet.
    render_job = await _db()["render_jobs"].find_one({"script_id": script_id}, sort=[("created_at", -1)])
    defaults = ScriptIn(unit_id="", lang="es", script_text="x", id3=Id3In(artist="", title="", album=""))
    has_video_job = False
    if render_job is not None:
        video_job = await _db()["video_jobs"].find_one({"render_job_id": render_job["_id"]})
        has_video_job = video_job is not None

    return ScriptDetailOut(
        script_id=script["_id"],
        unit_id=script["unit_id"],
        lang=script["lang"],
        series_name=script.get("series_name", ""),
        script_text=script["text"],
        id3=Id3In(**render_job["id3"]) if render_job else defaults.id3,
        engine_name=render_job["engine_name"] if render_job else defaults.engine_name,
        speed=render_job["speed"] if render_job else defaults.speed,
        exaggeration=render_job["exaggeration"] if render_job else defaults.exaggeration,
        cfg_weight=render_job["cfg_weight"] if render_job else defaults.cfg_weight,
        seed=render_job["seed"] if render_job else defaults.seed,
        series_album=render_job.get("series_album", "") if render_job else defaults.series_album,
        title=render_job.get("title") if render_job else defaults.title,
        voice_id=render_job.get("voice_id") if render_job else defaults.voice_id,
        has_video_job=has_video_job,
    )


class RegenerateOut(BaseModel):
    script_id: str
    render_job_id: str
    audio_regenerated: bool


# Fields that can actually change the synthesized audio bytes. unit_id is included
# conservatively since it's part of the output filename. Everything else the form
# submits (id3.*, series_name, series_album, title) is pure metadata — series_album
# and title only ever seed a *transient* default tag inside render_job() that
# apply_id3() immediately overwrites, so they don't affect the file even today.
_AUDIO_AFFECTING_SCRIPT_FIELDS = ("unit_id", "lang", "script_text")
_AUDIO_AFFECTING_RENDER_FIELDS = ("engine_name", "speed", "exaggeration", "cfg_weight", "seed", "voice_id")


@app.put("/scripts/{script_id}/regenerate", response_model=RegenerateOut)
async def regenerate_script(script_id: str, body: ScriptIn) -> RegenerateOut:
    """Edits a script's text/tags/render params. Per the user's own requirement: any
    existing render_job/video_job is stale the moment something that actually
    affects the synthesized audio changes — so those cases discard it and start a
    fresh render, same as before. But an edit that only touches metadata (ID3 tags,
    series_name, series_album, title) doesn't change the audio at all, so it's
    wasteful and needlessly destructive to re-run synthesis and throw away a good
    video review over a tag typo — that case rewrites the existing MP3's tags in
    place instead and leaves the render/video job untouched."""
    script = await _db()["scripts"].find_one({"_id": script_id})
    if script is None:
        raise HTTPException(status_code=404, detail=f"no scripts document for {script_id!r}")
    await _validate_script_in(body)

    render_job = await _db()["render_jobs"].find_one({"script_id": script_id}, sort=[("created_at", -1)])

    script_field_values = {"unit_id": script["unit_id"], "lang": script["lang"], "script_text": script["text"]}
    needs_full_regenerate = (
        render_job is None
        or render_job.get("status") != "complete"
        or any(script_field_values[f] != getattr(body, f) for f in _AUDIO_AFFECTING_SCRIPT_FIELDS)
        or any(render_job.get(f) != getattr(body, f) for f in _AUDIO_AFFECTING_RENDER_FIELDS)
    )

    await _db()["scripts"].update_one(
        {"_id": script_id},
        {
            "$set": {
                "unit_id": body.unit_id,
                "lang": body.lang,
                "series_name": body.series_name,
                "text": body.script_text,
            }
        },
    )

    if needs_full_regenerate:
        await _delete_render_jobs_for_script(script_id)
        render_job_id = await _start_render(script_id, body)
        return RegenerateOut(script_id=script_id, render_job_id=render_job_id, audio_regenerated=True)

    # Tags-only fast path: no workflow started or terminated, render_job/video_job
    # both untouched apart from the metadata fields themselves.
    await _db()["render_jobs"].update_one(
        {"_id": render_job["_id"]},
        {"$set": {"id3": body.id3.model_dump(), "series_album": body.series_album, "title": body.title}},
    )
    apply_id3(Path(render_job["audio_path"]), Id3Fields(**body.id3.model_dump()))

    return RegenerateOut(script_id=script_id, render_job_id=render_job["_id"], audio_regenerated=False)


class VoiceOut(BaseModel):
    id: str
    name: str
    languages: list[str]


def _validate_sample_lang(lang: str) -> None:
    if lang != DEFAULT_SAMPLE_KEY and lang not in available_languages():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid sample language: {lang!r}. Use one of "
                f"{', '.join(available_languages())}, or {DEFAULT_SAMPLE_KEY!r} for the fallback sample."
            ),
        )


def _validate_wav_upload(file: UploadFile) -> None:
    # No transcoding support — resolve_voice()'s per-language lookup swaps in
    # `.{lang}` before a *single* shared suffix, so every sample in a family must
    # share the same extension. Requiring .wav (matching the two existing samples
    # already in voices/) keeps that guarantee without adding an audio dependency.
    if Path(file.filename or "").suffix.lower() != ".wav":
        raise HTTPException(status_code=422, detail="voice samples must be a .wav file")


@app.get("/voices")
async def list_voices() -> dict:
    voices = await _db()["voices"].find().sort("created_at", -1).to_list(length=None)
    return {
        "voices": [
            VoiceOut(id=v["_id"], name=v["name"], languages=v.get("languages", [])).model_dump() for v in voices
        ]
    }


@app.post("/voices", response_model=VoiceOut)
async def create_voice(name: str = Form(...), lang: str = Form(...), file: UploadFile = File(...)) -> VoiceOut:
    _validate_sample_lang(lang)
    _validate_wav_upload(file)

    voice_id = str(uuid.uuid4())
    path = sample_path(MEDIA_ROOT, voice_id, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())

    await _db()["voices"].insert_one(
        {"_id": voice_id, "name": name, "languages": [lang], "created_at": datetime.now(timezone.utc)}
    )
    return VoiceOut(id=voice_id, name=name, languages=[lang])


@app.post("/voices/{voice_id}/samples", response_model=VoiceOut)
async def add_voice_sample(voice_id: str, lang: str = Form(...), file: UploadFile = File(...)) -> VoiceOut:
    voice = await _db()["voices"].find_one({"_id": voice_id})
    if voice is None:
        raise HTTPException(status_code=404, detail=f"no voices document for {voice_id!r}")
    _validate_sample_lang(lang)
    _validate_wav_upload(file)

    path = sample_path(MEDIA_ROOT, voice_id, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(await file.read())

    languages = sorted(set(voice.get("languages", [])) | {lang})
    await _db()["voices"].update_one({"_id": voice_id}, {"$set": {"languages": languages}})
    return VoiceOut(id=voice_id, name=voice["name"], languages=languages)


@app.delete("/voices/{voice_id}/samples/{lang}")
async def delete_voice_sample(voice_id: str, lang: str) -> dict:
    voice = await _db()["voices"].find_one({"_id": voice_id})
    if voice is None:
        raise HTTPException(status_code=404, detail=f"no voices document for {voice_id!r}")
    languages = voice.get("languages", [])
    if lang not in languages:
        raise HTTPException(status_code=404, detail=f"voice {voice_id!r} has no {lang!r} sample")
    if len(languages) <= 1:
        raise HTTPException(
            status_code=422, detail="cannot delete a voice's last remaining sample — delete the voice instead"
        )

    sample_path(MEDIA_ROOT, voice_id, lang).unlink(missing_ok=True)
    languages = [existing for existing in languages if existing != lang]
    await _db()["voices"].update_one({"_id": voice_id}, {"$set": {"languages": languages}})
    return {"ok": True}


@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str) -> dict:
    voice = await _db()["voices"].find_one({"_id": voice_id})
    if voice is None:
        raise HTTPException(status_code=404, detail=f"no voices document for {voice_id!r}")

    shutil.rmtree(voice_dir(MEDIA_ROOT, voice_id), ignore_errors=True)
    await _db()["voices"].delete_one({"_id": voice_id})
    return {"ok": True}


class VideoJobOut(BaseModel):
    video_job_id: str


@app.post("/video_jobs", response_model=VideoJobOut)
async def create_video_job(
    render_job_id: str = Form(...),
    image: UploadFile = File(...),
) -> VideoJobOut:
    render_job = await _db()["render_jobs"].find_one({"_id": render_job_id})
    if render_job is None:
        raise HTTPException(status_code=404, detail=f"no render_jobs document for {render_job_id!r}")
    if render_job.get("status") != "complete" or not render_job.get("audio_path"):
        raise HTTPException(status_code=422, detail="render_job has no finished audio yet")

    script = await _db()["scripts"].find_one({"_id": render_job["script_id"]})
    if script is None:
        raise HTTPException(status_code=404, detail=f"no scripts document for {render_job['script_id']!r}")

    video_job_id = str(uuid.uuid4())
    job_dir = MEDIA_ROOT / video_job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(image.filename or "background").suffix or ".jpg"
    image_path = job_dir / f"background{ext}"
    image_path.write_bytes(await image.read())

    # render_jobs.audio_url is computed once, in worker/activities.py:mark_render_job,
    # at the moment a render completes. Fallback here only for render_jobs docs
    # written before that field existed.
    audio_url = render_job.get("audio_url") or _media_url(render_job["audio_path"])

    now = datetime.now(timezone.utc)
    workflow_id = f"video-prod-{video_job_id}"
    await _db()["video_jobs"].insert_one(
        {
            "_id": video_job_id,
            "render_job_id": render_job_id,
            "image_path": str(image_path),
            "audio_url": audio_url,
            "status": "transcribing",
            # Which Temporal workflow execution currently "owns" this video job —
            # signals (mismatch/srt/metadata approval) need to reach whichever one
            # is actually running. Starts as this one; a later caption revision
            # (a fresh workflow execution — this one will have already closed by
            # then) updates it so approve_metadata still reaches the right place.
            "active_workflow_id": workflow_id,
            "created_at": now,
        }
    )

    await state["temporal"].start_workflow(
        "VideoProductionWorkflow",
        VideoProductionWorkflowInput(
            video_job_id=video_job_id,
            render_job_id=render_job_id,
            audio_path=render_job["audio_path"],
            script_text=script["text"],
            lang=script["lang"],
            image_path=str(image_path),
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return VideoJobOut(video_job_id=video_job_id)


@app.post("/video_jobs/{video_job_id}/mismatch/acknowledge")
async def acknowledge_mismatch(video_job_id: str) -> dict:
    handle = state["temporal"].get_workflow_handle(f"video-prod-{video_job_id}")
    await handle.signal("acknowledge_mismatch")
    return {"ok": True}


class SrtApproveIn(BaseModel):
    srt_text: str


@app.post("/video_jobs/{video_job_id}/srt/approve")
async def approve_srt(video_job_id: str, body: SrtApproveIn) -> dict:
    # Validated here, at the API boundary — signals are fire-and-forget with no
    # synchronous return path to reject bad input through, so a malformed SRT must
    # never reach the workflow at all (design.md).
    try:
        list(srt.parse(body.srt_text))
    except srt.SRTParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid SRT: {exc}") from exc

    handle = state["temporal"].get_workflow_handle(f"video-prod-{video_job_id}")
    await handle.signal("approve_srt", body.srt_text)
    return {"ok": True}


@app.get("/video_jobs/{video_job_id}/srt")
async def get_srt(video_job_id: str) -> dict:
    video_job = await _db()["video_jobs"].find_one({"_id": video_job_id})
    if video_job is None or not video_job.get("srt_path"):
        raise HTTPException(status_code=404, detail="no SRT available yet for this video job")
    return {"srt_text": Path(video_job["srt_path"]).read_text(encoding="utf-8")}


# Revising is only offered once captions have already been approved at least
# once — mid-render statuses aren't meaningful to revise into, and earlier
# statuses (still transcribing/reviewing for the first time) should go through
# the original mismatch/srt-approve flow instead.
_REVISABLE_VIDEO_STATUSES = {"metadata_review_pending", "ready_for_manual_upload", "failed"}


@app.post("/video_jobs/{video_job_id}/srt/revise")
async def revise_srt(video_job_id: str, body: SrtApproveIn) -> dict:
    try:
        list(srt.parse(body.srt_text))
    except srt.SRTParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid SRT: {exc}") from exc

    video_job = await _db()["video_jobs"].find_one({"_id": video_job_id})
    if video_job is None:
        raise HTTPException(status_code=404, detail=f"no video_jobs document for {video_job_id!r}")
    if video_job.get("status") not in _REVISABLE_VIDEO_STATUSES or not video_job.get("srt_path"):
        raise HTTPException(
            status_code=422,
            detail=f"captions can only be revised after initial approval (current status: {video_job.get('status')!r})",
        )

    render_job = await _db()["render_jobs"].find_one({"_id": video_job["render_job_id"]})
    if render_job is None or not render_job.get("audio_path"):
        raise HTTPException(status_code=404, detail=f"no render_jobs document for {video_job['render_job_id']!r}")

    metadata = await _db()["video_metadata"].find_one({"video_job_id": video_job_id})
    metadata_already_approved = metadata is not None and metadata.get("human_approved_at") is not None

    # Best-effort — the previous execution (original or an earlier revise) has
    # very likely already closed; _terminate_workflow handles that gracefully.
    # Guards against a genuinely still-open one (e.g. a prior revise mid-render)
    # racing the new one on the same files.
    old_workflow_id = video_job.get("active_workflow_id") or f"video-prod-{video_job_id}"
    await _terminate_workflow(old_workflow_id)

    new_workflow_id = f"video-revise-{video_job_id}"
    await _db()["video_jobs"].update_one(
        {"_id": video_job_id}, {"$set": {"active_workflow_id": new_workflow_id}}
    )

    await state["temporal"].start_workflow(
        "ReviseCaptionsWorkflow",
        ReviseCaptionsWorkflowInput(
            video_job_id=video_job_id,
            render_job_id=video_job["render_job_id"],
            srt_path=video_job["srt_path"],
            srt_text=body.srt_text,
            image_path=video_job["image_path"],
            audio_path=render_job["audio_path"],
            lang=render_job["lang"],
            metadata_already_approved=metadata_already_approved,
        ),
        id=new_workflow_id,
        task_queue=TASK_QUEUE,
    )
    return {"ok": True}


@app.post("/video_jobs/{video_job_id}/image/revise")
async def revise_image(video_job_id: str, image: UploadFile = File(...)) -> dict:
    """Same revisability rule and re-render machinery as `revise_srt` — reuses
    ReviseCaptionsWorkflow with the *current, unchanged* SRT text and a new
    image_path, rather than a separate workflow. Only the background image
    changes; captions/metadata are untouched (or regenerated only if not yet
    approved, same as any other revise)."""
    video_job = await _db()["video_jobs"].find_one({"_id": video_job_id})
    if video_job is None:
        raise HTTPException(status_code=404, detail=f"no video_jobs document for {video_job_id!r}")
    if video_job.get("status") not in _REVISABLE_VIDEO_STATUSES or not video_job.get("srt_path"):
        raise HTTPException(
            status_code=422,
            detail=f"the image can only be revised after initial approval (current status: {video_job.get('status')!r})",
        )

    render_job = await _db()["render_jobs"].find_one({"_id": video_job["render_job_id"]})
    if render_job is None or not render_job.get("audio_path"):
        raise HTTPException(status_code=404, detail=f"no render_jobs document for {video_job['render_job_id']!r}")

    srt_text = Path(video_job["srt_path"]).read_text(encoding="utf-8")

    job_dir = MEDIA_ROOT / video_job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(image.filename or "background").suffix or ".jpg"
    image_path = job_dir / f"background{ext}"
    image_path.write_bytes(await image.read())
    await _db()["video_jobs"].update_one({"_id": video_job_id}, {"$set": {"image_path": str(image_path)}})

    metadata = await _db()["video_metadata"].find_one({"video_job_id": video_job_id})
    metadata_already_approved = metadata is not None and metadata.get("human_approved_at") is not None

    old_workflow_id = video_job.get("active_workflow_id") or f"video-prod-{video_job_id}"
    await _terminate_workflow(old_workflow_id)

    new_workflow_id = f"video-revise-{video_job_id}"
    await _db()["video_jobs"].update_one(
        {"_id": video_job_id}, {"$set": {"active_workflow_id": new_workflow_id}}
    )

    await state["temporal"].start_workflow(
        "ReviseCaptionsWorkflow",
        ReviseCaptionsWorkflowInput(
            video_job_id=video_job_id,
            render_job_id=video_job["render_job_id"],
            srt_path=video_job["srt_path"],
            srt_text=srt_text,
            image_path=str(image_path),
            audio_path=render_job["audio_path"],
            lang=render_job["lang"],
            metadata_already_approved=metadata_already_approved,
        ),
        id=new_workflow_id,
        task_queue=TASK_QUEUE,
    )
    return {"ok": True}


@app.post("/video_jobs/{video_job_id}/revise-all")
async def revise_all(
    video_job_id: str,
    srt_text: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    image: UploadFile | None = File(None),
) -> dict:
    """Unified save for the Metadata review screen: captions, background
    image, and metadata title/description/tags all submitted together in one
    call. Only re-renders (terminating and restarting the active workflow)
    if the caption text or image actually changed — a pure metadata-only
    edit takes the same fast signal path `metadata/approve` already uses,
    since the workflow is still open and waiting for exactly that signal at
    this status. Scoped to `metadata_review_pending` only (unlike
    `revise_srt`/`revise_image`): `ready_for_manual_upload`/`failed` have no
    live waiting workflow left to signal, so this endpoint isn't valid
    there."""
    try:
        new_subs = list(srt.parse(srt_text))
    except srt.SRTParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid SRT: {exc}") from exc

    video_job = await _db()["video_jobs"].find_one({"_id": video_job_id})
    if video_job is None:
        raise HTTPException(status_code=404, detail=f"no video_jobs document for {video_job_id!r}")
    if video_job.get("status") != "metadata_review_pending" or not video_job.get("srt_path"):
        raise HTTPException(
            status_code=422,
            detail=f"can only be saved during metadata review (current status: {video_job.get('status')!r})",
        )

    render_job = await _db()["render_jobs"].find_one({"_id": video_job["render_job_id"]})
    if render_job is None or not render_job.get("audio_path"):
        raise HTTPException(status_code=404, detail=f"no render_jobs document for {video_job['render_job_id']!r}")

    # Compare parsed caption *text* only, not the raw SRT string — entries
    # round-tripped through the browser's parseSrt/serializeSrt (web/src/srt.js)
    # re-derive timestamps from a float, which can drift by a millisecond of
    # rounding noise with zero real edits (confirmed empirically). Timing
    # isn't user-editable in this UI anyway, so text is the only thing that
    # actually needs a re-render to reflect.
    current_srt_text = Path(video_job["srt_path"]).read_text(encoding="utf-8")
    current_subs = list(srt.parse(current_srt_text))
    srt_text_changed = [s.content for s in new_subs] != [s.content for s in current_subs]
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    image_path = video_job["image_path"]
    if image is not None:
        job_dir = MEDIA_ROOT / video_job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename or "background").suffix or ".jpg"
        image_path = str(job_dir / f"background{ext}")
        Path(image_path).write_bytes(await image.read())
        await _db()["video_jobs"].update_one({"_id": video_job_id}, {"$set": {"image_path": image_path}})

    needs_rerender = image is not None or srt_text_changed

    if not needs_rerender:
        # Fast path: identical to metadata/approve — signal the workflow
        # that's still open and waiting for this exact signal, no wasted
        # re-render for a pure metadata edit.
        workflow_id = video_job.get("active_workflow_id") or f"video-prod-{video_job_id}"
        handle = state["temporal"].get_workflow_handle(workflow_id)
        await handle.signal("approve_metadata", args=[title, description, tags_list])
        return {"ok": True, "rerendered": False}

    old_workflow_id = video_job.get("active_workflow_id") or f"video-prod-{video_job_id}"
    await _terminate_workflow(old_workflow_id)

    new_workflow_id = f"video-revise-{video_job_id}"
    await _db()["video_jobs"].update_one(
        {"_id": video_job_id}, {"$set": {"active_workflow_id": new_workflow_id}}
    )

    await state["temporal"].start_workflow(
        "ReviseCaptionsWorkflow",
        ReviseCaptionsWorkflowInput(
            video_job_id=video_job_id,
            render_job_id=video_job["render_job_id"],
            srt_path=video_job["srt_path"],
            srt_text=srt_text,
            image_path=image_path,
            audio_path=render_job["audio_path"],
            lang=render_job["lang"],
            metadata_already_approved=True,
            metadata=VideoMetadataFields(title=title, description=description, tags=tags_list),
        ),
        id=new_workflow_id,
        task_queue=TASK_QUEUE,
    )
    return {"ok": True, "rerendered": True}


class VideoMetadataOut(BaseModel):
    title: str
    description: str
    tags: list[str]
    human_approved: bool
    manually_uploaded: bool


@app.get("/video_jobs/{video_job_id}/metadata", response_model=VideoMetadataOut)
async def get_video_metadata(video_job_id: str) -> VideoMetadataOut:
    metadata = await _db()["video_metadata"].find_one({"video_job_id": video_job_id})
    if metadata is None:
        raise HTTPException(status_code=404, detail="no metadata available yet for this video job")
    return VideoMetadataOut(
        title=metadata.get("generated_title", ""),
        description=metadata.get("generated_description", ""),
        tags=metadata.get("generated_tags", []),
        human_approved=metadata.get("human_approved_at") is not None,
        manually_uploaded=metadata.get("manually_uploaded", False),
    )


class MetadataApproveIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = []


@app.post("/video_jobs/{video_job_id}/metadata/approve")
async def approve_metadata_endpoint(video_job_id: str, body: MetadataApproveIn) -> dict:
    video_job = await _db()["video_jobs"].find_one({"_id": video_job_id})
    # Metadata approval can now be signaled to either the original VideoProductionWorkflow
    # or a later ReviseCaptionsWorkflow — whichever is currently running for this video
    # job. Falls back to the original naming convention for video_jobs docs written
    # before active_workflow_id existed.
    workflow_id = (video_job or {}).get("active_workflow_id") or f"video-prod-{video_job_id}"
    handle = state["temporal"].get_workflow_handle(workflow_id)
    await handle.signal("approve_metadata", args=[body.title, body.description, body.tags])
    return {"ok": True}


@app.post("/video_jobs/{video_job_id}/manually_uploaded")
async def mark_manually_uploaded(video_job_id: str) -> dict:
    # Pure bookkeeping — the workflow has already reached its terminal state by the
    # time this is toggled, so this is a direct Mongo write, not a signal (RFC §6.2:
    # no YouTube call of any kind happens here, ever).
    result = await _db()["video_metadata"].update_one(
        {"video_job_id": video_job_id},
        {"$set": {"manually_uploaded": True, "manually_uploaded_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="no metadata document for this video job")
    return {"ok": True}


@app.get("/video_jobs/{video_job_id}/events")
async def video_job_events(video_job_id: str) -> StreamingResponse:
    return StreamingResponse(_sse_stream("video_jobs", video_job_id), media_type="text/event-stream")
