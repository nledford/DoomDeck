from __future__ import annotations

import io
import logging
import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from doomdeck.application.restore import restore_backup_archive
from doomdeck.domain.models import DoomDeckError


def write_backup(path: Path, root_name: str, content: bytes = b"restored") -> None:
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(f"{root_name}/restored.txt")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))


def test_restore_extracts_to_staging_before_replacing_active_root(tmp_path: Path) -> None:
    root = tmp_path / "Doom"
    root.mkdir()
    (root / "existing.txt").write_text("old", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    write_backup(archive, root.name)
    replaced = tmp_path / "Doom.pre-restore"
    staging = tmp_path / ".Doom.restore"

    restore_backup_archive(archive, root, replaced, staging, logging.getLogger("test"))

    assert (root / "restored.txt").read_bytes() == b"restored"
    assert (replaced / "existing.txt").read_text(encoding="utf-8") == "old"
    assert not staging.exists()


def test_restore_extraction_failure_leaves_active_root_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "Doom"
    root.mkdir()
    marker = root / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    write_backup(archive, root.name)
    replaced = tmp_path / "Doom.pre-restore"
    staging = tmp_path / ".Doom.restore"

    def fail_after_partial_extract(_archive, destination, **_kwargs):
        partial = destination / root.name
        partial.mkdir(parents=True)
        (partial / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    with (
        patch("doomdeck.application.restore.safe_extract_tar", side_effect=fail_after_partial_extract),
        pytest.raises(DoomDeckError, match="Failed to extract backup archive"),
    ):
        restore_backup_archive(archive, root, replaced, staging, logging.getLogger("test"))

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not replaced.exists()
    assert not staging.exists()


def test_restore_activation_failure_rolls_back_active_root(tmp_path: Path) -> None:
    root = tmp_path / "Doom"
    root.mkdir()
    marker = root / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    write_backup(archive, root.name)
    replaced = tmp_path / "Doom.pre-restore"
    staging = tmp_path / ".Doom.restore"
    real_move = shutil.move
    move_count = 0

    def fail_new_root_move(source, destination):
        nonlocal move_count
        move_count += 1
        if move_count == 2:
            raise OSError("activation failed")
        return real_move(source, destination)

    with (
        patch("doomdeck.application.restore.shutil.move", side_effect=fail_new_root_move),
        pytest.raises(DoomDeckError, match="Failed to activate restored backup"),
    ):
        restore_backup_archive(archive, root, replaced, staging, logging.getLogger("test"))

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not replaced.exists()
    assert not staging.exists()


def test_restore_rejects_existing_replacement_path_before_touching_active_root(tmp_path: Path) -> None:
    root = tmp_path / "Doom"
    root.mkdir()
    marker = root / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    write_backup(archive, root.name)
    replaced = tmp_path / "Doom.pre-restore"
    replaced.mkdir()
    staging = tmp_path / ".Doom.restore"

    with pytest.raises(DoomDeckError, match="replacement path already exists"):
        restore_backup_archive(archive, root, replaced, staging, logging.getLogger("test"))

    assert marker.read_text(encoding="utf-8") == "keep"
    assert replaced.is_dir()
    assert not staging.exists()
