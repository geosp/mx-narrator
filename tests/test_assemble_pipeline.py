"""End-to-end plumbing test for chunk -> synth -> assemble, using a fake
engine (sine-wave WAVs) instead of a real TTS model. This exercises the
ffmpeg concat/loudnorm/encode/tag path without needing a GPU."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from mutagen.mp3 import MP3

from mx_narrator.assemble import AssembleSegment, assemble_script, pause_ms_for_transition
from mx_narrator.chunk import chunk_prepared_script
from mx_narrator.engines.base import SynthEngine
from mx_narrator.prep import prepare

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
SAMPLE_RATE = 24000


class FakeEngine(SynthEngine):
    name = "fake"

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    def load(self, *, device: str) -> None:
        pass

    def prepare_voice(self, voice_path, *, exaggeration: float) -> None:
        pass

    def synth(self, text: str, lang: str, out_path: Path, **opts) -> None:
        duration_s = max(0.2, len(text) / 40)
        t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
        tone = 0.1 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), tone, SAMPLE_RATE)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_pause_rules_match_spec_section_11():
    assert pause_ms_for_transition(None, "paragraph") == 0
    assert pause_ms_for_transition("paragraph", "paragraph") == 600
    assert pause_ms_for_transition("paragraph", "heading") == 1200
    assert pause_ms_for_transition("heading", "paragraph") == 1200
    assert pause_ms_for_transition("paragraph", "quote") == 900
    assert pause_ms_for_transition("quote", "paragraph") == 900


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_full_pipeline_produces_tagged_mp3(tmp_path):
    raw = (
        "# Encabezado\n\n"
        "Primera oración del párrafo uno. Segunda oración del mismo párrafo.\n\n"
        "> Una cita de las Escrituras que merece una pausa antes y después.\n\n"
        "Párrafo final del pasaje."
    )
    script = prepare(raw, "es")
    chunks = chunk_prepared_script(script, max_chars=60)
    assert len(chunks) > 1

    engine = FakeEngine()
    chunk_dir = tmp_path / "chunks"
    segments = []
    for i, chunk in enumerate(chunks):
        p = chunk_dir / f"chunk_{i:04d}.wav"
        engine.synth(chunk.text, "es", p)
        segments.append(AssembleSegment(wav_path=p, block_kind=chunk.block_kind, block_index=chunk.block_index))

    out_path = tmp_path / "out" / "test-unit.es.mp3"
    assemble_script(
        segments,
        out_path,
        sample_rate=SAMPLE_RATE,
        speed=0.95,
        audio_format="mp3",
        normalize=True,
        id3=dict(
            title="Test Unit (es)", artist="Narrator", album="Test Series", track=1, lang="es",
            extra={"cfg_weight": 0.3, "exaggeration": 0.3, "engine": "chatterbox", "seed": 0},
        ),
    )

    assert out_path.exists()
    audio = MP3(str(out_path))
    assert audio.info.length > 1.0  # several chunks + pauses, should add up to more than a second
    assert audio.tags["TIT2"].text[0] == "Test Unit (es)"
    assert audio.tags["TXXX:cfg_weight"].text[0] == "0.3"
    assert audio.tags["TXXX:exaggeration"].text[0] == "0.3"
    assert audio.tags["TXXX:engine"].text[0] == "chatterbox"
    assert audio.tags["TLAN"].text[0] == "es"
    assert audio.tags["TALB"].text[0] == "Test Series"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_draft_mode_skips_loudness_and_tagging(tmp_path):
    engine = FakeEngine()
    p = tmp_path / "chunk_0000.wav"
    engine.synth("Texto corto.", "es", p)
    segments = [AssembleSegment(wav_path=p, block_kind="paragraph", block_index=0)]

    out_path = tmp_path / "draft.wav"
    assemble_script(
        segments, out_path,
        sample_rate=SAMPLE_RATE, speed=1.0,
        audio_format="wav", normalize=False, id3=None,
    )
    assert out_path.exists()
    assert out_path.suffix == ".wav"
