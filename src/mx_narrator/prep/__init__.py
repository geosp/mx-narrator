"""Prep orchestration: parse structure, run the language pack, collect warnings.

This is the only module (besides the packs themselves) that calls into a
`LanguagePack`. Everything upstream (CLI, batch, assemble) works with a
`PreparedScript`, never with a language code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from mx_narrator.prep import common
from mx_narrator.prep.registry import get_pack

logger = logging.getLogger(__name__)

# A digit:digit pattern that survives expand_scripture means the book
# name/abbreviation wasn't recognized — checked here, immediately after
# expand_scripture and before expand_numbers runs, because expand_numbers
# would otherwise turn the digits into words and destroy the evidence.
# generic_sanity_checks' own leftover-reference check (prep/langs/_shared.py)
# runs on the fully-expanded text and can no longer see this by then.
_LEFTOVER_SCRIPTURE_DIGITS = re.compile(r"\b\d{1,3}:\d{1,3}\b")


@dataclass
class PreparedBlock:
    kind: str  # "heading" | "paragraph" | "quote"
    sentences: list[str]


@dataclass
class PreparedScript:
    blocks: list[PreparedBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """One sentence per line, block order preserved — what `--dry-run` prints."""
        lines = []
        for block in self.blocks:
            lines.extend(block.sentences)
        return "\n".join(lines)


def prepare(raw_text: str, lang: str) -> PreparedScript:
    pack = get_pack(lang)
    structural_blocks = common.parse_blocks(raw_text)

    prepared_blocks: list[PreparedBlock] = []
    extra_warnings: list[str] = []
    for block in structural_blocks:
        after_scripture = pack.expand_scripture(block.text)
        for m in _LEFTOVER_SCRIPTURE_DIGITS.finditer(after_scripture):
            extra_warnings.append(
                f"Unrecognized scripture reference '{m.group(0)}' near "
                f"'...{after_scripture[max(0, m.start() - 20):m.end() + 20]}...' — "
                f"the book name/abbreviation wasn't recognized, so this was left as "
                f"raw digits and will be read as plain numbers instead of a reference."
            )

        text = pack.expand_numbers(after_scripture)
        text = pack.expand_abbreviations(text)
        if block.kind == "heading":
            sentences = [text]
        else:
            sentences = pack.split_sentences(text)
        prepared_blocks.append(PreparedBlock(kind=block.kind, sentences=sentences))

    result = PreparedScript(blocks=prepared_blocks)
    result.warnings = extra_warnings + pack.sanity_checks(result.full_text)
    for warning in result.warnings:
        logger.warning("prep[%s]: %s", lang, warning)

    return result
