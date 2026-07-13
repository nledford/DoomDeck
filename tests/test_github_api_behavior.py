from __future__ import annotations

import io
import urllib.error
from email.message import Message
from unittest.mock import MagicMock, patch

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.github_api import (
    request_github_json,
    validate_github_commit_payload,
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
                    "digest": "sha256:" + "a" * 64,
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
    assert release.assets[0].digest == "sha256:" + "a" * 64


def test_github_release_payload_rejects_asset_without_download_url() -> None:
    with pytest.raises(DoomDeckError, match=r"assets\.0\.browser_download_url"):
        validate_github_release_payload(
            {
                "tag_name": "v1.2.3",
                "assets": [{"name": "uzdoom.AppImage"}],
            },
            "example/repo",
        )


def test_github_release_payload_rejects_negative_asset_size() -> None:
    with pytest.raises(DoomDeckError, match=r"assets\.0\.size"):
        validate_github_release_payload(
            {
                "tag_name": "v1.2.3",
                "assets": [
                    {
                        "name": "uzdoom.zip",
                        "browser_download_url": "https://github.com/example/releases/download/v1/uzdoom.zip",
                        "size": -1,
                    }
                ],
            },
            "example/repo",
        )


def test_github_release_payload_rejects_boolean_asset_size() -> None:
    with pytest.raises(DoomDeckError, match=r"assets\.0\.size"):
        validate_github_release_payload(
            {
                "tag_name": "v1.2.3",
                "assets": [
                    {
                        "name": "uzdoom.zip",
                        "browser_download_url": "https://github.com/example/releases/download/v1/uzdoom.zip",
                        "size": True,
                    }
                ],
            },
            "example/repo",
        )


def test_github_release_payload_rejects_malformed_asset_digest() -> None:
    with pytest.raises(DoomDeckError, match=r"assets\.0\.digest"):
        validate_github_release_payload(
            {
                "tag_name": "v1.2.3",
                "assets": [
                    {
                        "name": "uzdoom.zip",
                        "browser_download_url": "https://github.com/example/releases/download/v1/uzdoom.zip",
                        "size": 10,
                        "digest": "md5:abcd",
                    }
                ],
            },
            "example/repo",
        )


def test_github_repository_payload_rejects_wrong_default_branch_type() -> None:
    with pytest.raises(DoomDeckError, match="default_branch"):
        validate_github_repository_payload({"default_branch": 123}, "example/repo")


def test_github_commit_payload_requires_full_sha() -> None:
    commit = validate_github_commit_payload({"sha": "a" * 40}, "example/repo")

    assert commit.sha == "a" * 40

    with pytest.raises(DoomDeckError, match="sha"):
        validate_github_commit_payload({"sha": "main"}, "example/repo")


def test_github_request_preserves_http_errors_for_status_aware_fallbacks() -> None:
    error = urllib.error.HTTPError(
        "https://api.github.com/repos/example/repo/releases/latest",
        404,
        "Not Found",
        Message(),
        io.BytesIO(),
    )
    opener = MagicMock()
    opener.open.side_effect = error

    with (
        patch("doomdeck.infrastructure.github_api.urllib.request.build_opener", return_value=opener),
        pytest.raises(urllib.error.HTTPError) as raised,
    ):
        request_github_json(error.url, "test-agent")

    assert raised.value.code == 404
