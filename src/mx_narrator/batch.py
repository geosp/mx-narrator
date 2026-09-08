"""Render orchestration and multi-GPU batch distribution. See spec section 9.

`render_job()` is the single "prep -> chunk -> synth -> assemble" path for
one script; it is used both directly (single-file / `unit` commands, no
worker pool needed) and inside batch workers pinned to one GPU each via
`CUDA_VISIBLE_DEVICES`. No render is ever split across GPUs — parallelism is
one process per GPU, fed from one shared queue (spec section 2 and 9).
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mx_narrator.assemble import AssembleSegment, assemble_script
from mx_narrator.chunk import chunk_prepared_script
from mx_narrator.engines import get_engine
from mx_narrator.prep import prepare
from mx_narrator.prep.registry import get_pack
from mx_narrator.units import Unit, output_path
from mx_narrator.voices import resolve_voice

logger = logging.getLogger(__name__)


@dataclass
class RenderJob:
    unit_id: str
    lang: str
    script_path: Path
    out_path: Path
    engine_name: str = "chatterbox"
    voice_family: Path | None = None
    speed: float = 0.95
    exaggeration: float = 0.3
    cfg_weight: float = 0.5
    seed: int = 0
    audio_format: str = "mp3"
    normalize: bool = True
    preview_chars: int | None = None
    dry_run: bool = False
    device: str = "cuda"
    series_album: str = ""
    title: str | None = None  # overrides the auto-detected episode title (see _derive_title_from_script)


@dataclass
class RenderResult:
    job: RenderJob
    ok: bool
    message: str = ""
    prepared_text: str | None = None  # populated for --dry-run


def _derive_title_from_script(raw_text: str) -> str:
    """The episode title, when not overridden by --title: the script's own
    first non-blank line, with a markdown heading's leading '#' stripped."""
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.lstrip("#").strip()
    return ""


def render_job(
    job: RenderJob,
    *,
    engine=None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> RenderResult:
    """`progress_callback(current, total)` is called after each chunk finishes
    synthesizing, if given — an optional hook for callers that want incremental
    progress (e.g. Narrator Studio's Temporal Activity writing it to Mongo).
    Deliberately not a field on `RenderJob` itself: `RenderJob` instances are
    pickled through `multiprocessing.Queue` in `run_batch()`/`_worker()` below, and a
    closure capturing e.g. a DB client wouldn't survive that."""
    try:
        raw_text = job.script_path.read_text(encoding="utf-8")
        title = job.title or _derive_title_from_script(raw_text) or job.unit_id
        if job.preview_chars is not None:
            raw_text = raw_text[: job.preview_chars]

        script = prepare(raw_text, job.lang)

        if job.dry_run:
            return RenderResult(job=job, ok=True, prepared_text=script.full_text)

        if engine is None:
            engine = get_engine(job.engine_name)
            engine.load(device=job.device)

        pack = get_pack(job.lang)
        voice_path = resolve_voice(job.voice_family, job.lang)
        engine.prepare_voice(voice_path, exaggeration=job.exaggeration)

        chunks = chunk_prepared_script(script)
        if not chunks:
            return RenderResult(job=job, ok=False, message="prepared script has no content to synthesize")

        tmp_dir = job.out_path.parent / f".{job.out_path.stem}.chunks"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            segments = []
            for i, chunk in enumerate(chunks):
                chunk_path = tmp_dir / f"chunk_{i:04d}.wav"
                synth_opts = dict(seed=job.seed, exaggeration=job.exaggeration, cfg_weight=job.cfg_weight)
                if job.engine_name == "kokoro":
                    synth_opts["voice"] = pack.kokoro_voice
                engine.synth(chunk.text, job.lang, chunk_path, **synth_opts)
                segments.append(
                    AssembleSegment(wav_path=chunk_path, block_kind=chunk.block_kind, block_index=chunk.block_index)
                )
                if progress_callback is not None:
                    progress_callback(i + 1, len(chunks))

            id3 = None
            if job.audio_format == "mp3":
                id3 = dict(
                    title=f"{title} ({job.lang})",
                    artist="Giovanni Fajardo",
                    album=job.series_album or job.unit_id,
                    track=1,
                    lang=job.lang,
                    extra={
                        "cfg_weight": job.cfg_weight,
                        "exaggeration": job.exaggeration,
                        "speed": job.speed,
                        "seed": job.seed,
                    },
                )
            assemble_script(
                segments,
                job.out_path,
                sample_rate=engine.sample_rate,
                speed=job.speed,
                audio_format=job.audio_format,
                normalize=job.normalize,
                id3=id3,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return RenderResult(job=job, ok=True, message=str(job.out_path))
    except Exception as exc:  # one failure must not take down the batch (spec section 9)
        logger.exception("render failed for %s [%s]", job.unit_id, job.lang)
        return RenderResult(job=job, ok=False, message=str(exc))


def plan_jobs(
    units: dict[str, Unit],
    *,
    out_dir: Path,
    langs: list[str] | None = None,
    **job_kwargs,
) -> tuple[list[RenderJob], list[tuple[str, str]]]:
    """Expand discovered units into per-language jobs.

    Returns (jobs, missing) where `missing` lists (unit_id, lang) pairs that
    were requested but have no source script — reported in the batch summary
    rather than silently skipped.
    """
    jobs: list[RenderJob] = []
    missing: list[tuple[str, str]] = []
    audio_format = job_kwargs.get("audio_format", "mp3")

    for unit_id, unit in sorted(units.items()):
        wanted = langs if langs is not None else sorted(unit.scripts.keys())
        for lang in wanted:
            script_path = unit.scripts.get(lang)
            if script_path is None:
                missing.append((unit_id, lang))
                continue
            jobs.append(
                RenderJob(
                    unit_id=unit_id,
                    lang=lang,
                    script_path=script_path,
                    out_path=output_path(out_dir, unit_id, lang, audio_format=audio_format),
                    **job_kwargs,
                )
            )
    return jobs, missing


def _worker(gpu_id: int, job_queue: "mp.Queue", result_queue: "mp.Queue") -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    engine_cache: dict[str, object] = {}
    while True:
        job = job_queue.get()
        if job is None:
            return
        engine = engine_cache.get(job.engine_name)
        if engine is None:
            engine = get_engine(job.engine_name)
            engine.load(device="cuda")
            engine_cache[job.engine_name] = engine
        result_queue.put(render_job(job, engine=engine))


def run_batch(jobs: list[RenderJob], *, gpu_ids: list[int]) -> list[RenderResult]:
    if not jobs:
        return []
    if not gpu_ids:
        raise ValueError("run_batch requires at least one GPU id")

    ctx = mp.get_context("spawn")
    job_queue: mp.Queue = ctx.Queue()
    result_queue: mp.Queue = ctx.Queue()

    for job in jobs:
        job_queue.put(job)
    for _ in gpu_ids:
        job_queue.put(None)  # one stop sentinel per worker

    workers = [ctx.Process(target=_worker, args=(gpu_id, job_queue, result_queue)) for gpu_id in gpu_ids]
    for w in workers:
        w.start()

    results: list[RenderResult] = []
    for _ in jobs:
        results.append(result_queue.get())

    for w in workers:
        w.join()

    return results
