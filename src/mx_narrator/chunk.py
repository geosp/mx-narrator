"""Pack prep's already-split sentences into TTS-call-sized chunks.

Never splits a sentence — that would produce an audible mid-sentence seam.
Packs sentences up toward the limit instead of sending one per call, per
spec section 11 ("fewer calls means fewer audible seams"). Block boundaries
(paragraph/heading/quote) are preserved on each chunk so `assemble.py` knows
where a real pause belongs versus a chunk split that exists only because of
the engine's length limit.

A very short paragraph synthesized alone — a one-line rhetorical fragment
like "Fue oído." — is disproportionately prone to Chatterbox's repetition
instability (engines/chatterbox.py's retry logic recovers from this, but at
a real GPU-time cost, and observed in practice to correlate strongly with
short, isolated calls). So a paragraph block that comes out shorter than
`min_chars` on its own is folded into a neighboring paragraph's TTS call
instead of standing alone. This does mean the 600ms paragraph pause is
skipped at that specific boundary — the two paragraphs become one
continuous synthesized segment — but only where it was already a fragment
too short to be worth an isolated call. Headings and quotes are never
folded in either direction: their bracketing pauses are structurally
meaningful (spec section 11), not just a length threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from mx_narrator.prep import PreparedScript

# Conservative default: Chatterbox and Kokoro both degrade (hallucinate,
# drift) on very long single calls. This keeps each call to roughly one or
# two sentences' worth of reflective-pace prose.
DEFAULT_MAX_CHARS = 300

# Below this, a standalone paragraph chunk is short enough to be worth
# folding into a neighbor rather than risking an isolated unstable call.
# Comfortably above the ~9-23 character fragments observed to trigger
# retries in practice, comfortably below a normal complete sentence.
DEFAULT_MIN_CHARS = 50


@dataclass
class RenderChunk:
    text: str
    block_kind: str
    block_index: int


def pack_sentences(sentences: list[str], *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        added_len = len(sentence) + (1 if current else 0)
        if current and current_len + added_len > max_chars:
            chunks.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += added_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_prepared_script(
    script: PreparedScript,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[RenderChunk]:
    # Pass 1: pack each block's own sentences, exactly as before — this is
    # still where a sentence never gets split across chunks.
    atoms: list[tuple[int, str, str]] = []  # (block_index, kind, text)
    for block_index, block in enumerate(script.blocks):
        for text in pack_sentences(block.sentences, max_chars=max_chars):
            atoms.append((block_index, block.kind, text))

    # Pass 2: fold short, consecutive PARAGRAPH atoms into one another until
    # the merged group reaches min_chars (or hits max_chars, a non-paragraph
    # atom, or the end of the script). A merged group becomes one RenderChunk
    # — one synth call, one AssembleSegment — so assemble.py naturally skips
    # the inter-paragraph pause at the boundaries that got folded together,
    # while every boundary it still sees (including both edges of the merged
    # group) gets its normal pause.
    result: list[RenderChunk] = []
    buffer: list[tuple[int, str]] = []  # (block_index, text), all "paragraph" kind
    buffer_len = 0

    def flush_buffer() -> None:
        nonlocal buffer, buffer_len
        if buffer:
            merged_text = " ".join(text for _, text in buffer)
            result.append(RenderChunk(text=merged_text, block_kind="paragraph", block_index=buffer[0][0]))
        buffer = []
        buffer_len = 0

    for block_index, kind, text in atoms:
        if kind != "paragraph":
            flush_buffer()
            result.append(RenderChunk(text=text, block_kind=kind, block_index=block_index))
            continue

        prospective_len = buffer_len + (1 if buffer else 0) + len(text)
        if buffer and prospective_len > max_chars:
            flush_buffer()
            prospective_len = len(text)

        buffer.append((block_index, text))
        buffer_len = prospective_len

        if buffer_len >= min_chars:
            flush_buffer()

    flush_buffer()
    return result
