"""Install workflow planning helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from doomdeck.domain.models import Dirs, SteamInfo


def build_install_actions(
    *,
    dirs: Dirs,
    steam: SteamInfo,
    appid: str,
    steamos_msg: str,
    moddb_wad_urls: Sequence[str],
    skip_steam_shortcut: bool,
) -> list[str]:
    actions = [
        f"Create/update managed layout under {dirs.root}",
        f"SteamOS suitability check: {steamos_msg}",
        f"Detect Steam root: {steam.steam_root if steam.steam_root else 'not found'}",
        f"Detect Steam DOOM + DOOM II app {appid}: {steam.app_install_dir if steam.app_install_dir else 'not found'}",
        "Install or reuse Doom Runner AppImage",
        "Install or reuse UZDoom AppImage",
        "Copy legal IWADs and add-on WADs from the Steam install into the managed Doom tree",
        "Create UZDoom classic/modern config templates and direct launcher scripts",
        "Check/update Brutal Doom from ModDB or install a supplied .pk3/.zip",
        "Check/update Project Brutality from GitHub and add a Doom Runner preset",
        "Generate Doom Runner live options.json, setup guide, and stable preset manifest",
    ]
    if moddb_wad_urls:
        actions.append("Download requested ModDB WAD archives into the PWAD map directory")
    if not skip_steam_shortcut:
        actions.append(f"Add/update Steam non-Steam shortcut for Doom Runner at {_shortcuts_label(steam.shortcuts_vdf)}")
    return actions


def _shortcuts_label(shortcuts_vdf: Path | None) -> str:
    return str(shortcuts_vdf) if shortcuts_vdf else "unknown shortcuts.vdf"
