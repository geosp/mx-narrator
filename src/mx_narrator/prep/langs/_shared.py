"""Shared machinery for language packs — imported only from within `prep/langs/`.

This is *not* a place for language-neutral pipeline steps (those belong in
`prep/common.py`, one level up). It exists so the three packs don't each
hand-roll the same regex-and-render plumbing around their (very different)
book tables and number words. Every language-specific fact — the book table,
the connector word, the epistle-numeral words, how numbers are spoken — is
still supplied by the calling pack.

## The spoken-reference rule

Derived from the worked examples in the spec (section 7), consistent across
all three languages:

- Chapter only, no verse (`Sal 23`, `1 Co 13`) -> short form, no "chapter" word:
  "Salmo veintitrés", "Primera de Corintios trece".
- A verse *range* (`1 Jn 1:1-4`, `Heb 12:18-24`) -> always full form, because a
  bare "Book N, A al B" is ambiguous about which number is the chapter:
  "Hebreos, capítulo doce, versículos dieciocho al veinticuatro".
- A single verse in chapter 1 (`Jn 1:1`) -> full form, because "Juan uno, uno"
  is genuinely confusing next to the numeral already used for epistle
  numbering: "Juan, capítulo uno, versículo uno".
- A single verse in any other chapter (`Ro 8:28`) -> short form:
  "Romanos ocho, veintiocho".
- A bare `v. N` / `vv. N-M` (no book/chapter, continuing a prior reference) ->
  "versículo N" / "versículos N <connector> M".
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ScriptureWords:
    chapter_word: str  # "capítulo" / "chapter"
    verse_word: str  # "versículo" / "verse"
    verses_word: str  # "versículos" / "verses"
    range_connector: str  # "al" / "through" / "a"
    numeral_words: dict[int, str]  # {1: "Primera de", 2: "Segunda de", 3: "Tercera de"}


def render_reference(
    *,
    numeral: int | None,
    book_name: str,
    chapter: int | None,
    verse_start: int | None,
    verse_end: int | None,
    words: ScriptureWords,
    num2words_fn: Callable[[int], str],
) -> str:
    if book_name:
        spoken_book = book_name if numeral is None else f"{words.numeral_words[numeral]} {book_name}"
    else:
        spoken_book = ""

    if chapter is None:
        # bare "v. N" / "vv. N-M" — no book or chapter in view
        if verse_end is not None:
            return f"{words.verses_word} {num2words_fn(verse_start)} {words.range_connector} {num2words_fn(verse_end)}"
        return f"{words.verse_word} {num2words_fn(verse_start)}"

    if verse_start is None:
        # chapter only -> short form
        return f"{spoken_book} {num2words_fn(chapter)}".strip()

    if verse_end is not None:
        # range -> always full form
        return (
            f"{spoken_book}, {words.chapter_word} {num2words_fn(chapter)}, "
            f"{words.verses_word} {num2words_fn(verse_start)} {words.range_connector} {num2words_fn(verse_end)}"
        )

    if chapter == 1:
        # single verse, chapter one -> full form (disambiguates from epistle numeral)
        return f"{spoken_book}, {words.chapter_word} {num2words_fn(chapter)}, {words.verse_word} {num2words_fn(verse_start)}"

    # single verse, any other chapter -> short form
    return f"{spoken_book} {num2words_fn(chapter)}, {num2words_fn(verse_start)}"


def build_book_pattern(book_table: dict[str, str]) -> re.Pattern:
    """Build a regex alternation from abbreviation keys, longest first.

    Longest-first ordering keeps e.g. "Jn" from shadowing a hypothetical "Jnh".
    Keys are matched case-sensitively as written in the table (books are
    proper nouns; forcing case avoids matching ordinary lowercase words).
    """
    keys = sorted(book_table.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys)
    return re.compile(
        rf"\b(?:(?P<numeral>[123])\s+)?(?P<book>{alternation})\.?\s+(?P<chapter>\d{{1,3}})"
        rf"(?::(?P<vstart>\d{{1,3}})(?:-(?P<vend>\d{{1,3}}))?)?"
    )


VERSE_ONLY_PATTERN = re.compile(
    r"\bvv?\.\s*(?P<vstart>\d{1,3})(?:-(?P<vend>\d{1,3}))?\b"
)


def expand_scripture_generic(
    text: str,
    *,
    book_table: dict[str, str],
    words: ScriptureWords,
    num2words_fn: Callable[[int], str],
) -> str:
    book_pattern = build_book_pattern(book_table)

    def replace_book_ref(m: re.Match) -> str:
        numeral = int(m.group("numeral")) if m.group("numeral") else None
        book_name = book_table[m.group("book")]
        chapter = int(m.group("chapter"))
        vstart = int(m.group("vstart")) if m.group("vstart") else None
        vend = int(m.group("vend")) if m.group("vend") else None
        return render_reference(
            numeral=numeral,
            book_name=book_name,
            chapter=chapter,
            verse_start=vstart,
            verse_end=vend,
            words=words,
            num2words_fn=num2words_fn,
        )

    text = book_pattern.sub(replace_book_ref, text)

    def replace_verse_only(m: re.Match) -> str:
        vstart = int(m.group("vstart"))
        vend = int(m.group("vend")) if m.group("vend") else None
        return render_reference(
            numeral=None,
            book_name="",
            chapter=None,
            verse_start=vstart,
            verse_end=vend,
            words=words,
            num2words_fn=num2words_fn,
        )

    text = VERSE_ONLY_PATTERN.sub(replace_verse_only, text)
    return text


_PARENTHETICAL = re.compile(r"\s*\(([^()]+)\)")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def lift_parentheticals(text: str) -> str:
    """Turn "(aside)" into its own sentence: ", aside." instead of a bracketed clause.

    The listener has no closing bracket to hear, so a parenthetical must not
    read as a subordinate clause — it becomes a short standalone sentence.
    """

    def replace(m: re.Match) -> str:
        inner = m.group(1).strip().rstrip(".")
        if not inner:
            return ""
        return f". {inner[0].upper()}{inner[1:]}."

    return _PARENTHETICAL.sub(replace, text)


def split_into_sentences(
    text: str,
    *,
    max_words: int,
    break_words: tuple[str, ...],
) -> list[str]:
    """Split text into sentences short enough to re-scan mentally.

    Structural splits (semicolons, parentheticals) happen first and are
    language-neutral in shape though language-specific in what counts as a
    good break word. Sentences still over `max_words` after that are broken
    at the nearest comma to the midpoint, preferring one immediately before
    a known conjunction/relative pronoun (`break_words`) if one is close by.
    """
    text = lift_parentheticals(text)
    text = text.replace(";", ".")

    raw_sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]

    result: list[str] = []
    for sentence in raw_sentences:
        result.extend(_break_long_sentence(sentence, max_words, break_words))
    return result


def _break_long_sentence(sentence: str, max_words: int, break_words: tuple[str, ...]) -> list[str]:
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    return [_finalize_fragment(w) for w in _split_words(words, max_words, break_words)]


def _finalize_fragment(words: list[str]) -> str:
    text = " ".join(words)
    if text.endswith((".", "!", "?", "…")):
        return text
    return text.rstrip(",") + "."


def _split_words(words: list[str], max_words: int, break_words: tuple[str, ...]) -> list[list[str]]:
    """Recursively split a word list so every fragment is <= max_words.

    Both the head and the tail of a split are re-checked — a single split
    at the "best" comma doesn't guarantee either side is actually short
    enough, especially for long, comma-heavy source sentences (verses like
    1 John 1:1 are exactly this shape).
    """
    if len(words) <= max_words:
        return [words]

    # Candidate split points: a comma not on the very last word, so the
    # split always leaves a non-empty tail and recursion makes progress.
    comma_positions = [i for i, w in enumerate(words) if w.endswith(",") and i < len(words) - 1]
    if not comma_positions:
        # No usable comma — fall back to a hard split at max_words.
        return [words[:max_words]] + _split_words(words[max_words:], max_words, break_words)

    midpoint = len(words) / 2
    # Prefer a comma immediately followed by one of the break words.
    preferred = [
        i for i in comma_positions
        if i + 1 < len(words) and words[i + 1].lower().strip(".,!?") in break_words
    ]
    pool = preferred or comma_positions
    split_at = min(pool, key=lambda i: abs(i - midpoint))

    head, tail = words[: split_at + 1], words[split_at + 1 :]
    return _split_words(head, max_words, break_words) + _split_words(tail, max_words, break_words)


_LEFTOVER_MARKDOWN = re.compile(r"[#*_`|]|\[.*?\]\(.*?\)")
_UNEXPANDED_REF = re.compile(r"\b\d{1,3}:\d{1,3}\b")
_URL = re.compile(r"https?://\S+")


def generic_sanity_checks(text: str, *, max_words: int) -> list[str]:
    warnings: list[str] = []

    if _LEFTOVER_MARKDOWN.search(text):
        warnings.append("Leftover markdown syntax survived structural cleanup.")

    if _URL.search(text):
        warnings.append("A URL survived structural cleanup and will be read aloud.")

    for m in _UNEXPANDED_REF.finditer(text):
        warnings.append(
            f"Unrecognized possible scripture reference '{m.group(0)}' near "
            f"'...{text[max(0, m.start() - 20):m.end() + 20]}...' — left as-is."
        )

    # `text` is one already-final sentence/heading per line (see
    # PreparedScript.full_text) — split on newlines first, so a heading with
    # no trailing period never gets fused with the paragraph that follows it
    # into one falsely-long "sentence." The punctuation split inside each
    # line is defense in depth, not the primary boundary.
    for line in text.split("\n"):
        for sentence in _SENTENCE_END.split(line):
            n = len(sentence.split())
            if n > max_words:
                warnings.append(f"Sentence still over {max_words} words ({n}): '{sentence[:60]}...'")

    return warnings
