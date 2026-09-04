"""Engine name -> SynthEngine class. Default is Chatterbox (spec section 3)."""

from __future__ import annotations

from mx_narrator.engines.base import SynthEngine
from mx_narrator.engines.chatterbox import ChatterboxEngine
from mx_narrator.engines.kokoro import KokoroEngine

DEFAULT_ENGINE = "chatterbox"

_ENGINES: dict[str, type[SynthEngine]] = {
    "chatterbox": ChatterboxEngine,
    "kokoro": KokoroEngine,
}


def get_engine(name: str) -> SynthEngine:
    try:
        return _ENGINES[name]()
    except KeyError:
        raise ValueError(f"Unknown engine: {name!r}. Supported: {', '.join(sorted(_ENGINES))}") from None


def available_engines() -> list[str]:
    return sorted(_ENGINES)
