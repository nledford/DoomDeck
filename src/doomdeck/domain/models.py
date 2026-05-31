"""Core DoomDeck domain data structures."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional


class DoomDeckError(RuntimeError):
    """A predictable setup/validation error with a human-actionable message."""


@dataclasses.dataclass
class Dirs:
    root: Path
    tools: Path
    doomrunner: Path
    ports: Path
    uzdoom: Path
    iwads: Path
    pwads: Path
    mods: Path
    brutal: Path
    project_brutality: Path
    configs: Path
    xdg_config: Path
    xdg_data: Path
    doomrunner_config: Path
    uzdoom_config: Path
    launchers: Path
    saves: Path
    screenshots: Path
    logs: Path
    backups: Path
    downloads: Path
    docs: Path


@dataclasses.dataclass
class SteamInfo:
    steam_root: Optional[Path]
    user_id: Optional[str]
    shortcuts_vdf: Optional[Path]
    library_folders: list[Path]
    app_install_dir: Optional[Path]


@dataclasses.dataclass
class GitHubAsset:
    name: str
    url: str
    size: Optional[int]
    tag_name: str


@dataclasses.dataclass
class ModDBDownload:
    title: str
    page_url: str
    filename: str
    download_url: str
    updated: str
    md5: str


@dataclasses.dataclass
class ValidationItem:
    level: str  # PASS, WARN, FAIL
    message: str
