"""Reference-sample resolution per language. See spec section 8.

    voices/geo.es.wav   ->  used for Spanish
    voices/geo.en.wav   ->  used for English
    voices/geo.pt.wav   ->  used for Portuguese
    voices/geo.wav      ->  fallback for any language with no specific sample

`--voice voices/geo.wav` selects the *family*; this module resolves the
per-language file and falls back to the bare name. The caller should log
whichever sample was actually used — when one language sounds off, that's
the first thing to check.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_voice(voice_family: Path | None, lang: str) -> Path | None:
    if voice_family is None:
        return None

    per_lang = voice_family.with_name(f"{voice_family.stem}.{lang}{voice_family.suffix}")

    if per_lang.exists():
        logger.info("voices[%s]: using per-language sample %s", lang, per_lang)
        return per_lang
    if voice_family.exists():
        logger.info("voices[%s]: no per-language sample (%s), falling back to %s", lang, per_lang.name, voice_family)
        return voice_family

    logger.warning(
        "voices[%s]: neither %s nor %s exists — the engine's default voice will be used",
        lang, per_lang, voice_family,
    )
    return None
