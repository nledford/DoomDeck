from __future__ import annotations

import pytest

from doomdeck.application.release_assets import select_linux_appimage_release_asset, select_windows_zip_release_asset
from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.github_api import GitHubReleaseAssetPayload, GitHubReleasePayload


def test_linux_release_asset_policy_prefers_current_x86_64_appimage() -> None:
    release = GitHubReleasePayload(
        tag_name="v1.2.3",
        assets=[
            GitHubReleaseAssetPayload(name="tool-windows-x86_64.zip", browser_download_url="https://example.test/windows.zip", size=100),
            GitHubReleaseAssetPayload(name="tool-linux-x86_64.AppImage", browser_download_url="https://example.test/linux.AppImage", size=200),
            GitHubReleaseAssetPayload(name="tool-linux-legacy_x86_64.AppImage", browser_download_url="https://example.test/legacy.AppImage", size=300),
        ],
    )

    selected = select_linux_appimage_release_asset(release, "example/tool", prefer_legacy_appimage=False)

    assert selected.name == "tool-linux-x86_64.AppImage"
    assert selected.url == "https://example.test/linux.AppImage"
    assert selected.size == 200
    assert selected.tag_name == "v1.2.3"


def test_windows_release_asset_policy_prefers_recent_x86_64_zip() -> None:
    release = GitHubReleasePayload(
        tag_name="v1.2.3",
        assets=[
            GitHubReleaseAssetPayload(name="DoomRunner-Linux-x86_64.AppImage", browser_download_url="https://example.test/linux.AppImage", size=100),
            GitHubReleaseAssetPayload(name="DoomRunner-Windows-legacy_i386.zip", browser_download_url="https://example.test/i386.zip", size=100),
            GitHubReleaseAssetPayload(
                name="DoomRunner-Windows-recent_x86_64.zip",
                browser_download_url="https://example.test/x86_64.zip",
                size=100,
                digest="sha256:" + "b" * 64,
            ),
        ],
    )

    selected = select_windows_zip_release_asset(release, "Youda008/DoomRunner")

    assert selected.name == "DoomRunner-Windows-recent_x86_64.zip"
    assert selected.sha256 == "b" * 64


def test_release_asset_policy_rejects_unsuitable_windows_assets() -> None:
    release = GitHubReleasePayload(
        tag_name="v1.2.3",
        assets=[
            GitHubReleaseAssetPayload(name="tool-linux-x86_64.AppImage", browser_download_url="https://example.test/linux.AppImage", size=100),
        ],
    )

    with pytest.raises(DoomDeckError, match="Could not identify a suitable Windows ZIP"):
        select_windows_zip_release_asset(release, "example/tool")
