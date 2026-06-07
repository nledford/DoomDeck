from __future__ import annotations

import json
import logging
import zipfile

from doomdeck.application.managed_mods import (
    install_brutal_doom_archive,
    install_project_brutality_archive,
)
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, ModSource
from doomdeck.infrastructure.downloads import sha256_file


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
        source=ModSource.moddb(
            channel="stable",
            title="Brutal Doom",
            page_url="https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-v22",
            filename="brutal-doom.zip",
            updated="2026-01-01",
            md5="abcd",
            download_url="https://www.moddb.com/downloads/mirror/123",
        ),
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
