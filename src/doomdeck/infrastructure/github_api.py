"""Validated GitHub API payload schemas."""
from __future__ import annotations

import dataclasses
from typing import Any

from doomdeck.domain.models import DoomDeckError

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
except ModuleNotFoundError:
    BaseModel = None  # type: ignore[assignment]
    ConfigDict = None  # type: ignore[assignment]
    Field = None  # type: ignore[assignment]
    ValidationError = None  # type: ignore[assignment]


if BaseModel is not None:

    class GitHubReleaseAssetPayload(BaseModel):
        """Release asset fields DoomDeck consumes from GitHub."""

        model_config = ConfigDict(extra="ignore")

        name: str = Field(min_length=1)
        browser_download_url: str = Field(min_length=1)
        size: int | None = Field(default=None, ge=0)


    class GitHubReleasePayload(BaseModel):
        """GitHub release fields DoomDeck needs for download selection."""

        model_config = ConfigDict(extra="ignore")

        tag_name: str | None = None
        name: str | None = None
        assets: list[GitHubReleaseAssetPayload] = Field(default_factory=list)
        zipball_url: str | None = Field(default=None, min_length=1)

        @property
        def label(self) -> str:
            return self.tag_name or self.name or "latest"


    class GitHubRepositoryPayload(BaseModel):
        """GitHub repository fields DoomDeck needs for source archive fallback."""

        model_config = ConfigDict(extra="ignore")

        default_branch: str | None = None

else:

    @dataclasses.dataclass(frozen=True)
    class GitHubReleaseAssetPayload:
        """Release asset fields DoomDeck consumes from GitHub."""

        name: str
        browser_download_url: str
        size: int | None = None


    @dataclasses.dataclass(frozen=True)
    class GitHubReleasePayload:
        """GitHub release fields DoomDeck needs for download selection."""

        tag_name: str | None = None
        name: str | None = None
        assets: list[GitHubReleaseAssetPayload] = dataclasses.field(default_factory=list)
        zipball_url: str | None = None

        @property
        def label(self) -> str:
            return self.tag_name or self.name or "latest"


    @dataclasses.dataclass(frozen=True)
    class GitHubRepositoryPayload:
        """GitHub repository fields DoomDeck needs for source archive fallback."""

        default_branch: str | None = None


def _format_validation_errors(exc: ValidationError) -> str:
    details: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        details.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(details)


def _append_optional_str_error(errors: list[str], field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    errors.append(f"{field_name}: Input should be a valid string")
    return None


def _append_required_nonempty_str_error(errors: list[str], field_name: str, value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    errors.append(f"{field_name}: Field required" if value is None else f"{field_name}: Input should be a non-empty string")
    return None


def _append_size_error(errors: list[str], field_name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    errors.append(f"{field_name}: Input should be a non-negative integer")
    return None


def _validate_github_release_payload_without_pydantic(payload: Any, repo: str) -> GitHubReleasePayload:
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: Input should be a valid dictionary")

    tag_name = _append_optional_str_error(errors, "tag_name", payload.get("tag_name"))
    name = _append_optional_str_error(errors, "name", payload.get("name"))
    zipball_url = _append_optional_str_error(errors, "zipball_url", payload.get("zipball_url"))

    assets: list[GitHubReleaseAssetPayload] = []
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list):
        errors.append("assets: Input should be a valid list")
    else:
        for index, raw_asset in enumerate(raw_assets):
            if not isinstance(raw_asset, dict):
                errors.append(f"assets.{index}: Input should be a valid dictionary")
                continue
            asset_name = _append_required_nonempty_str_error(errors, f"assets.{index}.name", raw_asset.get("name"))
            download_url = _append_required_nonempty_str_error(
                errors,
                f"assets.{index}.browser_download_url",
                raw_asset.get("browser_download_url"),
            )
            size = _append_size_error(errors, f"assets.{index}.size", raw_asset.get("size"))
            if asset_name and download_url:
                assets.append(GitHubReleaseAssetPayload(name=asset_name, browser_download_url=download_url, size=size))

    if errors:
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: {'; '.join(errors)}")
    return GitHubReleasePayload(tag_name=tag_name, name=name, assets=assets, zipball_url=zipball_url)


def _validate_github_repository_payload_without_pydantic(payload: Any, repo: str) -> GitHubRepositoryPayload:
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: Input should be a valid dictionary")
    default_branch = _append_optional_str_error(errors, "default_branch", payload.get("default_branch"))
    if errors:
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {'; '.join(errors)}")
    return GitHubRepositoryPayload(default_branch=default_branch)


def validate_github_release_payload(payload: Any, repo: str) -> GitHubReleasePayload:
    if BaseModel is None:
        return _validate_github_release_payload_without_pydantic(payload, repo)
    try:
        return GitHubReleasePayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_validation_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: {detail}") from exc


def validate_github_repository_payload(payload: Any, repo: str) -> GitHubRepositoryPayload:
    if BaseModel is None:
        return _validate_github_repository_payload_without_pydantic(payload, repo)
    try:
        return GitHubRepositoryPayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_validation_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {detail}") from exc
