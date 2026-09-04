"""Section 6.2: break sentences over ~25 words, and split semicolons /
parentheticals into their own sentences rather than leaving them as
subordinate clauses the listener can't re-scan."""

from mx_narrator.prep.langs.es import SpanishPack
from mx_narrator.prep.langs.pt import PortuguesePack


def test_long_sentence_is_broken_under_the_word_cap():
    long_sentence = " ".join([f"palabra{i}," if i % 4 == 0 else f"palabra{i}" for i in range(40)]) + "."
    parts = SpanishPack().split_sentences(long_sentence)
    assert len(parts) > 1
    for part in parts:
        assert len(part.split()) <= 25


def test_short_sentence_is_not_split():
    text = "Esta es una oración corta y clara."
    assert SpanishPack().split_sentences(text) == [text]


def test_semicolon_becomes_a_sentence_break():
    text = "Primero esto; segundo aquello."
    parts = SpanishPack().split_sentences(text)
    assert len(parts) == 2


def test_parenthetical_becomes_its_own_sentence():
    text = "Dios nos ama (esto es evidente) y nos guía."
    parts = SpanishPack().split_sentences(text)
    joined = " ".join(parts)
    assert "(" not in joined and ")" not in joined
    assert any("evidente" in p for p in parts)
    # the parenthetical is not left dangling as a subordinate clause mid-sentence
    assert len(parts) >= 2


def test_portuguese_uses_its_own_break_words():
    long_sentence = " ".join([f"palavra{i}," if i % 4 == 0 else f"palavra{i}" for i in range(40)]) + "."
    parts = PortuguesePack().split_sentences(long_sentence)
    assert len(parts) > 1
    for part in parts:
        assert len(part.split()) <= 25
