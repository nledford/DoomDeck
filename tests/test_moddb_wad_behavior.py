from __future__ import annotations

import logging
import urllib.error
import zipfile
from unittest.mock import patch

import pytest

from doomdeck.application.moddb_wads import install_moddb_wad_archive
from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.moddb import (
    BrutalDoomSelectionPolicy,
    BRUTAL_DOOM_DOWNLOADS_URL,
    BRUTAL_DOOM_MODDB_URL,
    ModDBPageCandidate,
    extract_moddb_download_link,
    select_brutal_doom_download,
)


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


def test_brutal_doom_selection_policy_rejects_related_addons() -> None:
    policy = BrutalDoomSelectionPolicy(channel="stable")

    score = policy.score(
        ModDBPageCandidate(
            title="Brutal Doom Monsters Only",
            url="https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-monsters-only",
            index=0,
        )
    )

    assert score <= 0


def test_brutal_doom_selection_policy_prefers_stable_full_versions_over_tests() -> None:
    policy = BrutalDoomSelectionPolicy(channel="stable")

    stable_score = policy.score(
        ModDBPageCandidate(
            title="Brutal Doom v22 Full Version",
            url="https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-v22",
            index=0,
        )
    )
    beta_score = policy.score(
        ModDBPageCandidate(
            title="Brutal Doom v22 Test Build",
            url="https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-v22-test",
            index=1,
        )
    )

    assert stable_score > beta_score


def test_brutal_doom_selection_falls_back_and_resolves_mirror_from_html_fixtures() -> None:
    candidate_url = "https://www.moddb.com/mods/brutal-doom/downloads/brutal-doom-v22"
    start_url = "https://www.moddb.com/downloads/start/123"
    mirror_url = "https://www.moddb.com/downloads/mirror/456"
    pages = {
        BRUTAL_DOOM_DOWNLOADS_URL: (
            '<a href="/mods/brutal-doom/downloads/brutal-doom-v22">'
            "Brutal Doom v22 Full Version</a>"
        ),
        candidate_url: (
            "<div>Filename:</div><div>brutal-doom-v22.zip</div>"
            "<div>Updated:</div><div>2026-07-01</div>"
            "<div>MD5 Hash:</div><div>abcd1234</div>"
            '<a href="/downloads/start/123">Download now</a>'
        ),
        start_url: "<p>Select a mirror</p>",
        f"{start_url}/all": '<a href="/downloads/mirror/456">Mirror</a>',
    }

    def fetch(url, _logger, *, user_agent):
        assert user_agent == "test-agent"
        if url == BRUTAL_DOOM_MODDB_URL:
            raise urllib.error.URLError("primary unavailable")
        return pages[url]

    with patch("doomdeck.infrastructure.moddb.fetch_text_url", side_effect=fetch):
        selected = select_brutal_doom_download(
            "stable",
            logging.getLogger("test"),
            user_agent="test-agent",
        )

    assert selected.title == "Brutal Doom v22 Full Version"
    assert selected.page_url == candidate_url
    assert selected.filename == "brutal-doom-v22.zip"
    assert selected.download_url == mirror_url
    assert selected.updated == "2026-07-01"
    assert selected.md5 == "abcd1234"
