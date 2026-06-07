"""Download helpers with explicit trust and integrity checks."""
from __future__ import annotations

import hashlib
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO, Optional, Protocol

from doomdeck.domain.downloads import DownloadPolicy, DownloadVerification
from doomdeck.domain.models import DoomDeckError

DEFAULT_USER_AGENT = "doomdeck"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class ReadableStream(Protocol):
    def read(self, size: int = -1) -> bytes: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_download(path: Path, url: str, verification: DownloadVerification) -> None:
    sha256 = sha256_file(path) if verification.expected_sha256 is not None else ""
    md5 = md5_file(path) if verification.expected_md5 is not None else ""
    verification.verify(path, url, sha256=sha256, md5=md5)


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw_value = headers.get("Content-Length")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _copy_response_bounded(response: ReadableStream, dest_handle: BinaryIO, url: str, max_bytes: int | None) -> None:
    content_length = _content_length(response)
    if max_bytes is not None and content_length is not None and content_length > max_bytes:
        raise DoomDeckError(
            f"Download for {url} exceeds maximum allowed size: expected at most {max_bytes} bytes, got {content_length} bytes"
        )

    total = 0
    while True:
        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
        if not chunk:
            return
        total += len(chunk)
        if max_bytes is not None and total > max_bytes:
            raise DoomDeckError(f"Download for {url} exceeds maximum allowed size: expected at most {max_bytes} bytes")
        dest_handle.write(chunk)


def download_url(
    url: str,
    dest: Path,
    dry_run: bool,
    logger: logging.Logger,
    force: bool = False,
    headers: Optional[dict[str, str]] = None,
    allowed_hosts: Optional[set[str]] = None,
    expected_size: Optional[int] = None,
    expected_sha256: Optional[str] = None,
    expected_md5: Optional[str] = None,
    max_bytes: Optional[int] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Path:
    policy = DownloadPolicy.for_hosts(allowed_hosts)
    policy.validate_url(url)
    verification = DownloadVerification(
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        expected_md5=expected_md5,
    )

    if dest.exists() and not force:
        logger.info("Download already exists: %s", dest)
        verify_download(dest, url, verification)
        return dest
    logger.info("Download: %s -> %s", url, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    max_allowed_bytes = max_bytes if max_bytes is not None else expected_size
    try:
        # URL policy is validated before opening the request.
        with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as handle:  # nosec B310
            _copy_response_bounded(response, handle, url, max_allowed_bytes)
        verify_download(tmp, url, verification)
        tmp.replace(dest)
    except DoomDeckError:
        if tmp.exists():
            tmp.unlink()
        raise
    except urllib.error.URLError as exc:
        if tmp.exists():
            tmp.unlink()
        raise DoomDeckError(f"Failed to download {url}: {exc}") from exc
    return dest
