"""Doom WAD naming and classification policy."""
from __future__ import annotations


IWAD_CANONICAL_NAMES = {
    "doom.wad": "Doom",
    "doom1.wad": "Doom Shareware",
    "doom2.wad": "Doom II",
    "tnt.wad": "Final Doom: TNT Evilution",
    "plutonia.wad": "Final Doom: The Plutonia Experiment",
}

DOOMRUNNER_IWAD_DISPLAY_NAMES = {
    "doom.wad": "The Ultimate Doom",
    "doom1.wad": "Doom Shareware",
    "doom2.wad": "Doom II: Hell on Earth",
    "tnt.wad": "Final Doom: TNT Evilution",
    "plutonia.wad": "Final Doom: The Plutonia Experiment",
}

DEFAULT_PRESET_IWADS = ["doom2.wad", "doom.wad", "tnt.wad", "plutonia.wad", "doom1.wad"]

WAD_COPY_EXCLUDES = {
    # DOSBox and engine support archives are not playable WAD content.
    "dosbox.wad",
}


def iwad_dest_name(iwad_lower_name: str) -> str:
    return iwad_lower_name.upper()


def is_iwad_name(name: str) -> bool:
    return name.lower() in IWAD_CANONICAL_NAMES


def is_excluded_wad_name(name: str) -> bool:
    return name.lower() in WAD_COPY_EXCLUDES
