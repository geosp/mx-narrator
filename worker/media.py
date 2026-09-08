"""Shared helpers for turning user-provided text and on-disk paths into
filesystem/URL-safe strings — see the "special characters in unit_id break
audio/video playback" bugfix.

Plain functions, no Temporal/Mongo import — safe for both `worker/activities.py`
and `api/main.py` to import directly.
"""

from __future__ import annotations

import re
from pathlib import Path

# Reserved URL delimiters (would corrupt a browser's own URL parse if left raw
# in a path segment — confirmed for real: a literal "?" in a filename gets
# parsed as the query-string delimiter client-side, before the request is even
# sent, silently truncating the path and 404ing) plus filesystem-hostile
# characters. Deliberately NOT accents, spaces, commas, or periods — those are
# already proven safe on disk and in a URL (real production files already
# contain them and play fine).
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f#%&$@+=;]')


def slugify_filename(text: str, *, max_length: int = 120) -> str:
    """Collapse characters unsafe in a filename or URL to "-", while keeping
    the result close to the original (readable) text."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("-", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned[:max_length].strip(" .-")
    return cleaned or "untitled"


def media_relative_url(absolute_path: str | Path, media_root: Path) -> str:
    """Same join used by every "write a Mongo *_url field" site — kept in one
    place rather than duplicated across worker/activities.py and api/main.py."""
    return f"/media/{Path(absolute_path).relative_to(media_root)}"
