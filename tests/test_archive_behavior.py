from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.archives import (
    choose_payload_member,
    common_zip_toplevel,
    normalized_zip_member_name,
    safe_extract_tar,
    safe_extract_zip,
    write_tree_tar_gz,
    zip_contains_markers,
)


def test_zip_member_names_drop_a_shared_archive_folder() -> None:
    names = [
        "Project_Brutality-master/gameinfo.txt",
        "Project_Brutality-master/zscript.zc",
    ]

    prefix = common_zip_toplevel(names)

    assert prefix == "Project_Brutality-master"
    assert normalized_zip_member_name(names[0], prefix) == "gameinfo.txt"
    assert normalized_zip_member_name(names[1], prefix) == "zscript.zc"


def test_zip_member_names_reject_path_traversal() -> None:
    assert normalized_zip_member_name("../outside.pk3", None) is None
    assert normalized_zip_member_name("folder/../../outside.pk3", "folder") is None


def test_zip_contains_markers_matches_case_insensitively_under_common_folder(tmp_path) -> None:
    archive_path = tmp_path / "project-brutality.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Project_Brutality-master/GameInfo.txt", "")
        archive.writestr("Project_Brutality-master/ZScript.zc", "")

    assert zip_contains_markers(archive_path, {"gameinfo.txt", "zscript.zc"})


def test_safe_zip_extraction_strips_shared_archive_folder(tmp_path) -> None:
    archive_path = tmp_path / "uzdoom.zip"
    dest = tmp_path / "extract"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Windows-UZDoom-4.14.3/uzdoom.exe", "exe")
        archive.writestr("Windows-UZDoom-4.14.3/fmod.dll", "dll")

    safe_extract_zip(archive_path, dest)

    assert (dest / "uzdoom.exe").read_text(encoding="utf-8") == "exe"
    assert (dest / "fmod.dll").read_text(encoding="utf-8") == "dll"


def test_safe_zip_extraction_rejects_members_outside_destination(tmp_path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.exe", "owned")

    with pytest.raises(DoomDeckError, match="Unsafe path in zip archive"):
        safe_extract_zip(archive_path, tmp_path / "extract")


def test_payload_selection_prefers_primary_brutal_doom_pk3() -> None:
    infos = [
        zipfile.ZipInfo("docs/readme.pk3"),
        zipfile.ZipInfo("extras/optional.wad"),
        zipfile.ZipInfo("BrutalDoom.pk3"),
    ]

    selected = choose_payload_member(infos)

    assert selected is not None
    assert selected.filename == "BrutalDoom.pk3"


def test_safe_tar_extraction_rejects_members_outside_destination(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"owned"
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(DoomDeckError, match="Unsafe path in tar archive"):
            safe_extract_tar(archive, tmp_path / "restore")


def test_safe_tar_extraction_rejects_absolute_member_paths(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"owned"
        member = tarfile.TarInfo("/tmp/outside.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(DoomDeckError, match="Unsafe absolute path"):
            safe_extract_tar(archive, tmp_path / "restore")


def test_safe_tar_extraction_rejects_link_members(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("Doom/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside.txt"
        archive.addfile(member)

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(DoomDeckError, match="Unsafe link"):
            safe_extract_tar(archive, tmp_path / "restore")


def test_safe_tar_extraction_rejects_special_file_members(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("Doom/fifo")
        member.type = tarfile.FIFOTYPE
        archive.addfile(member)

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(DoomDeckError, match="Unsafe special file"):
            safe_extract_tar(archive, tmp_path / "restore")


def test_safe_tar_extraction_accepts_regular_backup_members(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    restore_dir = tmp_path / "restore"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"iwad"
        member = tarfile.TarInfo("Doom/iwads/DOOM2.WAD")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive:
        safe_extract_tar(archive, restore_dir)

    assert (restore_dir / "Doom" / "iwads" / "DOOM2.WAD").read_bytes() == b"iwad"


def test_tree_backup_archive_excludes_nested_backup_directory(tmp_path) -> None:
    root = tmp_path / "Doom"
    backups = root / "backups"
    archive_path = backups / "doom-deck-backup.tar.gz"
    (root / "IWADs").mkdir(parents=True)
    backups.mkdir(parents=True)
    (root / "IWADs" / "DOOM.WAD").write_text("iwad", encoding="utf-8")
    (backups / "old-backup").write_text("old", encoding="utf-8")

    write_tree_tar_gz(archive_path, root, exclude_dirs=[backups])

    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())

    assert "Doom/IWADs/DOOM.WAD" in names
    assert "Doom/backups/old-backup" not in names
    assert "Doom/backups/doom-deck-backup.tar.gz" not in names
