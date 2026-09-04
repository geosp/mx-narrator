"""English language pack.

Decimal separator is a dot and thousands separator is a comma — inverted
relative to Spanish and Portuguese (spec section 11's "inverted decimal
separators" trap). This pack owns its own 66-book abbreviation table; see
`_shared.py` for why it is never shared with the other packs.
"""

from __future__ import annotations

import logging
import re

from num2words import num2words

from mx_narrator.prep.langs._shared import (
    ScriptureWords,
    expand_scripture_generic,
    generic_sanity_checks,
    split_into_sentences,
)

logger = logging.getLogger(__name__)

BOOK_TABLE: dict[str, str] = {
    # Pentateuch
    "Gen": "Genesis",
    "Ex": "Exodus", "Exod": "Exodus",
    "Lev": "Leviticus",
    "Num": "Numbers",
    "Deut": "Deuteronomy",
    # Historical
    "Josh": "Joshua",
    "Judg": "Judges",
    "Ruth": "Ruth",
    "Sam": "Samuel",
    "Kgs": "Kings",
    "Chr": "Chronicles",
    "Ezra": "Ezra",
    "Neh": "Nehemiah",
    "Esth": "Esther",
    # Poetic
    "Job": "Job",
    "Ps": "Psalm", "Psa": "Psalm",
    "Prov": "Proverbs",
    "Eccl": "Ecclesiastes",
    "Song": "Song of Solomon",
    # Major prophets
    "Isa": "Isaiah",
    "Jer": "Jeremiah",
    "Lam": "Lamentations",
    "Ezek": "Ezekiel",
    "Dan": "Daniel",
    # Minor prophets
    "Hos": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obad": "Obadiah",
    "Jonah": "Jonah",
    "Mic": "Micah",
    "Nah": "Nahum",
    "Hab": "Habakkuk",
    "Zeph": "Zephaniah",
    "Hag": "Haggai",
    "Zech": "Zechariah",
    "Mal": "Malachi",
    # Gospels and Acts
    "Matt": "Matthew",
    "Mark": "Mark",
    "Luke": "Luke",
    "Jn": "John",
    "Acts": "Acts",
    # Pauline epistles
    "Rom": "Romans",
    "Cor": "Corinthians",
    "Gal": "Galatians",
    "Eph": "Ephesians",
    "Phil": "Philippians",
    "Col": "Colossians",
    "Thess": "Thessalonians",
    "Tim": "Timothy",
    "Titus": "Titus",
    "Phlm": "Philemon",
    # General epistles and Revelation
    "Heb": "Hebrews",
    "Jas": "James",
    "Pet": "Peter",
    "Jude": "Jude",
    "Rev": "Revelation",
}
# Scripts naturally sometimes spell the book name out in full ("1 John
# 1:1-4") instead of abbreviating it ("1 Jn 1:1-4"). Without this, the full
# name silently fails to match at all, falls through to generic number
# expansion, and produces garbled output — with no warning, since by the
# time sanity_checks runs the digits are already words. Let every full name
# match itself too.
BOOK_TABLE.update({name: name for name in set(BOOK_TABLE.values()) if name not in BOOK_TABLE})

WORDS = ScriptureWords(
    chapter_word="chapter",
    verse_word="verse",
    verses_word="verses",
    range_connector="through",
    numeral_words={1: "First", 2: "Second", 3: "Third"},
)


def _n2w(n: int) -> str:
    return num2words(n, lang="en")


_NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b")

_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bDr\."), "Doctor"),
    (re.compile(r"\bMrs\."), "Missus"),
    (re.compile(r"\bMr\."), "Mister"),
    (re.compile(r"\bMs\."), "Miz"),
    (re.compile(r"\be\.g\."), "for example"),
    (re.compile(r"\bi\.e\."), "that is"),
    (re.compile(r"\betc\."), "et cetera"),
    (re.compile(r"\bvs\."), "versus"),
    # Era markers must lose their internal periods before sentence splitting,
    # or "... 90 A.D. reminds" gets misread as two sentences.
    (re.compile(r"\bB\.C\."), "B C"),
    (re.compile(r"\bA\.D\."), "A D"),
]

_BREAK_WORDS = ("and", "but", "because", "which", "when", "although", "so", "that")


class EnglishPack:
    code = "en"
    num2words_locale = "en"
    kokoro_voice = "am_puck"

    def expand_scripture(self, text: str) -> str:
        return expand_scripture_generic(text, book_table=BOOK_TABLE, words=WORDS, num2words_fn=_n2w)

    def expand_numbers(self, text: str) -> str:
        def replace_number(m: re.Match) -> str:
            raw = m.group(0)
            if "." in raw:
                int_part, dec_part = raw.split(".", 1)
                int_clean = int_part.replace(",", "")
                spoken_int = _n2w(int(int_clean))
                spoken_dec = " ".join(_n2w(int(d)) for d in dec_part)
                return f"{spoken_int} point {spoken_dec}"
            int_clean = raw.replace(",", "")
            n = int(int_clean)
            if "," not in raw and len(int_clean) == 4 and 1500 <= n <= 2099:
                logger.warning(
                    "en: read '%s' as a year (%s) rather than a plain count — "
                    "rewrite with a decimal or thousands separator if that's wrong",
                    raw, num2words(n, lang="en", to="year"),
                )
                return num2words(n, lang="en", to="year")
            return _n2w(n)

        return _NUMBER_RE.sub(replace_number, text)

    def expand_abbreviations(self, text: str) -> str:
        for pattern, replacement in _ABBREVIATIONS:
            text = pattern.sub(replacement, text)
        return text

    def split_sentences(self, text: str) -> list[str]:
        return split_into_sentences(text, max_words=25, break_words=_BREAK_WORDS)

    def sanity_checks(self, text: str) -> list[str]:
        return generic_sanity_checks(text, max_words=25)
