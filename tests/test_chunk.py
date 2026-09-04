"""Short-paragraph folding in chunk_prepared_script.

A one-line rhetorical fragment synthesized alone is disproportionately
prone to Chatterbox instability (observed in practice). Adjacent short
paragraph blocks should be folded into one TTS call; headings and quotes
must never be folded regardless of length, since their bracketing pauses
are structurally meaningful, not just a length threshold.
"""

from mx_narrator.chunk import chunk_prepared_script
from mx_narrator.prep import PreparedBlock, PreparedScript


def _script(blocks: list[tuple[str, list[str]]]) -> PreparedScript:
    return PreparedScript(blocks=[PreparedBlock(kind=k, sentences=s) for k, s in blocks])


def test_short_adjacent_paragraphs_are_folded_together():
    script = _script(
        [
            ("paragraph", ["Fue oído."]),
            ("paragraph", ["Y fue tocado."]),
            ("paragraph", ["Antes de nosotros."]),
        ]
    )
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text == "Fue oído. Y fue tocado. Antes de nosotros."
    assert chunks[0].block_index == 0  # reports the first contributing block


def test_normal_length_paragraphs_are_not_merged():
    long_a = "Esta es una oración de longitud normal que ya supera el umbral mínimo por sí sola."
    long_b = "Y esta es otra oración distinta, también de longitud normal, en su propio párrafo."
    script = _script([("paragraph", [long_a]), ("paragraph", [long_b])])
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    assert len(chunks) == 2
    assert chunks[0].text == long_a
    assert chunks[1].text == long_b
    assert chunks[0].block_index == 0
    assert chunks[1].block_index == 1


def test_short_paragraph_folds_into_a_following_longer_one():
    short = "Fue oído."
    long_ = "Esta es una oración de longitud normal que ya supera el umbral mínimo por sí sola."
    script = _script([("paragraph", [short]), ("paragraph", [long_])])
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text == f"{short} {long_}"


def test_heading_is_never_folded_even_if_short():
    script = _script(
        [
            ("heading", ["Intro"]),
            ("paragraph", ["Fue oído."]),
        ]
    )
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    assert len(chunks) == 2
    assert chunks[0].block_kind == "heading"
    assert chunks[0].text == "Intro"
    assert chunks[1].block_kind == "paragraph"


def test_quote_is_never_folded_even_if_short():
    script = _script(
        [
            ("paragraph", ["Fue oído."]),
            ("quote", ["Corto."]),
            ("paragraph", ["Y fue tocado."]),
        ]
    )
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    # the quote breaks any folding across it; the two short paragraphs on
    # either side each stand alone since they have no paragraph neighbor
    assert [c.block_kind for c in chunks] == ["paragraph", "quote", "paragraph"]
    assert chunks[1].text == "Corto."


def test_folding_never_exceeds_max_chars():
    sentences = [("paragraph", [f"Fragmento {i}."]) for i in range(20)]
    script = _script(sentences)
    chunks = chunk_prepared_script(script, max_chars=60, min_chars=50)
    assert all(len(c.text) <= 60 for c in chunks)
    assert len(chunks) > 1


def test_trailing_short_paragraph_with_nothing_to_merge_still_emitted():
    script = _script([("paragraph", ["Solo esto."])])
    chunks = chunk_prepared_script(script, max_chars=300, min_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text == "Solo esto."
