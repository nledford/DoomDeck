from __future__ import annotations

import json
import logging
import zipfile
from unittest.mock import patch

import pytest

from doomdeck.application.managed_mods import (
    install_brutal_doom_archive,
    install_project_brutality_archive,
)
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, ModSource
from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.downloads import sha256_file


def write_brutal_archive(path, payload: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("release/BrutalDoom.pk3", payload)


def brutal_source(updated: str = "2026-01-01") -> ModSource:
    return ModSource.moddb(
        channel="stable",
        title="Brutal Doom",
        page_url="https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-v22",
        filename="brutal-doom.zip",
        updated=updated,
        md5="abcd",
        download_url="https://www.moddb.com/downloads/mirror/123",
    )


def test_brutal_doom_archive_installs_selected_payload_and_records_provenance(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("docs/readme.txt", "documentation")
        archive.writestr("release/BrutalDoom.pk3", b"pk3 bytes")

    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"

    installed = install_brutal_doom_archive(
        archive_path,
        dest,
        tmp_path / "backups",
        metadata_path,
        dry_run=False,
        logger=logging.getLogger("test"),
        source=brutal_source(),
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert installed == dest
    assert dest.read_bytes() == b"pk3 bytes"
    assert metadata["name"] == BRUTAL_DOOM_MOD.name
    assert metadata["source_type"] == "moddb"
    assert metadata["source_channel"] == "stable"
    assert metadata["source_download_url"] == "https://www.moddb.com/downloads/mirror/123"
    assert metadata["payload_member"] == "release/BrutalDoom.pk3"
    assert metadata["installed_sha256"] == sha256_file(dest)


def test_identical_brutal_doom_rerun_skips_backup_and_payload_replacement(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    write_brutal_archive(archive_path, b"same bytes")
    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())

    with (
        patch("doomdeck.application.managed_mods.backup_path") as backup,
        patch("doomdeck.application.managed_mods._install_brutal_doom_payload") as install_payload,
    ):
        install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())

    backup.assert_not_called()
    install_payload.assert_not_called()


def test_same_brutal_doom_payload_refreshes_changed_source_metadata_without_backup(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    write_brutal_archive(archive_path, b"same bytes")
    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())

    with patch("doomdeck.application.managed_mods.backup_path") as backup:
        install_brutal_doom_archive(
            archive_path,
            dest,
            backups,
            metadata_path,
            False,
            logger,
            brutal_source(updated="2026-07-01"),
        )

    backup.assert_not_called()
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["source_updated"] == "2026-07-01"


@pytest.mark.parametrize("force,malformed_metadata", [(True, False), (False, True)])
def test_brutal_doom_forced_or_malformed_rerun_replaces_with_backup(
    tmp_path,
    force: bool,
    malformed_metadata: bool,
) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    write_brutal_archive(archive_path, b"same bytes")
    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())
    if malformed_metadata:
        metadata_path.write_text("{", encoding="utf-8")

    install_brutal_doom_archive(
        archive_path,
        dest,
        backups,
        metadata_path,
        False,
        logger,
        brutal_source(),
        force=force,
    )

    assert any(backups.iterdir())
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_changed_brutal_doom_payload_replaces_content_with_backup(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    write_brutal_archive(archive_path, b"old bytes")
    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())
    write_brutal_archive(archive_path, b"new bytes")

    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())

    assert dest.read_bytes() == b"new bytes"
    assert any(backups.iterdir())
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_corrupt_installed_brutal_doom_payload_is_replaced_from_current_source(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    write_brutal_archive(archive_path, b"expected bytes")
    dest = tmp_path / "mods" / "brutal-doom.pk3"
    metadata_path = tmp_path / "mods" / "brutal-doom.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())
    dest.write_bytes(b"corrupt")

    install_brutal_doom_archive(archive_path, dest, backups, metadata_path, False, logger, brutal_source())

    assert dest.read_bytes() == b"expected bytes"
    assert any(backups.iterdir())


def test_failed_brutal_doom_payload_install_removes_temporary_file(tmp_path) -> None:
    archive_path = tmp_path / "brutal-doom.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("readme.txt", "no payload")
    dest = tmp_path / "mods" / "brutal-doom.pk3"

    with pytest.raises(DoomDeckError, match="no .pk3/.wad payload"):
        install_brutal_doom_archive(
            archive_path,
            dest,
            tmp_path / "backups",
            tmp_path / "mods" / "brutal-doom.json",
            False,
            logging.getLogger("test"),
            brutal_source(),
        )

    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_project_brutality_archive_normalizes_common_folder_and_records_provenance(tmp_path) -> None:
    archive_path = tmp_path / "project-brutality.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Project_Brutality-main/gameinfo.txt", "game info")
        archive.writestr("Project_Brutality-main/zscript.zc", "zscript")

    dest = tmp_path / "mods" / "project-brutality.pk3"
    metadata_path = tmp_path / "mods" / "project-brutality.json"

    installed = install_project_brutality_archive(
        archive_path,
        dest,
        tmp_path / "backups",
        metadata_path,
        dry_run=False,
        logger=logging.getLogger("test"),
        source=ModSource.github(url="https://api.github.com/repos/example/project/zipball/main", tag="main"),
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(dest) as installed_zip:
        names = set(installed_zip.namelist())

    assert installed == dest
    assert names == {"gameinfo.txt", "zscript.zc"}
    assert metadata["name"] == PROJECT_BRUTALITY_MOD.name
    assert metadata["source_type"] == "github"
    assert metadata["source_tag"] == "main"
    assert metadata["source_url"] == "https://api.github.com/repos/example/project/zipball/main"
    assert metadata["installed_sha256"] == sha256_file(dest)


def test_corrupt_installed_project_brutality_payload_is_replaced_from_current_source(tmp_path) -> None:
    archive_path = tmp_path / "project-brutality.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Project_Brutality-main/gameinfo.txt", "game info")
    dest = tmp_path / "mods" / "project-brutality.pk3"
    metadata_path = tmp_path / "mods" / "project-brutality.json"
    backups = tmp_path / "backups"
    logger = logging.getLogger("test")
    source = ModSource.github(url="https://api.github.com/repos/example/project/zipball/main", tag="main")
    install_project_brutality_archive(archive_path, dest, backups, metadata_path, False, logger, source)
    dest.write_bytes(b"corrupt")

    install_project_brutality_archive(archive_path, dest, backups, metadata_path, False, logger, source)

    assert zipfile.is_zipfile(dest)
    assert any(backups.iterdir())
