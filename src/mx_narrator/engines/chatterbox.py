"""Chatterbox Multilingual (V3) engine — the default. See spec section 3.

Voice conditioning is computed once in `prepare_voice()` via the model's own
`prepare_conditionals()` (which caches the embedding on the model instance)
and every `synth()` call after that omits `audio_prompt_path` entirely, so
Chatterbox reuses the cached conditioning instead of recomputing it from the
reference file on every chunk. That is the fix for cross-chunk voice drift.

Pinned to V3 via a specific git commit in `pyproject.toml`'s `[tool.uv.sources]`
(not yet on the PyPI release) — chosen over V2 after a direct, evidenced
comparison: V2's `AlignmentStreamAnalyzer` forces an abrupt EOS override on
the large majority of chunks (audible as a chirp/glitch), which V3's
generation loop doesn't have at all anymore. V3's own `generate()` instead
unconditionally drops the final speech token's audio — its own comment:
"it is emitted just before EOS with degraded attention and decodes to
~40ms of noise" — a precise, native fix, so no equivalent trimming is done
here.

Traded away going from V2 to V3: V2's analyzer was also our only signal for
detecting a genuine repetition/hallucination loop, which drove an automatic
retry-with-a-different-seed. That whole mechanism (and a matching tail-trim
for the chirp) lived in this file until this V3 switch — removed because it
had become dead code (V3 never emits the log lines it watched for), not
because it stopped mattering. V3 still only leans on a standard
`repetition_penalty` logits processor with no escalation or retry if a loop
happens anyway. That's a real, currently-unmitigated gap — deliberately not
rebuilt from scratch until it's shown to be a real problem in practice
(V3 is specifically trained to need it less).
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

import numpy as np
import torch
import torchaudio

from mx_narrator.engines.base import SynthEngine

logger = logging.getLogger(__name__)

DEFAULT_T3_MODEL = "v3"  # see the module docstring and pyproject.toml's uv.sources pin
DEFAULT_EXAGGERATION = 0.3  # spec: default LOW — devotional material, not promotional
DEFAULT_CFG_WEIGHT = 0.5
DEFAULT_SEED = 0
DEFAULT_REPETITION_PENALTY = 1.2  # Chatterbox's own default


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class ChatterboxEngine(SynthEngine):
    name = "chatterbox"

    def __init__(self) -> None:
        self._model = None
        self._voice_path: Path | None = None

    @property
    def sample_rate(self) -> int:
        if self._model is None:
            raise RuntimeError("ChatterboxEngine.load() must be called before use")
        return self._model.sr

    def load(self, *, device: str) -> None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        logger.info("chatterbox: loading multilingual model (t3_model=%s) on %s", DEFAULT_T3_MODEL, device)
        self._model = ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model=DEFAULT_T3_MODEL)

    def prepare_voice(self, voice_path: Path | None, *, exaggeration: float = DEFAULT_EXAGGERATION) -> None:
        if self._model is None:
            raise RuntimeError("ChatterboxEngine.load() must be called before use")
        if voice_path is None:
            logger.warning("chatterbox: no reference voice given — using the model's built-in default voice")
            self._voice_path = None
            return
        logger.info("chatterbox: computing voice conditioning once from %s", voice_path)
        self._model.prepare_conditionals(str(voice_path), exaggeration=exaggeration)
        self._voice_path = voice_path

    def synth(self, text: str, lang: str, out_path: Path, **opts) -> None:
        if self._model is None:
            raise RuntimeError("ChatterboxEngine.load() must be called before use")

        seed = opts.get("seed", DEFAULT_SEED)
        exaggeration = opts.get("exaggeration", DEFAULT_EXAGGERATION)
        cfg_weight = opts.get("cfg_weight", DEFAULT_CFG_WEIGHT)
        repetition_penalty = opts.get("repetition_penalty", DEFAULT_REPETITION_PENALTY)

        _set_seed(seed)
        wav = self._model.generate(
            text,
            language_id=lang,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            repetition_penalty=repetition_penalty,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(out_path), wav, self._model.sr)
