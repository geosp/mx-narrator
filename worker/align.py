"""Caption re-timing via forced alignment — see design.md's Decisions.

Runs AFTER the caption text is already trusted (a clean `correctness_check`
pass, or the user's own manual corrections in SrtReview) to re-time each SRT
entry's start/end to the exact word boundaries CTC forced alignment finds in
the real audio, instead of relying on Whisper's own segment timestamps —
which can go stale after a hand-edit, since Whisper originally timed the OLD
wording, not the corrected one.

Deliberately NOT used for correctness verification: forced alignment assumes
the given text is correct and just times it. Confirmed empirically on real
audio that it's blind to a dropped word (the aligner silently absorbs the
missing word's audio into the neighboring words' boundaries — no score
anomaly at all), so it cannot replace `worker/diff.py`'s independent,
ASR-based check. This module only ever runs on text `correctness_check` (or
the user) has already approved.

Best-effort by design: any failure or word-count mismatch between the SRT
text and the aligner's output leaves srt_path untouched rather than risk
corrupting caption sync — this is a quality polish step, not a required one.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import srt
import torch
from ctc_forced_aligner import (
    generate_emissions,
    get_alignments,
    get_spans,
    load_alignment_model,
    load_audio,
    postprocess_results,
    preprocess_text,
)

logger = logging.getLogger(__name__)

# ctc-forced-aligner expects ISO 639-3; the rest of this codebase uses the
# ISO 639-1 codes mx_narrator.prep.registry's LanguagePacks are keyed by.
_LANG_TO_ISO_639_3 = {"es": "spa", "en": "eng", "pt": "por"}

# Cached across calls, unlike transcribe_audio's fresh-load-per-call: model
# load is the dominant fixed cost of this otherwise ~10s operation (~5s of a
# ~13s real-episode run), and this runs once per video job on the same
# process that already keeps other state alive across activity calls.
_model_cache: dict[str, tuple] = {}


def _get_model(device: str):
    if device not in _model_cache:
        dtype = torch.float16 if device == "cuda" else torch.float32
        _model_cache[device] = load_alignment_model(device, dtype=dtype)
    return _model_cache[device]


def align_captions(audio_path: Path, lang: str, srt_path: Path) -> bool:
    """Re-times srt_path's entries in place. Returns True if alignment was
    applied, False if it was skipped and the original SRT was left as-is."""
    iso_lang = _LANG_TO_ISO_639_3.get(lang)
    if iso_lang is None:
        logger.warning("align_captions: no ISO 639-3 mapping for lang=%r, skipping", lang)
        return False

    try:
        subtitles = list(srt.parse(srt_path.read_text(encoding="utf-8")))
        if not subtitles:
            return False

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, tokenizer = _get_model(device)

        audio_waveform = load_audio(str(audio_path), model.dtype, model.device)
        emissions, stride = generate_emissions(model, audio_waveform, batch_size=8)

        full_text = " ".join(sub.content.strip() for sub in subtitles)
        tokens_starred, text_starred = preprocess_text(full_text, romanize=True, language=iso_lang)
        segments, scores, blank_token = get_alignments(emissions, tokens_starred, tokenizer)
        spans = get_spans(tokens_starred, segments, blank_token)
        word_timestamps = postprocess_results(text_starred, spans, stride, scores)
    except Exception:
        logger.exception("align_captions: alignment failed, leaving existing SRT untouched")
        return False

    # Word count must match exactly to safely re-map aligned timestamps back
    # onto each SRT entry's own boundaries — confirmed on real audio this
    # holds for clean text, but never trust it blindly on unseen input.
    entry_word_counts = [len(sub.content.split()) for sub in subtitles]
    if sum(entry_word_counts) != len(word_timestamps):
        logger.warning(
            "align_captions: word count mismatch (%d SRT words vs %d aligned words), skipping",
            sum(entry_word_counts),
            len(word_timestamps),
        )
        return False

    idx = 0
    for sub, count in zip(subtitles, entry_word_counts):
        if count == 0:
            continue
        words = word_timestamps[idx : idx + count]
        sub.start = timedelta(seconds=words[0]["start"])
        sub.end = timedelta(seconds=words[-1]["end"])
        idx += count

    srt_path.write_text(srt.compose(subtitles), encoding="utf-8")
    return True
