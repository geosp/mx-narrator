"""sanity_checks' long-sentence audit scans PreparedScript.full_text, which
places one already-final sentence/heading per line. It must treat those
newlines as real boundaries — a heading with no trailing period must never
get fused with the paragraph that follows it into one falsely-long
"sentence" for word-counting purposes."""

from mx_narrator.prep import prepare


def test_heading_without_trailing_period_does_not_inflate_next_sentence():
    text = (
        "# Reflexión 1 de 1 Juan 1:1-4\n\n"
        "La Vida se manifestó: contemplamos con nuestros propios ojos algo que "
        "trascendía toda comprensión humana y nos dejó sin palabras.\n"
    )
    result = prepare(text, "es")
    assert result.warnings == []


def test_unrecognized_book_abbreviation_warns_before_digits_become_words():
    """An unrecognized book abbreviation leaves raw "digit:digit" behind,
    which expand_numbers would otherwise silently turn into words —
    destroying the evidence before the post-hoc sanity check ever runs.
    This must be caught immediately after expand_scripture instead."""
    result = prepare("Ver Xyz 1:1 para más contexto.", "es")
    assert any("Unrecognized scripture reference" in w for w in result.warnings)
    assert "1:1" not in result.full_text  # still gets number-expanded, just also warned about
    assert "uno:uno" in result.full_text


def test_genuinely_long_heading_still_warns():
    # Headings are never run through the word-cap splitter (spec: a heading
    # is a spoken line, not broken up like body prose) — so an unusually
    # long one is the one case where the audit should still legitimately
    # fire, proving the newline fix didn't just silence the check entirely.
    words = " ".join(f"palabra{i}" for i in range(30))
    text = f"# {words}\n\nPárrafo normal debajo del encabezado.\n"
    result = prepare(text, "es")
    assert any("over 25 words" in w for w in result.warnings)
