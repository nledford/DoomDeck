"""Filesystem mutation helpers used by application services and CLI commands."""
from __future__ import annotations

import datetime as _dt
import logging
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Optional

from doomdeck.infrastructure.downloads import sha256_file


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def atomic_write_text(path: Path, content: str, dry_run: bool, logger: logging.Logger, mode: int = 0o644) -> None:
    logger.info("Write file: %s", path)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    tmp_path.replace(path)


def atomic_write_bytes(path: Path, content: bytes, dry_run: bool, logger: logging.Logger, mode: int = 0o644) -> None:
    logger.info("Write file: %s", path)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    tmp_path.replace(path)


def make_executable(path: Path, dry_run: bool, logger: logging.Logger) -> None:
    logger.info("Mark executable: %s", path)
    if dry_run:
        return
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def files_equal(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return sha256_file(a) == sha256_file(b)


def backup_destination(backups_dir: Path, label: str, stamp: str) -> Path:
    base = backups_dir / f"{label}.{stamp}"
    if not base.exists():
        return base
    index = 1
    while True:
        candidate = backups_dir / f"{label}.{stamp}.{index:03d}"
        if not candidate.exists():
            return candidate
        index += 1


def backup_path(path: Path, backups_dir: Path, dry_run: bool, logger: logging.Logger, label: Optional[str] = None) -> Optional[Path]:
    if not path.exists():
        return None
    label_text = label or path.name
    dest = backup_destination(backups_dir, label_text, now_stamp())
    logger.info("Back up %s -> %s", path, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, symlinks=True)
    else:
        shutil.copy2(path, dest)
    return dest


def replace_file_safely(src: Path, dest: Path, backups_dir: Path, dry_run: bool, logger: logging.Logger) -> None:
    if dest.exists() and files_equal(src, dest):
        logger.info("Already current: %s", dest)
        make_executable(dest, dry_run, logger)
        return
    if dest.exists():
        backup_path(dest, backups_dir, dry_run, logger, label=dest.name)
    logger.info("Install file: %s -> %s", src, dest)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    make_executable(dest, dry_run, logger)
