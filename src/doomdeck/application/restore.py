"""Atomic managed-root restore workflow."""
from __future__ import annotations

import logging
import shutil
import tarfile
from pathlib import Path

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.archives import safe_extract_tar


def restore_backup_archive(
    archive_path: Path,
    active_root: Path,
    replaced_root: Path,
    staging_dir: Path,
    logger: logging.Logger,
) -> None:
    if staging_dir.exists() or staging_dir.is_symlink():
        raise DoomDeckError(f"Restore staging path already exists: {staging_dir}")
    if replaced_root.exists() or replaced_root.is_symlink():
        raise DoomDeckError(f"Restore replacement path already exists: {replaced_root}")

    staging_dir.mkdir(parents=True)
    try:
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                safe_extract_tar(archive, staging_dir, expected_root_name=active_root.name)
        except DoomDeckError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise DoomDeckError(f"Failed to extract backup archive into staging: {archive_path}") from exc

        staged_root = staging_dir / active_root.name
        if not staged_root.is_dir():
            raise DoomDeckError(f"Restored backup did not create the expected root: {staged_root}")

        moved_existing = False
        if active_root.exists() or active_root.is_symlink():
            shutil.move(str(active_root), str(replaced_root))
            moved_existing = True

        try:
            shutil.move(str(staged_root), str(active_root))
        except Exception as exc:
            if active_root.exists() or active_root.is_symlink():
                _remove_path(active_root)
            try:
                if moved_existing:
                    shutil.move(str(replaced_root), str(active_root))
            except Exception as rollback_exc:
                raise DoomDeckError(
                    f"Failed to activate restored backup and rollback failed; previous root remains at {replaced_root}"
                ) from rollback_exc
            raise DoomDeckError(f"Failed to activate restored backup at {active_root}") from exc

        logger.info("Restore activated from %s", archive_path)
    finally:
        if staging_dir.exists() or staging_dir.is_symlink():
            _remove_path(staging_dir)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
