"""Language resolution — fail loud. See spec section 9.

Resolve in order: the `--lang` flag, then the filename suffix, then
content-based detection. If detection is not confident, error out rather
than guessing — guessing wrong doesn't produce a slight accent, it applies
the wrong scripture table and the wrong number locale, silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from mx_narrator.prep.registry import available_languages

_KNOWN_LANGS = set(available_languages())

# Lightweight, dependency-free stopword markers. Deliberately conservative:
# this path only exists as a last resort when neither --lang nor the
# filename suffix settled the question, and a wrong guess is worse than an
# error (see module docstring).
_MARKERS: dict[str, set[str]] = {
    "es": {
        "el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "es",
        "por", "para", "con", "su", "se", "no", "del", "al", "como", "más",
    },
    "en": {
        "the", "a", "an", "of", "and", "in", "to", "is", "that", "for",
        "with", "as", "on", "was", "it", "this", "we", "you", "are",
    },
    "pt": {
        "o", "a", "os", "as", "de", "que", "e", "em", "um", "uma", "é",
        "por", "para", "com", "se", "não", "do", "da", "como", "mais",
    },
}
_MIN_MARKER_HITS = 5
_MIN_MARGIN_RATIO = 1.5
_MIN_WORDS = 20


class LanguageResolutionError(Exception):
    pass


def filename_suffix_language(path: Path) -> str | None:
    parts = path.stem.split(".")
    if len(parts) >= 2 and parts[-1] in _KNOWN_LANGS:
        return parts[-1]
    return None


def detect_from_content(text: str) -> str | None:
    words = re.findall(r"[a-zA-zÀ-ÿ]+", text.lower())
    if len(words) < _MIN_WORDS:
        return None

    scores = {lang: sum(1 for w in words if w in markers) for lang, markers in _MARKERS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_lang, top_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0

    if top_score < _MIN_MARKER_HITS or top_score < runner_up_score * _MIN_MARGIN_RATIO:
        return None
    return top_lang


def resolve_language(path: Path, *, lang_flag: str | None = None, text: str | None = None) -> str:
    if lang_flag:
        if lang_flag not in _KNOWN_LANGS:
            raise LanguageResolutionError(
                f"Unknown --lang {lang_flag!r}. Supported: {', '.join(sorted(_KNOWN_LANGS))}"
            )
        return lang_flag

    suffix_lang = filename_suffix_language(path)
    if suffix_lang is not None:
        return suffix_lang

    content = text if text is not None else path.read_text(encoding="utf-8")
    detected = detect_from_content(content)
    if detected is not None:
        return detected

    raise LanguageResolutionError(
        f"Cannot determine the language of {path}: no --lang flag, the filename "
        f"isn't <unit>.<lang>.txt, and content-based detection wasn't confident. "
        f"Refusing to guess — the wrong language applies the wrong scripture "
        f"and number tables, silently. Rename the file or pass --lang explicitly."
    )
