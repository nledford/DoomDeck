from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest

from doomdeck.application.steam import SteamShortcutSettings, add_or_update_steam_shortcut
from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.paths import build_dirs
from doomdeck.infrastructure.binary_vdf import BKV_OBJECT
from doomdeck.infrastructure.steam_compat import TextVDFObject, compat_mapping_key, load_text_vdf
from doomdeck.infrastructure.steam_shortcuts import get_bkv_str, load_shortcuts, shortcut_entries


def test_steam_shortcut_update_refuses_to_modify_files_when_steam_is_running(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    shortcuts_path = tmp_path / "Steam" / "userdata" / "123" / "config" / "shortcuts.vdf"
    logger = logging.getLogger("test")

    with pytest.raises(DoomDeckError, match="Steam appears to be running"):
        add_or_update_steam_shortcut(
            shortcuts_path,
            "Doom Runner",
            dirs.doomrunner / "DoomRunner.exe",
            dirs.doomrunner,
            dirs,
            SteamShortcutSettings(dry_run=False),
            logger,
            process_detector=lambda _patterns: True,
        )

    assert not shortcuts_path.exists()


def test_steam_shortcut_update_writes_shortcut_and_proton_mapping(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.backups.mkdir(parents=True)
    shortcuts_path = tmp_path / "Steam" / "userdata" / "123" / "config" / "shortcuts.vdf"
    logger = logging.getLogger("test")

    appid = add_or_update_steam_shortcut(
        shortcuts_path,
        "Doom Runner",
        dirs.doomrunner / "DoomRunner.exe",
        dirs.doomrunner,
        dirs,
        SteamShortcutSettings(dry_run=False, allow_steam_running=True, proton_compat_tool="proton_10"),
        logger,
        process_detector=lambda _patterns: True,
    )

    shortcuts = shortcut_entries(load_shortcuts(shortcuts_path))
    assert len(shortcuts) == 1
    shortcut = next(iter(shortcuts.values()))
    assert shortcut.type_code == BKV_OBJECT
    assert get_bkv_str(shortcut.value, "appname", "AppName") == "Doom Runner"
    assert get_bkv_str(shortcut.value, "exe", "Exe") == f'"{dirs.doomrunner / "DoomRunner.exe"}"'

    localconfig = load_text_vdf(shortcuts_path.parent / "localconfig.vdf")
    user_store = cast(TextVDFObject, localconfig["UserLocalConfigStore"])
    software = cast(TextVDFObject, user_store["Software"])
    valve = cast(TextVDFObject, software["Valve"])
    steam = cast(TextVDFObject, valve["Steam"])
    mapping = cast(TextVDFObject, steam["CompatToolMapping"])
    compat_entry = cast(TextVDFObject, mapping[compat_mapping_key(appid)])
    assert compat_entry["name"] == "proton_10"
