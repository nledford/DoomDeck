"""Application services for finding Doom WAD files in an installed game."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from doomdeck.domain.wads import IWAD_CANONICAL_NAMES, is_excluded_wad_name


def score_iwad_candidate(path: Path) -> tuple[int, float]:
    parts = [p.lower() for p in path.parts]
    score = 0
    if "rerelease" in parts:
        score += 50
    if "base" in parts:
        score += 40
    if "dosbox" in parts:
        score += 10
    if any(part in {"soundtrack", "music", "manual"} for part in parts):
        score -= 100
    try:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
    except OSError:
        size = 0
        mtime = 0.0
    if size > 1_000_000:
        score += 10
    return score, mtime


def find_wads_in_install(install_dir: Optional[Path], logger: logging.Logger) -> tuple[dict[str, Path], dict[str, Path]]:
    found_iwads: dict[str, list[Path]] = {name: [] for name in IWAD_CANONICAL_NAMES}
    found_pwads: dict[str, list[Path]] = {}
    if not install_dir or not install_dir.exists():
        return {}, {}
    for file_path in install_dir.rglob("*"):
        if not file_path.is_file():
            continue
        name = file_path.name.lower()
        if file_path.suffix.lower() != ".wad" or is_excluded_wad_name(name):
            continue
        if name in found_iwads:
            found_iwads[name].append(file_path)
        else:
            found_pwads.setdefault(name, []).append(file_path)

    best: dict[str, Path] = {}
    for name, candidates in found_iwads.items():
        if not candidates:
            continue
        chosen = sorted(candidates, key=score_iwad_candidate, reverse=True)[0]
        best[name] = chosen.resolve()
        logger.info("Selected IWAD %s from %s", name, chosen)

    extras: dict[str, Path] = {}
    for name, candidates in found_pwads.items():
        chosen = sorted(candidates, key=score_iwad_candidate, reverse=True)[0]
        extras[name] = chosen.resolve()
        logger.info("Selected add-on WAD %s from %s", name, chosen)
    return best, extras
