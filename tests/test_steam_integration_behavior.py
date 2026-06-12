from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest

from doomdeck.application.steam import SteamShortcutSettings, add_or_update_doomrunner_shortcut, add_or_update_steam_shortcut
from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.paths import build_dirs
from doomdeck.infrastructure.binary_vdf import BKV_OBJECT, BinaryVDF
from doomdeck.infrastructure.steam_compat import TextVDFObject, compat_mapping_key, load_text_vdf
from doomdeck.infrastructure.steam_shortcuts import empty_shortcuts_root, get_bkv_str, load_shortcuts, make_shortcut_entry, shortcut_entries


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


def test_doomrunner_shortcut_update_removes_extra_doomdeck_shortcuts(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.backups.mkdir(parents=True)
    shortcuts_path = tmp_path / "Steam" / "userdata" / "123" / "config" / "shortcuts.vdf"
    shortcuts_path.parent.mkdir(parents=True)
    logger = logging.getLogger("test")
    root = empty_shortcuts_root()
    shortcuts = shortcut_entries(root)
    shortcuts["0"] = make_shortcut_entry("Doom Runner", Path("/old/DoomRunner.exe"), Path("/old"), tags=["Doom"])
    shortcuts["1"] = make_shortcut_entry("Doom Runner", Path("/duplicate/DoomRunner.exe"), Path("/duplicate"), tags=["Doom"])
    shortcuts["2"] = make_shortcut_entry(
        "DoomDeck - Brutal Doom",
        dirs.uzdoom / "uzdoom.exe",
        dirs.uzdoom,
        tags=["Doom"],
        launch_options="-iwad DOOM2.WAD",
    )
    shortcuts["3"] = make_shortcut_entry("Unrelated Tool", Path("/usr/bin/true"), Path("/usr/bin"), tags=["Tools"])
    shortcuts_path.write_bytes(BinaryVDF.dumps(root))

    add_or_update_doomrunner_shortcut(
        shortcuts_path,
        dirs,
        SteamShortcutSettings(dry_run=False, proton_compat_tool="proton_10"),
        logger,
        process_detector=lambda _patterns: False,
    )

    updated = shortcut_entries(load_shortcuts(shortcuts_path))
    names = [get_bkv_str(value.value, "appname", "AppName") for value in updated.values() if value.type_code == BKV_OBJECT]
    assert names.count("Doom Runner") == 1
    assert "DoomDeck - Brutal Doom" not in names
    assert "Unrelated Tool" in names
