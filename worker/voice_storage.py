"""Where uploaded voice samples live on disk, and the filename convention
`mx_narrator.voices.resolve_voice()` expects — shared by api/main.py (upload/delete)
and worker/activities.py (render-time resolution) so both agree on layout without
either importing the other's heavier module. Import-light: only `pathlib`.

    MEDIA_ROOT/voices/{voice_id}/voice.wav       ->  fallback ("default") sample
    MEDIA_ROOT/voices/{voice_id}/voice.es.wav    ->  Spanish sample
    MEDIA_ROOT/voices/{voice_id}/voice.en.wav    ->  English sample
    MEDIA_ROOT/voices/{voice_id}/voice.pt.wav    ->  Portuguese sample

`resolve_voice(voice_family, lang)` (src/mx_narrator/voices.py) is handed the fallback
path and derives the per-language path itself by swapping in `.{lang}` before the
suffix — this convention is exactly what makes that work unmodified.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_SAMPLE_KEY = "default"


def voice_dir(media_root: Path, voice_id: str) -> Path:
    return media_root / "voices" / voice_id


def voice_family_path(media_root: Path, voice_id: str) -> Path:
    """The path to hand `mx_narrator.voices.resolve_voice()` as `voice_family`."""
    return voice_dir(media_root, voice_id) / "voice.wav"


def sample_path(media_root: Path, voice_id: str, lang: str) -> Path:
    """Where one language's sample lives. `lang == DEFAULT_SAMPLE_KEY` is the bare
    fallback file (no language segment)."""
    if lang == DEFAULT_SAMPLE_KEY:
        return voice_family_path(media_root, voice_id)
    return voice_dir(media_root, voice_id) / f"voice.{lang}.wav"
