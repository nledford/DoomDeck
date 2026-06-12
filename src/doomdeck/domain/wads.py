"""Doom WAD naming and classification policy."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping


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

PWAD_DISPLAY_NAME_OVERRIDES_FILE = "wad-display-names.json"
PWAD_DISPLAY_NAME_OVERRIDES_SCHEMA = "doom-deck-setup/wad-display-names/v1"

PWAD_CURATED_DISPLAY_NAMES = {
    "dtwid.wad": "Doom The Way ID Did",
    "dtwid.pk3": "Doom The Way ID Did",
    "nerve.wad": "No Rest for the Living",
    "sigil.wad": "SIGIL",
    "sigil.pk3": "SIGIL",
}

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


def pwad_display_name(
    path: Path,
    *,
    metadata: Mapping[str, str] | None = None,
    overrides: Mapping[str, str] | None = None,
    root: Path | None = None,
    pwads_dir: Path | None = None,
) -> str:
    """Return a UI label for a PWAD without changing its launchable path."""
    if display_name := _display_name_from_overrides(path, overrides or {}, root=root, pwads_dir=pwads_dir):
        return display_name
    if display_name := _display_name_from_metadata(metadata or {}):
        return display_name
    if display_name := PWAD_CURATED_DISPLAY_NAMES.get(path.name.casefold()):
        return display_name
    return clean_pwad_filename(path)


def clean_pwad_filename(path: Path) -> str:
    stem = path.stem.strip()
    if not stem:
        return path.name
    if not re.search(r"[_\-.\s]", stem):
        return stem
    text = re.sub(r"[_\-.]+", " ", stem)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return path.name
    return " ".join(_title_safe_token(token) for token in text.split(" "))


def _display_name_from_metadata(metadata: Mapping[str, str]) -> str:
    for key in ["display_name", "title", "source_title", "name"]:
        value = str(metadata.get(key, "")).strip()
        if value:
            return value
    return ""


def _display_name_from_overrides(
    path: Path,
    overrides: Mapping[str, str],
    *,
    root: Path | None,
    pwads_dir: Path | None,
) -> str:
    if not overrides:
        return ""
    normalized = {_normalize_override_key(key): value.strip() for key, value in overrides.items() if str(value).strip()}
    for key in _override_keys(path, root=root, pwads_dir=pwads_dir):
        if display_name := normalized.get(_normalize_override_key(key)):
            return display_name
    return ""


def _override_keys(path: Path, *, root: Path | None, pwads_dir: Path | None) -> list[str]:
    keys = [str(path), path.as_posix(), path.name]
    for base in [root, pwads_dir]:
        if base is None:
            continue
        try:
            keys.append(path.relative_to(base).as_posix())
        except ValueError:
            continue
    return keys


def _normalize_override_key(key: str) -> str:
    return key.replace("\\", "/").casefold()


def _title_safe_token(token: str) -> str:
    if token.isupper() and len(token) <= 5:
        return token
    return token[:1].upper() + token[1:].lower()
