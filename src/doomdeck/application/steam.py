"""Steam shortcut and Proton compatibility orchestration."""
from __future__ import annotations

import dataclasses
import logging
import shutil
import subprocess
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional, cast

from doomdeck.domain.models import Dirs, DoomDeckError, SteamInfo
from doomdeck.infrastructure.binary_vdf import BKV_OBJECT, BKVValue, BinaryVDF
from doomdeck.infrastructure.files import atomic_write_bytes, atomic_write_text, backup_path
from doomdeck.infrastructure.processes import is_process_running
from doomdeck.infrastructure.steam_compat import compat_mapping_key, dumps_text_vdf, load_text_vdf, set_compat_tool_mapping
from doomdeck.infrastructure.steam_shortcuts import get_bkv_str, load_shortcuts, shortcut_entries, upsert_shortcut

ProcessDetector = Callable[[list[str]], bool]
SteamShutdown = Callable[[logging.Logger, bool], None]
DOOMRUNNER_SHORTCUT_NAME = "Doom Runner"
DOOMDECK_PRESET_SHORTCUT_PREFIX = "DoomDeck - "


@dataclasses.dataclass(frozen=True)
class SteamShortcutSettings:
    dry_run: bool
    allow_steam_running: bool = False
    shutdown_steam: bool = False
    proton_compat_tool: str = ""


def doomrunner_proton_options_path(steam: SteamInfo, appid: int) -> Optional[Path]:
    if not steam.steam_root:
        return None
    return (
        steam.steam_root
        / "steamapps"
        / "compatdata"
        / compat_mapping_key(appid)
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "AppData"
        / "Roaming"
        / "DoomRunner"
        / "options.json"
    )


def shutdown_steam(logger: logging.Logger, dry_run: bool) -> None:
    logger.info("Request Steam shutdown")
    if dry_run:
        return
    candidates = [["steam", "-shutdown"], ["steam-runtime", "-shutdown"]]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(8)
            return
    logger.warning("Steam command not found; close Steam manually before modifying Steam shortcut and compatibility files")


def add_or_update_doomrunner_shortcut(
    shortcuts_path: Path,
    dirs: Dirs,
    settings: SteamShortcutSettings,
    logger: logging.Logger,
    *,
    process_detector: ProcessDetector = is_process_running,
    steam_shutdown: SteamShutdown = shutdown_steam,
) -> int:
    return add_or_update_steam_shortcut(
        shortcuts_path,
        DOOMRUNNER_SHORTCUT_NAME,
        dirs.doomrunner / "DoomRunner.exe",
        dirs.doomrunner,
        dirs,
        settings,
        logger,
        process_detector=process_detector,
        steam_shutdown=steam_shutdown,
        remove_extra_doomdeck_shortcuts=True,
    )


def add_or_update_steam_shortcut(
    shortcuts_path: Path,
    appname: str,
    exe: Path,
    start_dir: Path,
    dirs: Dirs,
    settings: SteamShortcutSettings,
    logger: logging.Logger,
    launch_options: str = "",
    match_exe: bool = True,
    *,
    remove_extra_doomdeck_shortcuts: bool = False,
    process_detector: ProcessDetector = is_process_running,
    steam_shutdown: SteamShutdown = shutdown_steam,
) -> int:
    if process_detector(["steamwebhelper", "steam -", "/steam"]):
        if settings.shutdown_steam:
            steam_shutdown(logger, settings.dry_run)
        elif not settings.allow_steam_running:
            raise DoomDeckError(
                "Steam appears to be running. Close Steam first, rerun with --shutdown-steam, "
                "or use --skip-steam-shortcut."
            )
        else:
            logger.warning("Steam appears to be running; modifying Steam shortcut and compatibility files anyway because --allow-steam-running was set")

    shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
    if shortcuts_path.exists():
        backup_path(shortcuts_path, dirs.backups, settings.dry_run, logger, label="shortcuts.vdf")
    root = load_shortcuts(shortcuts_path)
    result = upsert_shortcut(root, appname, exe, start_dir, tags=["Doom", "Tools"], launch_options=launch_options, match_exe=match_exe)
    if result.created:
        logger.info("Add Steam shortcut %s at index %s in %s", appname, result.key, shortcuts_path)
    else:
        logger.info("Update existing Steam shortcut %s in %s", appname, shortcuts_path)
    if remove_extra_doomdeck_shortcuts:
        removed = _remove_extra_doomdeck_shortcuts(root, keep_key=result.key)
        if removed:
            logger.info("Remove extra DoomDeck-managed Steam shortcuts: %s", ", ".join(removed))
    atomic_write_bytes(shortcuts_path, BinaryVDF.dumps(root), settings.dry_run, logger)
    if settings.proton_compat_tool:
        add_or_update_steam_compat_mapping(shortcuts_path.parent / "localconfig.vdf", result.appid, settings.proton_compat_tool, dirs, settings, logger)
    return result.appid


def _remove_extra_doomdeck_shortcuts(root: OrderedDict[str, BKVValue], *, keep_key: str) -> tuple[str, ...]:
    shortcuts = shortcut_entries(root)
    removed: list[str] = []
    for key, value in list(shortcuts.items()):
        if key == keep_key or value.type_code != BKV_OBJECT:
            continue
        entry = cast(OrderedDict[str, BKVValue], value.value)
        appname = get_bkv_str(entry, "appname", "AppName")
        if appname == DOOMRUNNER_SHORTCUT_NAME or appname.startswith(DOOMDECK_PRESET_SHORTCUT_PREFIX):
            del shortcuts[key]
            removed.append(appname or key)
    return tuple(removed)


def add_or_update_steam_compat_mapping(
    localconfig_path: Path,
    appid: int,
    compat_tool: str,
    dirs: Dirs,
    settings: SteamShortcutSettings,
    logger: logging.Logger,
) -> None:
    if localconfig_path.exists():
        backup_path(localconfig_path, dirs.backups, settings.dry_run, logger, label="localconfig.vdf")
    logger.info("Set Steam compatibility tool for appid %s to %s in %s", appid, compat_tool, localconfig_path)
    root = load_text_vdf(localconfig_path)
    set_compat_tool_mapping(root, appid, compat_tool)
    atomic_write_text(localconfig_path, dumps_text_vdf(root), settings.dry_run, logger)
