"""Structural cleanup is language-neutral: markdown stripped, headings and
blank lines preserved as pause metadata (not dropped), URLs removed
entirely (spec section 6.1)."""

from mx_narrator.prep.common import parse_blocks


def test_heading_becomes_its_own_block_not_dropped():
    blocks = parse_blocks("# Introduction\n\nSome paragraph text here.")
    kinds = [b.kind for b in blocks]
    assert kinds == ["heading", "paragraph"]
    assert blocks[0].text == "Introduction"


def test_blank_lines_separate_paragraph_blocks():
    blocks = parse_blocks("First paragraph.\n\nSecond paragraph.")
    assert len(blocks) == 2
    assert blocks[0].text == "First paragraph."
    assert blocks[1].text == "Second paragraph."


def test_url_removed_entirely():
    blocks = parse_blocks("Check this out: https://example.com/path for more.")
    assert "https://" not in blocks[0].text
    assert "example.com" not in blocks[0].text


def test_markdown_emphasis_and_links_stripped():
    blocks = parse_blocks("This is **bold** and _italic_ and a [link](https://x.com) and `code`.")
    text = blocks[0].text
    for marker in ("**", "__", "_", "`", "["):
        assert marker not in text
    assert "link" in text  # link text kept, URL dropped


def test_horizontal_rule_dropped():
    blocks = parse_blocks("Before.\n\n---\n\nAfter.")
    assert [b.text for b in blocks] == ["Before.", "After."]


def test_blockquote_becomes_quote_block():
    blocks = parse_blocks("> Al principio era el Verbo.\n\nComentario normal.")
    assert blocks[0].kind == "quote"
    assert blocks[0].text == "Al principio era el Verbo."
    assert blocks[1].kind == "paragraph"


def test_table_pipes_removed():
    blocks = parse_blocks("Col1 | Col2 | Col3")
    assert "|" not in blocks[0].text


def test_smart_quotes_are_straightened():
    """Curly quotes (word-processor auto-substitution) get straightened —
    observed to occasionally trip Chatterbox into a repetition loop right at
    the start of a quoted chunk; straight quotes are far better represented
    in TTS training data."""
    blocks = parse_blocks("Ella dijo: “Tóquenme y vean.” ‘Así es’, respondió él.")
    text = blocks[0].text
    assert "“" not in text and "”" not in text
    assert "‘" not in text and "’" not in text
    assert '"Tóquenme y vean."' in text
    assert "'Así es'" in text


def test_clean_prose_passes_through_essentially_untouched():
    raw = "Hoy hablaremos de un tema importante.\nCada línea sigue siendo parte del mismo párrafo."
    blocks = parse_blocks(raw)
    assert len(blocks) == 1
    assert blocks[0].kind == "paragraph"
    assert "importante" in blocks[0].text
    assert "párrafo" in blocks[0].text
