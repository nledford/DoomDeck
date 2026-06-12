"""Application policies for selecting release assets."""
from __future__ import annotations

from collections.abc import Callable

from doomdeck.domain.models import DoomDeckError, GitHubAsset
from doomdeck.infrastructure.github_api import GitHubReleaseAssetPayload, GitHubReleasePayload


def select_linux_appimage_release_asset(
    release: GitHubReleasePayload,
    repo: str,
    *,
    prefer_legacy_appimage: bool,
) -> GitHubAsset:
    return _select_release_asset(
        release,
        repo,
        minimum_score=50,
        error_label="Linux AppImage",
        scorer=_linux_appimage_score(repo, prefer_legacy_appimage),
    )


def select_windows_zip_release_asset(release: GitHubReleasePayload, repo: str) -> GitHubAsset:
    return _select_release_asset(
        release,
        repo,
        minimum_score=120,
        error_label="Windows ZIP",
        scorer=_windows_zip_score(repo),
    )


def _select_release_asset(
    release: GitHubReleasePayload,
    repo: str,
    *,
    minimum_score: int,
    error_label: str,
    scorer: Callable[[GitHubReleaseAssetPayload], int],
) -> GitHubAsset:
    tag_name = release.label
    assets = release.assets
    if not assets:
        raise DoomDeckError(f"GitHub release {repo}@{tag_name} has no downloadable assets")

    ranked = sorted(assets, key=scorer, reverse=True)
    chosen = ranked[0]
    if scorer(chosen) < minimum_score:
        names = ", ".join(asset.name for asset in assets)
        raise DoomDeckError(f"Could not identify a suitable {error_label} for {repo}@{tag_name}. Assets: {names}")
    return GitHubAsset(
        name=chosen.name,
        url=chosen.browser_download_url,
        size=chosen.size,
        tag_name=str(tag_name),
    )


def _repo_key(repo: str) -> str:
    return repo.split("/")[-1].lower().replace("_", "").replace("-", "")


def _linux_appimage_score(repo: str, prefer_legacy_appimage: bool) -> Callable[[GitHubReleaseAssetPayload], int]:
    repo_key = _repo_key(repo)

    def score(asset: GitHubReleaseAssetPayload) -> int:
        lower = asset.name.lower()
        value = 0
        if "appimage" in lower:
            value += 100
        if "linux" in lower:
            value += 50
        if any(token in lower for token in ["x86_64", "x64", "amd64"]):
            value += 30
        if repo_key in lower.replace("_", "").replace("-", ""):
            value += 10
        if "legacy" in lower:
            value += 20 if prefer_legacy_appimage else -25
        if any(token in lower for token in ["windows", "win64", ".exe", "mac", "dmg", "arm64", "aarch64"]):
            value -= 100
        return value

    return score


def _windows_zip_score(repo: str) -> Callable[[GitHubReleaseAssetPayload], int]:
    repo_key = _repo_key(repo)

    def score(asset: GitHubReleaseAssetPayload) -> int:
        lower = asset.name.lower()
        compact = lower.replace("_", "").replace("-", "")
        value = 0
        if lower.endswith(".zip"):
            value += 100
        if "windows" in lower or "win64" in lower:
            value += 80
        if any(token in lower for token in ["x86_64", "x64", "amd64"]):
            value += 40
        if "recent" in lower:
            value += 15
        if repo_key in compact:
            value += 10
        if any(token in lower for token in ["legacy", "i386", "i686", "x86-32"]):
            value -= 80
        if any(token in lower for token in ["linux", "appimage", "mac", "dmg", "arm64", "aarch64"]):
            value -= 120
        return value

    return score
