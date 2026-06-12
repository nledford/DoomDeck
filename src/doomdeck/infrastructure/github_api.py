"""Validated GitHub API payload schemas."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from doomdeck.domain.models import DoomDeckError


PYDANTIC_MODEL_CONFIG = ConfigDict(frozen=True, extra="ignore")


class GitHubReleaseAssetPayload(BaseModel):
    """Release asset fields DoomDeck consumes from GitHub."""

    model_config = PYDANTIC_MODEL_CONFIG

    name: StrictStr = Field(min_length=1)
    browser_download_url: StrictStr = Field(min_length=1)
    size: StrictInt | None = Field(default=None, ge=0)


class GitHubReleasePayload(BaseModel):
    """GitHub release fields DoomDeck needs for download selection."""

    model_config = PYDANTIC_MODEL_CONFIG

    tag_name: StrictStr | None = None
    name: StrictStr | None = None
    assets: list[GitHubReleaseAssetPayload] = Field(default_factory=list)
    zipball_url: StrictStr | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        return self.tag_name or self.name or "latest"


class GitHubRepositoryPayload(BaseModel):
    """GitHub repository fields DoomDeck needs for source archive fallback."""

    model_config = PYDANTIC_MODEL_CONFIG

    default_branch: StrictStr | None = None


def _format_pydantic_errors(error: ValidationError) -> str:
    formatted: list[str] = []
    for issue in error.errors():
        location = ".".join(str(part) for part in issue["loc"])
        message = str(issue["msg"])
        formatted.append(f"{location}: {message}" if location else message)
    return "; ".join(formatted)


def validate_github_release_payload(payload: Any, repo: str) -> GitHubReleasePayload:
    if not isinstance(payload, Mapping):
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: input should be an object")
    try:
        return GitHubReleasePayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_pydantic_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: {detail}") from exc


def validate_github_repository_payload(payload: Any, repo: str) -> GitHubRepositoryPayload:
    if not isinstance(payload, Mapping):
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: input should be an object")
    try:
        return GitHubRepositoryPayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_pydantic_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {detail}") from exc
