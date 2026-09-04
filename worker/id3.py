"""ID3 tag writing, factored out of worker/activities.py so it can be imported by
api/main.py without pulling in that module's heavy dependencies (torch, faster-
whisper, litellm, ...) — same reasoning as worker/types.py staying import-light."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import COMM, ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TRCK

from worker.types import Id3Fields


def apply_id3(mp3_path: Path, id3: Id3Fields) -> None:
    """Overwrites render_job()'s own default tags with the fields submitted through
    the UI's tag-editor form — a post-processing step here, not a change to mx_narrator's
    own `tag_mp3()`, per design.md's "orchestrate, don't modify" Non-Goal. Called both
    by worker/activities.py::synthesize (right after a fresh render) and directly by
    api/main.py's tags-only edit fast path (rewriting an existing file in place,
    with no re-synthesis)."""
    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()
    tags["TIT2"] = TIT2(encoding=3, text=id3.title)
    tags["TPE1"] = TPE1(encoding=3, text=id3.artist)
    tags["TALB"] = TALB(encoding=3, text=id3.album)
    tags["TRCK"] = TRCK(encoding=3, text=str(id3.track))
    if id3.year:
        tags["TDRC"] = TDRC(encoding=3, text=id3.year)
    if id3.genre:
        tags["TCON"] = TCON(encoding=3, text=id3.genre)
    if id3.comments:
        tags["COMM"] = COMM(encoding=3, lang="eng", desc="", text=id3.comments)
    tags.save(str(mp3_path))
