"""Unit discovery, language pairing, and naming. See spec section 9.

    Input:  scripts/<unit-id>.<lang>.txt
    Output: out/<unit-id>.<lang>.mp3

The unit id is language-neutral so the three versions sort together and
pair automatically — discovery is a glob-and-group on that id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Unit:
    id: str
    scripts: dict[str, Path] = field(default_factory=dict)  # lang -> source path


def discover_units(scripts_dir: Path) -> dict[str, Unit]:
    units: dict[str, Unit] = {}
    for path in sorted(scripts_dir.glob("*.txt")):
        parts = path.stem.split(".")
        if len(parts) < 2:
            continue  # not "<unit-id>.<lang>.txt" — skip silently, not a script
        lang = parts[-1]
        unit_id = ".".join(parts[:-1])
        units.setdefault(unit_id, Unit(id=unit_id)).scripts[lang] = path
    return units


def output_path(out_dir: Path, unit_id: str, lang: str, *, audio_format: str = "mp3") -> Path:
    return out_dir / f"{unit_id}.{lang}.{audio_format}"
