"""Code -> LanguagePack. The only place that instantiates packs."""

from __future__ import annotations

from mx_narrator.prep.base import LanguagePack
from mx_narrator.prep.langs.en import EnglishPack
from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack

_PACKS: dict[str, LanguagePack] = {
    "es": SpanishPack(),
    "en": EnglishPack(),
    "pt": PortuguesePack(),
}


def get_pack(code: str) -> LanguagePack:
    try:
        return _PACKS[code]
    except KeyError:
        raise ValueError(
            f"Unknown language code: {code!r}. Supported: {', '.join(sorted(_PACKS))}"
        ) from None


def available_languages() -> list[str]:
    return sorted(_PACKS)
