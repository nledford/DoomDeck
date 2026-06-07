"""Validated GitHub API payload schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from doomdeck.domain.models import DoomDeckError


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


def _format_validation_errors(exc: Any) -> str:
    details: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        details.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(details)


def validate_github_release_payload(payload: Any, repo: str) -> GitHubReleasePayload:
    try:
        return GitHubReleasePayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_validation_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub release metadata for {repo}: {detail}") from exc


def validate_github_repository_payload(payload: Any, repo: str) -> GitHubRepositoryPayload:
    try:
        return GitHubRepositoryPayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_validation_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {detail}") from exc
