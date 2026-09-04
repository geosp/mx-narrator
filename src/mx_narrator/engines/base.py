"""Shared engine interface: `synth(text, lang, out_path, **opts)`.

Both engines write 16-bit PCM WAV to `out_path`; `assemble.py` concatenates,
normalizes, and encodes afterward. Speed is deliberately *not* an engine
concern — see `assemble.py` for why it's applied once, uniformly, via
ffmpeg's `atempo`, rather than per-engine (Chatterbox has no native speed
control; applying it only at the assembly stage keeps the two engines'
output comparable).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SynthEngine(ABC):
    name: str

    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @abstractmethod
    def load(self, *, device: str) -> None:
        """Load model weights onto `device`. Called once per process."""

    @abstractmethod
    def prepare_voice(self, voice_path: Path | None, *, exaggeration: float) -> None:
        """Compute and cache the reference-voice conditioning once.

        Every subsequent `synth()` call must reuse this cached conditioning
        rather than recomputing it from `voice_path` — recomputing per call
        is exactly what causes the timbre drift described in spec section 11.
        """

    @abstractmethod
    def synth(self, text: str, lang: str, out_path: Path, **opts) -> None:
        """Synthesize `text` in `lang`, writing PCM WAV to `out_path`.

        `opts` may include `seed`, `exaggeration`, `cfg_weight` — engines
        ignore keys they don't understand.
        """
