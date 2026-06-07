"""Download helpers with explicit trust and integrity checks."""
from __future__ import annotations

import hashlib
import logging
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from doomdeck.domain.downloads import DownloadPolicy, DownloadVerification
from doomdeck.domain.models import DoomDeckError

DEFAULT_USER_AGENT = "doomdeck"


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
    try:
        # URL policy is validated before opening the request.
        with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as handle:  # nosec B310
            shutil.copyfileobj(response, handle)
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
