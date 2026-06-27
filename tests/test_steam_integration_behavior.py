from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import cast

import pytest

from doomdeck.application.doomrunner import DoomRunnerLiveConfigSettings, doomrunner_options_paths, write_doomrunner_live_config
from doomdeck.application.launchers import write_launchers_and_manifest
from doomdeck.application.steam import SteamShortcutSettings, add_or_update_doomrunner_shortcut, add_or_update_steam_shortcut
from doomdeck.application.steam import doomrunner_proton_options_path
from doomdeck.application.steam_input import deploy_steam_input_profile, steam_input_profile_path, write_managed_steam_input_profile
from doomdeck.application.uzdoom import write_uzdoom_configs
from doomdeck.application.proton import proton_linux_path
from doomdeck.domain.models import DoomDeckError, SteamInfo
from doomdeck.domain.paths import all_managed_dirs, build_dirs
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


def test_simulated_post_run_flow_writes_single_shortcut_and_launchable_doomrunner_options(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    steam_root = tmp_path / "Steam"
    shortcuts_path = steam_root / "userdata" / "123" / "config" / "shortcuts.vdf"
    steam = SteamInfo(
        steam_root=steam_root,
        user_id="123",
        shortcuts_vdf=shortcuts_path,
        library_folders=[steam_root],
        app_install_dir=steam_root / "steamapps" / "common" / "DOOM",
        localconfig_vdf=shortcuts_path.parent / "localconfig.vdf",
    )
    logger = logging.getLogger("test")
    for directory in all_managed_dirs(dirs):
        directory.mkdir(parents=True, exist_ok=True)
    (dirs.doomrunner / "DoomRunner.exe").write_bytes(b"doomrunner")
    (dirs.uzdoom / "uzdoom.exe").write_bytes(b"uzdoom")
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    brutal = dirs.brutal / "brutal-doom.pk3"
    project_brutality = dirs.project_brutality / "project-brutality.pk3"
    brutal.write_bytes(b"brutal")
    project_brutality.write_bytes(b"project-brutality")

    write_uzdoom_configs(dirs, dry_run=False, logger=logger)
    write_managed_steam_input_profile(dirs, dry_run=False, logger=logger)
    manifest = write_launchers_and_manifest(dirs, brutal, project_brutality, dry_run=False, logger=logger)
    settings = SteamShortcutSettings(dry_run=False, proton_compat_tool="proton_10")
    first_appid = add_or_update_doomrunner_shortcut(shortcuts_path, dirs, settings, logger, process_detector=lambda _patterns: False)
    second_appid = add_or_update_doomrunner_shortcut(shortcuts_path, dirs, settings, logger, process_detector=lambda _patterns: False)
    proton_options = doomrunner_proton_options_path(steam, second_appid)
    assert proton_options is not None
    deploy_steam_input_profile(dirs, steam, second_appid, dry_run=False, logger=logger)
    write_doomrunner_live_config(
        dirs,
        manifest,
        DoomRunnerLiveConfigSettings(dry_run=False, extra_options_paths=(proton_options,)),
        logger,
        process_detector=lambda _patterns: False,
    )

    shortcuts = shortcut_entries(load_shortcuts(shortcuts_path))
    names = [get_bkv_str(value.value, "appname", "AppName") for value in shortcuts.values() if value.type_code == BKV_OBJECT]
    assert first_appid == second_appid
    assert names.count("Doom Runner") == 1
    assert all(not name.startswith("DoomDeck - ") for name in names)

    portable_options = doomrunner_options_paths(dirs)[0]
    assert portable_options == dirs.doomrunner / "options.json"
    assert portable_options.exists()
    assert proton_options.exists()
    options = json.loads(portable_options.read_text(encoding="utf-8"))
    assert json.loads(proton_options.read_text(encoding="utf-8")) == options

    engine = next(engine for engine in options["engines"]["engine_list"] if engine["id"] == "doomdeck-uzdoom")
    brutal_preset = next(preset for preset in options["presets"] if preset["name"] == "Brutal Doom")
    assert proton_linux_path(engine["path"]) == dirs.uzdoom / "uzdoom.exe"
    assert proton_linux_path(brutal_preset["selected_IWAD"]) == dirs.iwads / "DOOM2.WAD"
    assert [proton_linux_path(mod["path"]) for mod in brutal_preset["mods"] if mod["checked"]] == [brutal]
    additional_args = shlex.split(brutal_preset["additional_args"])
    assert proton_linux_path(additional_args[additional_args.index("-config") + 1]) == dirs.uzdoom_config / "brutal" / "uzdoom.ini"
    assert proton_linux_path(additional_args[additional_args.index("+exec") + 1]) == dirs.uzdoom_config / "brutal" / "autoexec.cfg"
    assert "-savedir" not in brutal_preset["additional_args"]
    deployed_profile = steam_input_profile_path(steam)
    assert deployed_profile is not None and deployed_profile.exists()
