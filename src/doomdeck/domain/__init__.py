"""Domain models and layout helpers for DoomDeck."""
from __future__ import annotations

from .deck import STEAM_DECK_HEIGHT, STEAM_DECK_TARGET_FPS, STEAM_DECK_WIDTH
from .downloads import DownloadPolicy, DownloadVerification
from .doomrunner import (
    DoomRunnerEngine,
    DoomRunnerIWAD,
    DoomRunnerMod,
    DoomRunnerOptions,
    DoomRunnerPreset,
    DoomRunnerPresetPaths,
)
from .models import DoomDeckError, Dirs, GitHubAsset, ModDBDownload, SteamInfo, ValidationItem, ValidationLevel
from .mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, InstalledModMetadata, ManagedMod, ModSource
from .paths import all_managed_dirs, build_dirs, expand_path
from .presets import EngineSpec, Preset, PresetManifest
from .wads import DOOMRUNNER_IWAD_DISPLAY_NAMES, IWAD_CANONICAL_NAMES, iwad_dest_name

__all__ = [
    "DoomDeckError",
    "Dirs",
    "DownloadPolicy",
    "DownloadVerification",
    "DoomRunnerEngine",
    "DoomRunnerIWAD",
    "DoomRunnerMod",
    "DoomRunnerOptions",
    "DoomRunnerPreset",
    "DoomRunnerPresetPaths",
    "EngineSpec",
    "GitHubAsset",
    "InstalledModMetadata",
    "ManagedMod",
    "ModSource",
    "ModDBDownload",
    "SteamInfo",
    "Preset",
    "PresetManifest",
    "ValidationItem",
    "ValidationLevel",
    "all_managed_dirs",
    "build_dirs",
    "expand_path",
    "DOOMRUNNER_IWAD_DISPLAY_NAMES",
    "BRUTAL_DOOM_MOD",
    "IWAD_CANONICAL_NAMES",
    "PROJECT_BRUTALITY_MOD",
    "iwad_dest_name",
    "STEAM_DECK_HEIGHT",
    "STEAM_DECK_TARGET_FPS",
    "STEAM_DECK_WIDTH",
]
