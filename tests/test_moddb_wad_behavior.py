from __future__ import annotations

import logging
import zipfile

import pytest

from doomdeck.cli import extract_moddb_download_link, install_moddb_wad_archive
from doomdeck.domain.models import DoomDeckError


def test_moddb_wad_archive_extracts_playable_files_to_pwad_directory(tmp_path) -> None:
    archive_path = tmp_path / "dtwid.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("dtwid/dtwid.wad", b"wad bytes")
        archive.writestr("dtwid/docs/readme.txt", "documentation")

    installed = install_moddb_wad_archive(
        archive_path,
        tmp_path / "pwads",
        tmp_path / "backups",
        dry_run=False,
        logger=logging.getLogger("test"),
    )

    assert installed == [tmp_path / "pwads" / "DTWID.WAD"]
    assert (tmp_path / "pwads" / "DTWID.WAD").read_bytes() == b"wad bytes"
    assert not (tmp_path / "pwads" / "README.TXT").exists()


def test_moddb_wad_archive_rejects_unsafe_payload_paths(tmp_path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../evil.wad", b"bad")

    with pytest.raises(DoomDeckError, match="Unsafe path"):
        install_moddb_wad_archive(
            archive_path,
            tmp_path / "pwads",
            tmp_path / "backups",
            dry_run=False,
            logger=logging.getLogger("test"),
        )


def test_moddb_download_link_extraction_accepts_addon_start_urls() -> None:
    html = '<a href="/addons/start/12345">1.91mb Download Now</a>'

    assert (
        extract_moddb_download_link(
            html,
            "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
        )
        == "https://www.moddb.com/addons/start/12345"
    )
