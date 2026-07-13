"""Validated GitHub API payload schemas."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.downloads import DownloadPolicy
from doomdeck.infrastructure.downloads import ValidatingRedirectHandler


PYDANTIC_MODEL_CONFIG = ConfigDict(frozen=True, extra="ignore")


class GitHubCommitPayload(BaseModel):
    """Git commit identity returned by GitHub's commits API."""

    model_config = PYDANTIC_MODEL_CONFIG

    sha: StrictStr = Field(pattern=r"^[0-9a-fA-F]{40}$")


class GitHubReleaseAssetPayload(BaseModel):
    """Release asset fields DoomDeck consumes from GitHub."""

    model_config = PYDANTIC_MODEL_CONFIG

    name: StrictStr = Field(min_length=1)
    browser_download_url: StrictStr = Field(min_length=1)
    size: StrictInt | None = Field(default=None, ge=0)
    digest: StrictStr | None = Field(default=None, pattern=r"^sha256:[0-9a-fA-F]{64}$")


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


def request_github_json(url: str, user_agent: str) -> Any:
    policy = DownloadPolicy.for_hosts({"api.github.com"})
    policy.validate_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/vnd.github+json"},
    )
    opener = urllib.request.build_opener(ValidatingRedirectHandler(policy))
    try:
        with opener.open(request, timeout=30) as response:
            policy.validate_url(response.geturl())
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
        raise DoomDeckError(f"Could not read GitHub metadata from {url}: {exc}") from exc


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


def validate_github_commit_payload(payload: Any, repo: str) -> GitHubCommitPayload:
    if not isinstance(payload, Mapping):
        raise DoomDeckError(f"Could not understand GitHub commit metadata for {repo}: input should be an object")
    try:
        return GitHubCommitPayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_pydantic_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub commit metadata for {repo}: {detail}") from exc


def validate_github_repository_payload(payload: Any, repo: str) -> GitHubRepositoryPayload:
    if not isinstance(payload, Mapping):
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: input should be an object")
    try:
        return GitHubRepositoryPayload.model_validate(payload)
    except ValidationError as exc:
        detail = _format_pydantic_errors(exc)
        raise DoomDeckError(f"Could not understand GitHub repository metadata for {repo}: {detail}") from exc
