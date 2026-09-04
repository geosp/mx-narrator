"""The LanguagePack protocol — the one extension point for language-specific behavior.

Nothing outside `prep/langs/` may branch on language code. Adding a fourth language
means writing one new module under `prep/langs/` and registering it in `registry.py`,
never touching `prep/__init__.py`, `prep/common.py`, or anything upstream of it.

Packs log uncertain-but-applied transformations via the standard `logging` module
(logger name `mx_narrator.prep.langs.<code>`) rather than through return values, so that
`--dry-run` and normal runs share one logging path. `sanity_checks` is a separate,
final audit pass — it never raises, only reports.
"""

from __future__ import annotations

from typing import Protocol


class LanguagePack(Protocol):
    code: str
    num2words_locale: str
    kokoro_voice: str

    def expand_scripture(self, text: str) -> str: ...

    def expand_numbers(self, text: str) -> str: ...

    def expand_abbreviations(self, text: str) -> str: ...

    def split_sentences(self, text: str) -> list[str]: ...

    def sanity_checks(self, text: str) -> list[str]: ...
