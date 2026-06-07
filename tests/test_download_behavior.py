from __future__ import annotations

import io
import logging
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from doomdeck.cli import download_url, fetch_text_url, github_request_json
from doomdeck.domain.models import DoomDeckError


@dataclass
class FakeResponse:
    payload: bytes

    def __enter__(self) -> io.BytesIO:
        return io.BytesIO(self.payload)

    def __exit__(self, *_exc: Any) -> None:
        return None


def fake_urlopen(payload: bytes) -> Any:
    def open_request(_request: object, timeout: int) -> FakeResponse:
        assert timeout == 60
        return FakeResponse(payload)

    return open_request


def test_download_url_rejects_non_https_urls(tmp_path: Path) -> None:
    with pytest.raises(DoomDeckError, match="must use https"):
        download_url(
            "http://example.test/file.pk3",
            tmp_path / "file.pk3",
            dry_run=False,
            logger=logging.getLogger("test"),
            allowed_hosts={"example.test"},
        )


def test_download_url_rejects_untrusted_hosts(tmp_path: Path) -> None:
    with pytest.raises(DoomDeckError, match="not allowed"):
        download_url(
            "https://evil.test/file.pk3",
            tmp_path / "file.pk3",
            dry_run=False,
            logger=logging.getLogger("test"),
            allowed_hosts={"example.test"},
        )


def test_download_url_verifies_size_and_sha256(tmp_path: Path) -> None:
    payload = b"downloaded bytes"

    with patch("doomdeck.infrastructure.downloads.urllib.request.urlopen", side_effect=fake_urlopen(payload)):
        downloaded = download_url(
            "https://example.test/file.pk3",
            tmp_path / "file.pk3",
            dry_run=False,
            logger=logging.getLogger("test"),
            allowed_hosts={"example.test"},
            expected_size=len(payload),
            expected_sha256="7b13421e5997dd03f43e4cfbbb79dd42eddbe73112928f65cac1f64eca1f96f4",
        )

    assert downloaded.read_bytes() == payload


def test_download_url_removes_partial_file_after_checksum_failure(tmp_path: Path) -> None:
    dest = tmp_path / "file.pk3"

    with patch("doomdeck.infrastructure.downloads.urllib.request.urlopen", side_effect=fake_urlopen(b"bad bytes")):
        with pytest.raises(DoomDeckError, match="checksum mismatch"):
            download_url(
                "https://example.test/file.pk3",
                dest,
                dry_run=False,
                logger=logging.getLogger("test"),
                allowed_hosts={"example.test"},
                expected_sha256="7b13421e5997dd03f43e4cfbbb79dd42eddbe73112928f65cac1f64eca1f96f4",
            )

    assert not dest.exists()
    assert not (tmp_path / "file.pk3.tmp").exists()


def test_download_url_preserves_download_error_context(tmp_path: Path) -> None:
    with patch("doomdeck.infrastructure.downloads.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
        with pytest.raises(DoomDeckError, match="Failed to download"):
            download_url(
                "https://example.test/file.pk3",
                tmp_path / "file.pk3",
                dry_run=False,
                logger=logging.getLogger("test"),
                allowed_hosts={"example.test"},
            )


def test_metadata_fetches_reject_untrusted_urls() -> None:
    with pytest.raises(DoomDeckError, match="must use https"):
        fetch_text_url("http://www.moddb.com/mods/brutal-doom")

    with pytest.raises(DoomDeckError, match="not allowed"):
        github_request_json("https://example.test/repos/nledford/DoomDeck")
