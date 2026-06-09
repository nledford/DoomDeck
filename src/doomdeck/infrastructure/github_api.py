"""Validated GitHub API payload schemas."""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from doomdeck.domain.models import DoomDeckError


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


ValidationErrors = list[tuple[str, str]]


def _format_validation_errors(errors: ValidationErrors) -> str:
    return "; ".join(f"{location}: {message}" if location else message for location, message in errors)


def _optional_string(payload: Mapping[Any, Any], field: str, errors: ValidationErrors) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    value = payload[field]
    if isinstance(value, str):
        return value
    errors.append((field, "input should be a string"))
    return None


def _optional_non_empty_string(
    payload: Mapping[Any, Any],
    field: str,
    errors: ValidationErrors,
) -> str | None:
    value = _optional_string(payload, field, errors)
    if value == "":
        errors.append((field, "string should have at least 1 character"))
        return None
    return value


def _required_non_empty_string(
    payload: Mapping[Any, Any],
    field: str,
    location: str,
    errors: ValidationErrors,
) -> str:
    if field not in payload:
        errors.append((location, "field required"))
        return ""
    value = payload[field]
    if not isinstance(value, str):
        errors.append((location, "input should be a string"))
        return ""
    if value == "":
        errors.append((location, "string should have at least 1 character"))
        return ""
    return value


def _optional_non_negative_int(
    payload: Mapping[Any, Any],
    field: str,
    location: str,
    errors: ValidationErrors,
) -> int | None:
    if field not in payload or payload[field] is None:
        return None
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append((location, "input should be an integer"))
        return None
    if value < 0:
        errors.append((location, "input should be greater than or equal to 0"))
        return None
    return value


def _validate_release_assets(raw_assets: Any, errors: ValidationErrors) -> list[GitHubReleaseAssetPayload]:
    if raw_assets is None:
        errors.append(("assets", "input should be a list"))
        return []
    if not isinstance(raw_assets, list):
        errors.append(("assets", "input should be a list"))
        return []

    assets: list[GitHubReleaseAssetPayload] = []
    for index, raw_asset in enumerate(raw_assets):
        location = f"assets.{index}"
        if not isinstance(raw_asset, Mapping):
            errors.append((location, "input should be an object"))
            continue
        name = _required_non_empty_string(raw_asset, "name", f"{location}.name", errors)
        browser_download_url = _required_non_empty_string(
            raw_asset,
            "browser_download_url",
            f"{location}.browser_download_url",
            errors,
        )
        size = _optional_non_negative_int(raw_asset, "size", f"{location}.size", errors)
        if name and browser_download_url:
            assets.append(
                GitHubReleaseAssetPayload(
                    name=name,
                    browser_download_url=browser_download_url,
                    size=size,
                )
            )
    return assets


def validate_github_release_payload(payload: Any, repo: str) -> GitHubReleasePayload:
    errors: ValidationErrors = []
    if not isinstance(payload, Mapping):
        errors.append(("", "input should be an object"))
    else:
        tag_name = _optional_string(payload, "tag_name", errors)
        name = _optional_string(payload, "name", errors)
        zipball_url = _optional_non_empty_string(payload, "zipball_url", errors)
        assets = _validate_release_assets(payload.get("assets", []), errors)
        if not errors:
            return GitHubReleasePayload(
                tag_name=tag_name,
                name=name,
                assets=assets,
                zipball_url=zipball_url,
            )

    detail = _format_validation_errors(errors)
    raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: {detail}")


def validate_github_repository_payload(payload: Any, repo: str) -> GitHubRepositoryPayload:
    errors: ValidationErrors = []
    if not isinstance(payload, Mapping):
        errors.append(("", "input should be an object"))
    else:
        default_branch = _optional_string(payload, "default_branch", errors)
        if not errors:
            return GitHubRepositoryPayload(default_branch=default_branch)

    detail = _format_validation_errors(errors)
    raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {detail}")
