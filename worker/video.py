"""Turns a finished episode's background image + audio + approved SRT into a
playable MP4 — entirely Mx Narrator Studio-side, not part of `src/mx_narrator/`. The
original CLI's scope was always "script -> audio"; video production never existed
in mx_narrator's own library, so this doesn't touch it, matching every prior phase's
"orchestrate, don't modify" rule.

Captions are burned directly into the video frames (`-vf subtitles=...`, libass)
— a soft/selectable `mov_text` track alone turned out invisible in practice: no
browser exposes an embedded MP4 subtitle stream in its native `<video>` controls,
and YouTube doesn't pull captions from one either. The `mov_text` track is kept
too (costs nothing, still helps players that do support it, e.g. VLC), but
burning in is what actually makes captions visible everywhere with no extra
manual step. Caption styling (font/size/color) is a disclosed "good enough for
v1" choice, not tuned per output resolution.

The image is looped at a low framerate (it never changes) to keep file size sane
for long-form audio — `-framerate` must be given on the *input* side (before the
image `-i`), not just the output, or ffmpeg generates frames at its default rate
internally before downsampling, doing far more encoding work than necessary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

VIDEO_FRAMERATE = 1
SUBTITLE_STYLE = (
    "FontName=DejaVu Sans,FontSize=28,PrimaryColour=&HFFFFFF&,"
    "OutlineColour=&H000000&,BorderStyle=1,Outline=2,MarginV=40"
)


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({' '.join(args)}):\n{result.stderr}")


def render_video(image_path: Path, audio_path: Path, srt_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-loop", "1",
            "-framerate", str(VIDEO_FRAMERATE),
            "-i", str(image_path),
            "-i", str(audio_path),
            "-i", str(srt_path),
            "-map", "0:v",
            "-map", "1:a",
            "-map", "2:s",
            # scale=trunc(iw/2)*2:trunc(ih/2)*2 first: yuv420p's 2x2 chroma
            # subsampling requires even width AND height, but an uploaded
            # background image is user-supplied and often isn't (confirmed the
            # hard way: libx264 "width not divisible by 2" on a real 1671x941
            # image). Rounds each dimension down by at most 1px — imperceptible
            # for a static background.
            "-vf", f"scale=trunc(iw/2)*2:trunc(ih/2)*2,subtitles={srt_path}:force_style='{SUBTITLE_STYLE}'",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-c:s", "mov_text",
            "-shortest",
            str(out_path),
        ]
    )
    return out_path
