"""Concatenation, silences, loudness normalization, MP3 encoding, ID3 tagging.

Spec section 11:
- Silence between blocks reflects block *kind*, not model output — inserted
  as generated digital silence, never left to the model.
- Concatenation uses ffmpeg's `concat` audio filter, not the `-f concat`
  demuxer with a list file (the filter avoids format-mismatch surprises
  across engines/sample rates and doesn't require writing a list file).
- Loudness is normalized to -16 LUFS with identical settings across
  languages, so the three renders of one unit match each other.
- Speed is applied here, once, via ffmpeg `atempo` — uniformly across
  engines, since Chatterbox has no native speed control (see `engines/base.py`).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TIT2, TLAN, TPE1, TRCK, TXXX

logger = logging.getLogger(__name__)

SILENCE_PARAGRAPH_MS = 600
SILENCE_HEADING_MS = 1200
SILENCE_QUOTE_MS = 900
TARGET_LUFS = -16.0


def pause_ms_for_transition(prev_kind: str | None, next_kind: str) -> int:
    """How much silence belongs between two adjacent blocks.

    Headings and quotes both want a pause on either side of them; when two
    rules could apply at one boundary (e.g. a quote right after a heading),
    the stronger pause wins rather than picking one rule arbitrarily.
    """
    if prev_kind is None:
        return 0
    candidates = []
    if prev_kind == "heading" or next_kind == "heading":
        candidates.append(SILENCE_HEADING_MS)
    if prev_kind == "quote" or next_kind == "quote":
        candidates.append(SILENCE_QUOTE_MS)
    if not candidates:
        candidates.append(SILENCE_PARAGRAPH_MS)
    return max(candidates)


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({' '.join(args)}):\n{result.stderr}")


def _make_silence(path: Path, ms: int, *, sample_rate: int) -> None:
    duration_s = ms / 1000
    _run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", f"{duration_s:.3f}",
            str(path),
        ]
    )


def _atempo_filter(speed: float) -> str:
    """ffmpeg's `atempo` only accepts [0.5, 2.0] per stage; chain stages for extremes."""
    stages = []
    remaining = speed
    while remaining < 0.5 or remaining > 2.0:
        step = 0.5 if remaining < 0.5 else 2.0
        stages.append(step)
        remaining /= step
    stages.append(remaining)
    return ",".join(f"atempo={s:.6f}" for s in stages)


@dataclass
class AssembleSegment:
    wav_path: Path
    block_kind: str
    block_index: int


def concat_with_silences(segments: list[AssembleSegment], *, sample_rate: int, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    inputs: list[Path] = []
    prev_block_index = None
    prev_kind = None
    silence_cache: dict[int, Path] = {}

    def silence_path(ms: int) -> Path:
        if ms not in silence_cache:
            p = workdir / f"silence_{ms}ms.wav"
            _make_silence(p, ms, sample_rate=sample_rate)
            silence_cache[ms] = p
        return silence_cache[ms]

    for seg in segments:
        if seg.block_index != prev_block_index:
            pause = pause_ms_for_transition(prev_kind, seg.block_kind)
            if pause > 0:
                inputs.append(silence_path(pause))
            prev_kind = seg.block_kind
        inputs.append(seg.wav_path)
        prev_block_index = seg.block_index

    if len(inputs) == 1:
        return inputs[0]

    filter_inputs = "".join(f"[{i}:a]" for i in range(len(inputs)))
    filter_complex = f"{filter_inputs}concat=n={len(inputs)}:v=0:a=1[out]"
    out_path = workdir / "concatenated.wav"

    args: list[str] = []
    for p in inputs:
        args += ["-i", str(p)]
    args += ["-filter_complex", filter_complex, "-map", "[out]", str(out_path)]
    _run_ffmpeg(args)
    return out_path


def apply_speed_and_loudness(in_path: Path, out_path: Path, *, speed: float, normalize: bool) -> None:
    filters = []
    if speed and abs(speed - 1.0) > 1e-6:
        filters.append(_atempo_filter(speed))
    if normalize:
        filters.append(f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11")

    if not filters:
        shutil.copyfile(in_path, out_path)
        return
    _run_ffmpeg(["-i", str(in_path), "-af", ",".join(filters), str(out_path)])


def encode_mp3(wav_path: Path, mp3_path: Path) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(["-i", str(wav_path), "-ac", "1", "-ar", "44100", "-b:a", "128k", str(mp3_path)])


def tag_mp3(
    mp3_path: Path,
    *,
    title: str,
    artist: str,
    album: str,
    track: int,
    lang: str,
    extra: dict[str, str] | None = None,
) -> None:
    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags["TPE1"] = TPE1(encoding=3, text=artist)
    tags["TALB"] = TALB(encoding=3, text=album)
    tags["TRCK"] = TRCK(encoding=3, text=str(track))
    tags["TLAN"] = TLAN(encoding=3, text=lang)
    # Custom render-parameter frames (TXXX), e.g. cfg_weight, exaggeration —
    # so a finished file records what settings produced it, for comparing
    # renders later. Identified by `desc`, not just the frame id, since a
    # file can carry several TXXX frames at once.
    for key, value in (extra or {}).items():
        tags[f"TXXX:{key}"] = TXXX(encoding=3, desc=key, text=str(value))
    tags.save(str(mp3_path))


def assemble_script(
    segments: list[AssembleSegment],
    out_path: Path,
    *,
    sample_rate: int,
    speed: float,
    audio_format: str,
    normalize: bool,
    id3: dict | None,
) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="mx_narrator_assemble_"))
    try:
        concatenated = concat_with_silences(segments, sample_rate=sample_rate, workdir=workdir)
        processed = workdir / "processed.wav"
        apply_speed_and_loudness(concatenated, processed, speed=speed, normalize=normalize)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if audio_format == "mp3":
            encode_mp3(processed, out_path)
            if id3:
                tag_mp3(out_path, **id3)
        else:
            shutil.copyfile(processed, out_path)
        return out_path
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
