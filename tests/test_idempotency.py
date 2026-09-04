"""Scripts for this series arrive already hand-prepared. `prep` must not
damage them — clean input passes through essentially untouched, in every
language (spec section 6.3, acceptance criterion 9)."""

import pytest

from mx_narrator.prep import prepare
from mx_narrator.prep.langs.en import EnglishPack
from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack

ALREADY_PREPARED = {
    "es": (
        "Primera de Juan, capítulo uno, versículos uno al cuatro. "
        "Esto ya tiene dos mil veintiséis palabras preparadas de antemano."
    ),
    "en": (
        "First John, chapter one, verses one through four. "
        "This already has twenty twenty-six words prepared in advance."
    ),
    "pt": (
        "Primeira de João, capítulo um, versículos um a quatro. "
        "Isto já tem dois mil e vinte e seis palavras preparadas com antecedência."
    ),
}

PACKS = {"es": SpanishPack(), "en": EnglishPack(), "pt": PortuguesePack()}


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_expand_pipeline_is_idempotent(lang):
    pack = PACKS[lang]
    text = ALREADY_PREPARED[lang]

    once = pack.expand_abbreviations(pack.expand_numbers(pack.expand_scripture(text)))
    twice = pack.expand_abbreviations(pack.expand_numbers(pack.expand_scripture(once)))

    assert once == text, f"{lang}: already-prepared text was altered:\n  {text!r}\n  {once!r}"
    assert twice == once


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_full_prepare_is_idempotent_on_clean_prose(lang):
    text = ALREADY_PREPARED[lang]
    first = prepare(text, lang).full_text
    second = prepare(first, lang).full_text
    assert first == second
