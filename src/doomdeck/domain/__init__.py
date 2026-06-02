"""Domain models and layout helpers for DoomDeck."""
from __future__ import annotations

from .deck import STEAM_DECK_HEIGHT, STEAM_DECK_TARGET_FPS, STEAM_DECK_WIDTH
from .models import DoomDeckError, Dirs, GitHubAsset, ModDBDownload, SteamInfo, ValidationItem, ValidationLevel
from .paths import all_managed_dirs, build_dirs, expand_path
from .wads import DOOMRUNNER_IWAD_DISPLAY_NAMES, IWAD_CANONICAL_NAMES, iwad_dest_name

__all__ = [
    "DoomDeckError",
    "Dirs",
    "GitHubAsset",
    "ModDBDownload",
    "SteamInfo",
    "ValidationItem",
    "ValidationLevel",
    "all_managed_dirs",
    "build_dirs",
    "expand_path",
    "DOOMRUNNER_IWAD_DISPLAY_NAMES",
    "IWAD_CANONICAL_NAMES",
    "iwad_dest_name",
    "STEAM_DECK_HEIGHT",
    "STEAM_DECK_TARGET_FPS",
    "STEAM_DECK_WIDTH",
]
