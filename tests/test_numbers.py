"""Every worked example from spec section 7's number tables, plus the
inverted-decimal-separator trap called out in section 11."""

import pytest

from mx_narrator.prep.langs.en import EnglishPack
from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack


@pytest.mark.parametrize(
    "written,spoken",
    [
        ("2026", "dos mil veintiséis"),
        ("3,5", "tres coma cinco"),
        ("1.000", "mil"),
        ("1º", "primero"),
        ("1ª", "primera"),
    ],
)
def test_spanish_numbers(written, spoken):
    assert SpanishPack().expand_numbers(written) == spoken


@pytest.mark.parametrize(
    "written,spoken",
    [
        ("2026", "twenty twenty-six"),
        ("3.5", "three point five"),
        ("1,000", "one thousand"),
    ],
)
def test_english_numbers(written, spoken):
    assert EnglishPack().expand_numbers(written) == spoken


@pytest.mark.parametrize(
    "written,spoken",
    [
        ("2026", "dois mil e vinte e seis"),
        ("3,5", "três vírgula cinco"),
        ("1.000", "mil"),
    ],
)
def test_portuguese_numbers(written, spoken):
    assert PortuguesePack().expand_numbers(written) == spoken


def test_inverted_decimal_separator_is_not_shared():
    """3,5 must not mean the same thing to the English pack as to Spanish/Portuguese.

    In English, "," is a thousands separator, not a decimal point, so "3,5" is
    not a valid grouped number (a group needs exactly 3 digits) — the parser
    reads it as two separate numbers rather than silently applying Spanish's
    comma-as-decimal rule.
    """
    assert EnglishPack().expand_numbers("3,5") != SpanishPack().expand_numbers("3,5")
    assert EnglishPack().expand_numbers("3,5") == "three,five"
    assert SpanishPack().expand_numbers("3,5") == "tres coma cinco"
