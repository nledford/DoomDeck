"""Application services for finding Doom WAD files in an installed game."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from doomdeck.domain.wads import IWAD_CANONICAL_NAMES, is_excluded_wad_name
from doomdeck.domain.models import Dirs
from doomdeck.infrastructure.files import backup_path, files_equal


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


def copy_wads(
    wads: dict[str, Path],
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
    label: str,
    overwrite_existing: bool = True,
) -> None:
    for name, src in wads.items():
        dest = dest_dir / name.upper()
        if dest.exists() and files_equal(src, dest):
            logger.info("%s already copied: %s", label, dest)
            continue
        if dest.exists() and not overwrite_existing:
            logger.warning("Preserving existing %s with same name; skipping copy from %s: %s", label, src, dest)
            continue
        if dest.exists():
            backup_path(dest, backups_dir, dry_run, logger, label=dest.name)
        logger.info("Copy %s: %s -> %s", label, src, dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def copy_iwads(iwads: dict[str, Path], dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    copy_wads(iwads, dirs.iwads, dirs.backups, dry_run, logger, "IWAD")


def copy_addon_wads(wads: dict[str, Path], dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    copy_wads(wads, dirs.pwads, dirs.backups, dry_run, logger, "add-on WAD", overwrite_existing=False)
