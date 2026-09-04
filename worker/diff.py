"""Exact-text correctness check — see design.md's Decisions.

Plain function, no Temporal import (mirrors `worker/llm.py`/`worker/transcription.py`)
— `activities.py` wraps this with `@activity.defn`.

The single highest-leverage correctness decision here: mx_narrator's own prepared text
(the `expected_text` this compares against) already has numbers spelled out as words
(`prepare()`'s own `expand_numbers()` step already ran on it) — but Whisper's raw
transcript writes spoken numbers back as digits. Left unhandled, every chapter:verse
reference and enumerated number would show up as a spurious mismatch. Fix: run the
same per-language `expand_numbers()` over each transcribed word before comparing, so
both sides share the same canonical "numbers as words" form.
"""

from __future__ import annotations

import difflib
import re

from mx_narrator.prep.registry import get_pack
from worker.types import CorrectnessCheckResult, Mismatch, WordTiming

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Acute/grave/circumflex/diaeresis accent marks fold to their base vowel — these
# mark stress/pronunciation, not a different letter, and Whisper is inconsistent
# about reproducing them ("qué"/"que", "aún"/"aun", "pódcast"/"podcast" are the
# same word for this comparison's purposes). Deliberately NOT folded: ñ and ç —
# those are distinct letters in Spanish/Portuguese, not accented vowels, and
# folding them would hide real differences (e.g. "año" vs "ano" mean different
# things).
_ACCENT_FOLD: dict[int, str] = {}
for _base, _accented in {"a": "áàâäã", "e": "éèêë", "i": "íìîï", "o": "óòôöõ", "u": "úùûü"}.items():
    for _ch in _accented:
        _ACCENT_FOLD[ord(_ch)] = _base
        _ACCENT_FOLD[ord(_ch.upper())] = _base.upper()

# A handful of Spanish words with two RAE-valid spellings — one word or two —
# that mean the same thing but tokenize differently, so word-level diffing sees
# them as unrelated. Confirmed real source of false-positive mismatches: a
# script using "adonde" against a transcript that rendered it as "a donde".
# Merged to the one-word canonical form on both sides before diffing.
_SPANISH_SPLIT_WORD_MERGES: dict[tuple[str, str], str] = {
    ("a", "donde"): "adonde",
    ("por", "que"): "porque",
    ("con", "que"): "conque",
    ("si", "no"): "sino",
    ("a", "parte"): "aparte",
}


def _normalize_text(text: str) -> list[str]:
    folded = _PUNCTUATION_RE.sub(" ", text.lower()).translate(_ACCENT_FOLD)
    return folded.split()


def _merge_split_words(
    words: list[str], times: list[float] | None, lang: str
) -> tuple[list[str], list[float] | None]:
    if lang != "es":
        return words, times
    merged_words: list[str] = []
    merged_times: list[float] | None = [] if times is not None else None
    i = 0
    while i < len(words):
        pair = (words[i], words[i + 1]) if i + 1 < len(words) else None
        if pair in _SPANISH_SPLIT_WORD_MERGES:
            merged_words.append(_SPANISH_SPLIT_WORD_MERGES[pair])
            if merged_times is not None:
                merged_times.append(times[i])
            i += 2
        else:
            merged_words.append(words[i])
            if merged_times is not None:
                merged_times.append(times[i])
            i += 1
    return merged_words, merged_times


def _normalize_transcript_words(words: list[WordTiming], pack) -> tuple[list[str], list[float]]:
    out_words: list[str] = []
    out_times: list[float] = []
    for w in words:
        expanded = pack.expand_numbers(w.word)
        for sub_word in _normalize_text(expanded):
            out_words.append(sub_word)
            out_times.append(w.start)
    return out_words, out_times


def check_correctness(expected_text: str, lang: str, words: list[WordTiming]) -> CorrectnessCheckResult:
    pack = get_pack(lang)
    expected_words = _normalize_text(expected_text)
    expected_words, _ = _merge_split_words(expected_words, None, lang)
    actual_words, actual_times = _normalize_transcript_words(words, pack)
    actual_words, actual_times = _merge_split_words(actual_words, actual_times, lang)

    matcher = difflib.SequenceMatcher(a=expected_words, b=actual_words, autojunk=False)
    mismatches: list[Mismatch] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        approx_time = actual_times[j1] if j1 < len(actual_times) else (actual_times[-1] if actual_times else 0.0)
        mismatches.append(
            Mismatch(
                expected=" ".join(expected_words[i1:i2]),
                actual=" ".join(actual_words[j1:j2]),
                approx_time=approx_time,
            )
        )

    return CorrectnessCheckResult(status="mismatch" if mismatches else "pass", mismatches=mismatches)
