from __future__ import annotations

import io
import http.client
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from doomdeck.cli import download_url
from doomdeck.domain.downloads import DownloadPolicy
from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.downloads import ValidatingRedirectHandler
from doomdeck.infrastructure.github_api import request_github_json
from doomdeck.infrastructure.moddb import fetch_text_url


@dataclass
class FakeResponse:
    payload: bytes
    url: str = "https://example.test/file.pk3"

    def __post_init__(self) -> None:
        self._stream = io.BytesIO(self.payload)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self.url


def fake_urlopen(payload: bytes, final_url: str = "https://example.test/file.pk3") -> Any:
    def open_request(_request: object, _policy: DownloadPolicy, timeout: int) -> FakeResponse:
        assert timeout == 60
        return FakeResponse(payload, final_url)

    return open_request


@dataclass
class FakeHeaderResponse:
    payload: bytes
    headers: dict[str, str]
    url: str = "https://example.test/file.pk3"

    def __post_init__(self) -> None:
        self._stream = io.BytesIO(self.payload)

    def __enter__(self) -> "FakeHeaderResponse":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self.url


def fake_header_urlopen(payload: bytes, headers: dict[str, str]) -> Any:
    def open_request(_request: object, _policy: DownloadPolicy, timeout: int) -> FakeHeaderResponse:
        assert timeout == 60
        return FakeHeaderResponse(payload, headers)

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


def test_download_url_rejects_redirects_to_untrusted_hosts(tmp_path: Path) -> None:
    dest = tmp_path / "file.pk3"

    with patch(
        "doomdeck.infrastructure.downloads._open_url",
        side_effect=fake_urlopen(b"downloaded bytes", "https://redirected.invalid/file.pk3"),
    ):
        with pytest.raises(DoomDeckError, match="not allowed"):
            download_url(
                "https://example.test/file.pk3",
                dest,
                dry_run=False,
                logger=logging.getLogger("test"),
                allowed_hosts={"example.test"},
            )

    assert not dest.exists()
    assert not (tmp_path / "file.pk3.tmp").exists()


def test_redirect_handler_rejects_each_untrusted_target() -> None:
    handler = ValidatingRedirectHandler(DownloadPolicy.for_hosts({"example.test"}))

    with pytest.raises(DoomDeckError, match="not allowed"):
        handler.redirect_request(
            urllib.request.Request("https://example.test/file.pk3"),
            io.BytesIO(),
            302,
            "Found",
            http.client.HTTPMessage(),
            "https://redirected.invalid/file.pk3",
        )


def test_download_url_verifies_size_and_sha256(tmp_path: Path) -> None:
    payload = b"downloaded bytes"

    with patch("doomdeck.infrastructure.downloads._open_url", side_effect=fake_urlopen(payload)):
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


def test_download_url_rejects_oversized_content_length_before_copying(tmp_path: Path) -> None:
    dest = tmp_path / "file.pk3"

    with patch(
        "doomdeck.infrastructure.downloads._open_url",
        side_effect=fake_header_urlopen(b"downloaded bytes", {"Content-Length": "16"}),
    ):
        with pytest.raises(DoomDeckError, match="exceeds maximum allowed size"):
            download_url(
                "https://example.test/file.pk3",
                dest,
                dry_run=False,
                logger=logging.getLogger("test"),
                allowed_hosts={"example.test"},
                expected_size=15,
            )

    assert not dest.exists()
    assert not (tmp_path / "file.pk3.tmp").exists()


def test_download_url_aborts_streams_that_exceed_expected_size(tmp_path: Path) -> None:
    dest = tmp_path / "file.pk3"

    with patch("doomdeck.infrastructure.downloads._open_url", side_effect=fake_urlopen(b"too many bytes")):
        with pytest.raises(DoomDeckError, match="exceeds maximum allowed size"):
            download_url(
                "https://example.test/file.pk3",
                dest,
                dry_run=False,
                logger=logging.getLogger("test"),
                allowed_hosts={"example.test"},
                expected_size=3,
            )

    assert not dest.exists()
    assert not (tmp_path / "file.pk3.tmp").exists()


def test_download_url_removes_partial_file_after_checksum_failure(tmp_path: Path) -> None:
    dest = tmp_path / "file.pk3"

    with patch("doomdeck.infrastructure.downloads._open_url", side_effect=fake_urlopen(b"bad bytes")):
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
    with patch("doomdeck.infrastructure.downloads._open_url", side_effect=urllib.error.URLError("offline")):
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
        request_github_json("https://example.test/repos/nledford/DoomDeck", "test-agent")
