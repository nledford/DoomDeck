"""Install workflow planning helpers."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from doomdeck.domain.models import Dirs, SteamInfo


@dataclasses.dataclass(frozen=True)
class InstallAction:
    id: str
    description: str


@dataclasses.dataclass(frozen=True)
class InstallPlan:
    actions: tuple[InstallAction, ...]

    def render_actions(self) -> list[str]:
        return [action.description for action in self.actions]


def build_install_plan(
    *,
    dirs: Dirs,
    steam: SteamInfo,
    appid: str,
    steamos_msg: str,
    skip_steam_shortcut: bool,
) -> InstallPlan:
    actions = [
        InstallAction("managed-layout", f"Create/update managed layout under {dirs.root}"),
        InstallAction("steamos-check", f"SteamOS suitability check: {steamos_msg}"),
        InstallAction("steam-root-detection", f"Detect Steam root: {steam.steam_root if steam.steam_root else 'not found'}"),
        InstallAction(
            "steam-app-detection",
            f"Detect Steam DOOM + DOOM II app {appid}: {steam.app_install_dir if steam.app_install_dir else 'not found'}",
        ),
        InstallAction("doomrunner-appimage", "Install or reuse Doom Runner AppImage"),
        InstallAction("uzdoom-appimage", "Install or reuse UZDoom AppImage"),
        InstallAction("steam-wads", "Copy legal IWADs and add-on WADs from the Steam install into the managed Doom tree"),
        InstallAction("uzdoom-launchers", "Create UZDoom classic/modern config templates and direct launcher scripts"),
        InstallAction("brutal-doom", "Check/update Brutal Doom from ModDB or install a supplied .pk3/.zip"),
        InstallAction("project-brutality", "Check/update Project Brutality from GitHub and add a Doom Runner preset"),
        InstallAction("doomrunner-config", "Generate Doom Runner live options.json, setup guide, and stable preset manifest"),
    ]
    if not skip_steam_shortcut:
        actions.append(
            InstallAction(
                "steam-shortcut",
                f"Add/update Steam non-Steam shortcut for Doom Runner at {_shortcuts_label(steam.shortcuts_vdf)}",
            )
        )
    return InstallPlan(tuple(actions))


def build_install_actions(
    *,
    dirs: Dirs,
    steam: SteamInfo,
    appid: str,
    steamos_msg: str,
    skip_steam_shortcut: bool,
) -> list[str]:
    return build_install_plan(
        dirs=dirs,
        steam=steam,
        appid=appid,
        steamos_msg=steamos_msg,
        skip_steam_shortcut=skip_steam_shortcut,
    ).render_actions()


def _shortcuts_label(shortcuts_vdf: Path | None) -> str:
    return str(shortcuts_vdf) if shortcuts_vdf else "unknown shortcuts.vdf"
