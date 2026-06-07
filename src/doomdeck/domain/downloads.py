"""Download trust and integrity policies."""
from __future__ import annotations

import dataclasses
import urllib.parse
from pathlib import Path
from typing import Iterable

from doomdeck.domain.models import DoomDeckError


@dataclasses.dataclass(frozen=True)
class DownloadPolicy:
    allowed_hosts: frozenset[str] = dataclasses.field(default_factory=frozenset)
    require_https: bool = True

    @classmethod
    def for_hosts(cls, hosts: Iterable[str] | None) -> "DownloadPolicy":
        return cls(frozenset(host.lower() for host in hosts or ()))

    def validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if self.require_https and parsed.scheme != "https":
            raise DoomDeckError(f"Download URL must use https: {url}")
        hostname = (parsed.hostname or "").lower()
        if self.allowed_hosts:
            host_allowed = any(hostname == host or hostname.endswith(f".{host}") for host in self.allowed_hosts)
            if not host_allowed:
                allowed = ", ".join(sorted(self.allowed_hosts))
                raise DoomDeckError(f"Download URL host is not allowed: {hostname or '<missing>'}. Allowed hosts: {allowed}")


@dataclasses.dataclass(frozen=True)
class DownloadVerification:
    expected_size: int | None = None
    expected_sha256: str | None = None
    expected_md5: str | None = None

    def verify(self, path: Path, url: str, sha256: str, md5: str) -> None:
        if self.expected_size is not None and path.stat().st_size != self.expected_size:
            raise DoomDeckError(
                f"Download size mismatch for {url}: expected {self.expected_size} bytes, got {path.stat().st_size} bytes"
            )
        if self.expected_sha256 is not None and sha256.lower() != self.expected_sha256.lower():
            raise DoomDeckError(f"Download checksum mismatch for {url}: expected sha256 {self.expected_sha256}, got {sha256}")
        if self.expected_md5 is not None and md5.lower() != self.expected_md5.lower():
            raise DoomDeckError(f"Download checksum mismatch for {url}: expected md5 {self.expected_md5}, got {md5}")
