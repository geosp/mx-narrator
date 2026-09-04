"""Language-neutral structural cleanup: markdown stripping and block/pause metadata.

Nothing here inspects language code or content language. It only understands
markdown structure: headings, blockquotes, horizontal rules, blank-line
paragraph breaks, links, and inline emphasis markers.

Blank lines and headings are pauses, not punctuation to discard — see
`assemble.py` section 11 for how `Block.kind` maps to silence duration.
Blockquote lines (`> ...`) are treated as scripture quotations, which is the
natural reading of markdown blockquote semantics and gets the 900ms pause
`assemble.py` uses for long scripture quotes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["heading", "paragraph", "quote"]


@dataclass
class Block:
    kind: BlockKind
    text: str


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])\1{2,}\s*$")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_INLINE_MD_RE = re.compile(r"(\*\*|\*|__|_|`)")
_PIPE_RE = re.compile(r"\|")
_WHITESPACE_RE = re.compile(r"[ \t]+")

# Word processors auto-substitute straight quotes for curly ones. Observed in
# practice to occasionally push Chatterbox into a repetition loop right at
# the start of a quoted chunk (the retry logic in engines/chatterbox.py is a
# safety net for exactly this kind of thing, but straightening the quotes
# here means it usually never has to fire). Straight quotes are far better
# represented in TTS training data than curly ones.
_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def strip_markdown_inline(text: str) -> str:
    """Remove inline markdown syntax without touching the words it wraps."""
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _URL_RE.sub("", text)
    text = _INLINE_MD_RE.sub("", text)
    text = _PIPE_RE.sub(" ", text)
    text = text.translate(_SMART_QUOTES)
    return text


def parse_blocks(raw: str) -> list[Block]:
    """Parse raw script text into structural blocks, ready for a pack to expand."""
    raw = raw.replace("\r\n", "\n")
    lines = raw.split("\n")
    blocks: list[Block] = []
    buf: list[str] = []
    buf_kind: BlockKind = "paragraph"

    def flush() -> None:
        nonlocal buf, buf_kind
        if buf:
            joined = " ".join(line.strip() for line in buf if line.strip())
            cleaned = strip_markdown_inline(joined)
            cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
            if cleaned:
                blocks.append(Block(buf_kind, cleaned))
        buf = []
        buf_kind = "paragraph"

    for line in lines:
        if not line.strip():
            flush()
            continue
        if _HR_RE.match(line):
            flush()
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            heading_text = _WHITESPACE_RE.sub(" ", strip_markdown_inline(heading_match.group(1))).strip()
            if heading_text:
                blocks.append(Block("heading", heading_text))
            continue
        quote_match = _BLOCKQUOTE_RE.match(line)
        if quote_match:
            if buf_kind != "quote":
                flush()
                buf_kind = "quote"
            buf.append(quote_match.group(1))
            continue
        if buf_kind == "quote":
            flush()
        buf.append(line)
    flush()
    return blocks


def blocks_to_text(blocks: list[Block]) -> str:
    """Flatten blocks to one text stream, one block per line, for pack-level expansion."""
    return "\n".join(b.text for b in blocks)
