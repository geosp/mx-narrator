"""Kokoro engine — fast drafts for proofing a script. See spec section 3.

No voice cloning: `--voice` is accepted for interface parity with Chatterbox
but ignored here (with a warning), since Kokoro only offers built-in preset
voices. The preset actually used comes from the language pack's
`kokoro_voice` and must be passed in via `synth(..., voice=...)` by the
caller — Kokoro's notion of "voice" (a name) is fundamentally different from
Chatterbox's (a cloned reference sample), so it doesn't fit the same
`prepare_voice(path)` shape.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from mx_narrator.engines.base import SynthEngine

logger = logging.getLogger(__name__)

# Kokoro's own single-letter language codes.
_LANG_CODE = {"es": "e", "en": "a", "pt": "p"}
SAMPLE_RATE = 24000


class KokoroEngine(SynthEngine):
    name = "kokoro"

    def __init__(self) -> None:
        self._pipelines: dict[str, object] = {}
        self._device = "cpu"

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    def load(self, *, device: str) -> None:
        # Kokoro pipelines are created lazily per language in _pipeline_for(),
        # since each one is pinned to a single lang_code.
        self._device = device

    def prepare_voice(self, voice_path: Path | None, *, exaggeration: float) -> None:
        if voice_path is not None:
            logger.warning(
                "kokoro: has no voice cloning — ignoring --voice %s, using the "
                "built-in per-language preset voice instead",
                voice_path,
            )

    def _pipeline_for(self, lang: str):
        code = _LANG_CODE.get(lang)
        if code is None:
            raise ValueError(f"kokoro: no preset language mapping for {lang!r}")
        if code not in self._pipelines:
            from kokoro import KPipeline

            try:
                self._pipelines[code] = KPipeline(lang_code=code, device=self._device)
            except TypeError:
                # Some Kokoro versions don't accept `device` — VERIFY at install time.
                self._pipelines[code] = KPipeline(lang_code=code)
        return self._pipelines[code]

    def synth(self, text: str, lang: str, out_path: Path, **opts) -> None:
        voice = opts.get("voice")
        if not voice:
            raise ValueError("kokoro: synth() requires opts['voice'] (a Kokoro preset voice name)")

        pipeline = self._pipeline_for(lang)
        segments = [audio for _, _, audio in pipeline(text, voice=voice, speed=1.0)]
        if not segments:
            raise RuntimeError(f"kokoro: produced no audio for text: {text[:60]!r}")
        full = segments[0] if len(segments) == 1 else np.concatenate(segments)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), full, SAMPLE_RATE)
