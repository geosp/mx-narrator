"""Every worked example from spec section 7, verbatim, one table per language.

Acceptance criterion 2: `--dry-run` correctly expands every scripture
reference in the section 7 tables, each language against its own table.
"""

import pytest

from mx_narrator.prep.langs.en import EnglishPack
from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack

ES_TABLE = [
    ("1 Jn 1:1-4", "Primera de Juan, capítulo uno, versículos uno al cuatro"),
    ("Jn 1:1", "Juan, capítulo uno, versículo uno"),
    ("Ro 8:28", "Romanos ocho, veintiocho"),
    ("Sal 23", "Salmo veintitrés"),
    ("1 Co 13", "Primera de Corintios trece"),
    ("Heb 12:18-24", "Hebreos, capítulo doce, versículos dieciocho al veinticuatro"),
    ("vv. 4-6", "versículos cuatro al seis"),
    ("v. 2", "versículo dos"),
]

EN_TABLE = [
    ("1 Jn 1:1-4", "First John, chapter one, verses one through four"),
    ("Jn 1:1", "John, chapter one, verse one"),
    ("Rom 8:28", "Romans eight, twenty-eight"),
    ("Ps 23", "Psalm twenty-three"),
    ("1 Cor 13", "First Corinthians thirteen"),
    ("Heb 12:18-24", "Hebrews, chapter twelve, verses eighteen through twenty-four"),
    ("vv. 4-6", "verses four through six"),
    ("v. 2", "verse two"),
]

PT_TABLE = [
    ("1 Jo 1:1-4", "Primeira de João, capítulo um, versículos um a quatro"),
    ("Jo 1:1", "João, capítulo um, versículo um"),
    ("Rm 8:28", "Romanos oito, vinte e oito"),
    ("Sl 23", "Salmo vinte e três"),
    ("1 Co 13", "Primeira de Coríntios treze"),
    ("Hb 12:18-24", "Hebreus, capítulo doze, versículos dezoito a vinte e quatro"),
    ("vv. 4-6", "versículos quatro a seis"),
    ("v. 2", "versículo dois"),
]


@pytest.mark.parametrize("written,spoken", ES_TABLE)
def test_spanish_scripture_table(written, spoken):
    assert SpanishPack().expand_scripture(written) == spoken


@pytest.mark.parametrize("written,spoken", EN_TABLE)
def test_english_scripture_table(written, spoken):
    assert EnglishPack().expand_scripture(written) == spoken


@pytest.mark.parametrize("written,spoken", PT_TABLE)
def test_portuguese_scripture_table(written, spoken):
    assert PortuguesePack().expand_scripture(written) == spoken


def test_ambiguity_rule_numeral_prefix_means_epistle():
    """Section 7.4: numeral prefix -> epistle, bare -> Gospel. No further guessing."""
    es = SpanishPack()
    assert "Juan" in es.expand_scripture("Jn 3:16")
    assert "Primera de Juan" in es.expand_scripture("1 Jn 3:16")


def test_spelled_out_book_name_expands_same_as_abbreviation():
    """A script that writes "1 Juan 1:1-4" instead of "1 Jn 1:1-4" must not
    silently fail to match — that leaves raw digits for the generic number
    expander, which produces garbled text like "Juan uno:uno-cuatro" with
    no warning (the sanity check only looks for digit:digit, which is
    already gone by the time it runs)."""
    es, en, pt = SpanishPack(), EnglishPack(), PortuguesePack()

    assert es.expand_scripture("1 Juan 1:1-4") == es.expand_scripture("1 Jn 1:1-4")
    assert es.expand_scripture("Juan 1:1") == es.expand_scripture("Jn 1:1")
    assert "uno:uno" not in es.expand_numbers(es.expand_scripture("1 Juan 1:1-4"))

    assert en.expand_scripture("1 John 1:1-4") == en.expand_scripture("1 Jn 1:1-4")
    assert pt.expand_scripture("1 João 1:1-4") == pt.expand_scripture("1 Jo 1:1-4")


def test_full_book_names_still_isolated_per_language():
    """The self-mapping addition must not reopen the cross-language
    contamination section 5 warns about."""
    from mx_narrator.prep.langs.en import BOOK_TABLE as EN
    from mx_narrator.prep.langs.es import BOOK_TABLE as ES

    assert "John" in EN and "John" not in ES
    assert "Juan" in ES and "Juan" not in EN
