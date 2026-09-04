"""render_job()'s ID3 title/artist handling.

The title tag should reflect the actual episode (the script's own first
line), not the filename-derived unit id — with a --title override for when
that heuristic picks a bad line. See batch.py's _derive_title_from_script.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mx_narrator.batch import RenderJob, _derive_title_from_script, render_job
from mx_narrator.engines.base import SynthEngine

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def test_derive_title_uses_first_non_blank_line():
    raw = "\n\n  Reflexión 1 de Juan 1:1-4  \n\nLa Vida se manifestó...\n"
    assert _derive_title_from_script(raw) == "Reflexión 1 de Juan 1:1-4"


def test_derive_title_strips_markdown_heading_marker():
    raw = "# Introducción\n\nTexto del párrafo."
    assert _derive_title_from_script(raw) == "Introducción"


def test_derive_title_blank_file_returns_empty_string():
    assert _derive_title_from_script("\n\n   \n") == ""


class FakeEngine(SynthEngine):
    name = "fake"

    @property
    def sample_rate(self) -> int:
        return 24000

    def load(self, *, device: str) -> None:
        pass

    def prepare_voice(self, voice_path, *, exaggeration: float) -> None:
        pass

    def synth(self, text: str, lang: str, out_path: Path, **opts) -> None:
        import numpy as np
        import soundfile as sf

        tone = 0.1 * np.sin(2 * np.pi * 220 * np.linspace(0, 0.3, int(24000 * 0.3), endpoint=False)).astype(
            np.float32
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), tone, 24000)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_render_job_title_defaults_to_script_first_line(tmp_path):
    from mutagen.mp3 import MP3

    script_path = tmp_path / "unit-1.es.txt"
    script_path.write_text("Reflexión 1 de Juan 1:1-4\n\nLa Vida se manifestó.\n", encoding="utf-8")
    out_path = tmp_path / "out" / "unit-1.es.mp3"

    job = RenderJob(unit_id="unit-1", lang="es", script_path=script_path, out_path=out_path)
    result = render_job(job, engine=FakeEngine())

    assert result.ok, result.message
    audio = MP3(str(out_path))
    assert audio.tags["TIT2"].text[0] == "Reflexión 1 de Juan 1:1-4 (es)"
    assert audio.tags["TPE1"].text[0] == "Giovanni Fajardo"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_render_job_title_override(tmp_path):
    from mutagen.mp3 import MP3

    script_path = tmp_path / "unit-1.es.txt"
    script_path.write_text("Reflexión 1 de Juan 1:1-4\n\nLa Vida se manifestó.\n", encoding="utf-8")
    out_path = tmp_path / "out" / "unit-1.es.mp3"

    job = RenderJob(
        unit_id="unit-1", lang="es", script_path=script_path, out_path=out_path, title="Custom Title"
    )
    result = render_job(job, engine=FakeEngine())

    assert result.ok, result.message
    audio = MP3(str(out_path))
    assert audio.tags["TIT2"].text[0] == "Custom Title (es)"
