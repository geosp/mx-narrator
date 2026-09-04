"""GPU-dependent tests, skipped by default. Run with `uv run pytest -m slow`.

Spec section 11: "Write a test that synthesizes the same text twice with the
same seed and asserts the audio is identical." This is the direct proof that
--seed actually pins reproducibility, which is the fix for the cross-chunk
voice-drift trap described in the same section.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

pytestmark = pytest.mark.slow

requires_cuda = pytest.mark.skipif(not torch.cuda.is_available(), reason="requires a CUDA GPU")


@pytest.fixture(scope="module")
def engine():
    from mx_narrator.engines.chatterbox import ChatterboxEngine

    eng = ChatterboxEngine()
    eng.load(device="cuda")
    eng.prepare_voice(None, exaggeration=0.3)
    return eng


@requires_cuda
def test_same_seed_produces_identical_audio(engine, tmp_path):
    import numpy as np
    import soundfile as sf

    text = "Este es un texto de prueba para verificar la reproducibilidad."
    out1, out2 = tmp_path / "a.wav", tmp_path / "b.wav"

    engine.synth(text, "es", out1, seed=42)
    engine.synth(text, "es", out2, seed=42)

    audio1, _ = sf.read(str(out1))
    audio2, _ = sf.read(str(out2))
    assert np.array_equal(audio1, audio2)
