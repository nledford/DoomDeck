from __future__ import annotations

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.github_api import (
    validate_github_release_payload,
    validate_github_repository_payload,
)


def test_github_release_payload_accepts_required_asset_fields_and_ignores_extras() -> None:
    release = validate_github_release_payload(
        {
            "tag_name": "v1.2.3",
            "extra": "ignored",
            "assets": [
                {
                    "name": "uzdoom.AppImage",
                    "browser_download_url": "https://github.com/example/releases/download/v1/uzdoom.AppImage",
                    "size": 1024,
                    "unused": "ignored",
                }
            ],
        },
        "example/repo",
    )

    assert release.label == "v1.2.3"
    assert release.assets[0].name == "uzdoom.AppImage"
    assert release.assets[0].browser_download_url == "https://github.com/example/releases/download/v1/uzdoom.AppImage"
    assert release.assets[0].size == 1024


def test_github_release_payload_rejects_asset_without_download_url() -> None:
    with pytest.raises(DoomDeckError, match=r"assets\.0\.browser_download_url"):
        validate_github_release_payload(
            {
                "tag_name": "v1.2.3",
                "assets": [{"name": "uzdoom.AppImage"}],
            },
            "example/repo",
        )


def test_github_repository_payload_rejects_wrong_default_branch_type() -> None:
    with pytest.raises(DoomDeckError, match="default_branch"):
        validate_github_repository_payload({"default_branch": 123}, "example/repo")
