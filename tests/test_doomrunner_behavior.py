from __future__ import annotations

from pathlib import Path

from doomdeck.application.doomrunner import (
    build_doomrunner_iwad_entries,
    build_doomrunner_options,
    build_doomrunner_preset,
    choose_doomrunner_default_iwad,
    choose_doomrunner_selected_preset,
    doomrunner_options_paths,
    doomrunner_quote_arg,
    launcher_slug,
)
from doomdeck.application.proton import proton_windows_path
from doomdeck.domain.paths import build_dirs


def test_doomrunner_options_are_written_to_data_path_before_config_compatibility_path(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")

    assert doomrunner_options_paths(dirs) == [
        dirs.xdg_data / "DoomRunner" / "options.json",
        dirs.xdg_config / "DoomRunner" / "options.json",
    ]


def test_doomrunner_iwad_entries_use_display_names_and_prefer_doom2(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM.WAD").write_text("", encoding="utf-8")
    (dirs.iwads / "DOOM2.WAD").write_text("", encoding="utf-8")

    entries = build_doomrunner_iwad_entries(dirs)

    assert entries == [
        {"name": "The Ultimate Doom", "path": proton_windows_path(dirs.iwads / "DOOM.WAD")},
        {"name": "Doom II: Hell on Earth", "path": proton_windows_path(dirs.iwads / "DOOM2.WAD")},
    ]
    assert choose_doomrunner_default_iwad(entries, dirs) == proton_windows_path(dirs.iwads / "DOOM2.WAD")


def test_doomrunner_preset_builds_mod_list_and_quoted_launcher_arguments(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    preset = {
        "name": "Project Brutality",
        "iwad": str(dirs.iwads / "DOOM2.WAD"),
        "files": [str(dirs.project_brutality / "project-brutality.pk3")],
        "config": str(dirs.uzdoom_config / "modern config" / "uzdoom.ini"),
        "autoexec": str(dirs.uzdoom_config / "modern config" / "autoexec.cfg"),
    }

    built = build_doomrunner_preset(dirs, preset)

    assert launcher_slug("Project Brutality!") == "Project_Brutality"
    assert doomrunner_quote_arg(Path('/tmp/quoted "path".cfg')) == '"/tmp/quoted \\"path\\".cfg"'
    assert built["selected_engine"] == "doomdeck-uzdoom"
    assert built["mods"] == [{"path": proton_windows_path(dirs.project_brutality / "project-brutality.pk3"), "checked": True}]
    assert built["alternative_paths"]["save_dir"] == proton_windows_path(dirs.saves / "project_brutality")
    assert f'-config "{proton_windows_path(dirs.uzdoom_config / "modern config" / "uzdoom.ini")}"' in built["additional_args"]
    assert f'+exec "{proton_windows_path(dirs.uzdoom_config / "modern config" / "autoexec.cfg")}"' in built["additional_args"]


def test_doomrunner_preset_keeps_raw_wad_paths_for_launching(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    wad_path = dirs.pwads / "DTWID.wad"
    preset = {
        "name": "Custom WAD",
        "iwad": str(dirs.iwads / "DOOM2.WAD"),
        "files": [str(wad_path)],
        "config": str(dirs.uzdoom_config / "classic" / "uzdoom.ini"),
        "autoexec": str(dirs.uzdoom_config / "classic" / "autoexec.cfg"),
    }

    built = build_doomrunner_preset(dirs, preset)

    assert built["mods"] == [{"path": proton_windows_path(wad_path), "checked": True}]
    assert "Doom The Way ID Did" not in str(built)


def test_doomrunner_options_select_highest_value_available_preset(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_text("", encoding="utf-8")
    manifest = {
        "presets": [
            {
                "name": "Vanilla Doom",
                "iwad": str(dirs.iwads / "DOOM2.WAD"),
                "files": [],
                "config": str(dirs.uzdoom_config / "classic" / "uzdoom.ini"),
                "autoexec": str(dirs.uzdoom_config / "classic" / "autoexec.cfg"),
            },
            {
                "name": "Brutal Doom",
                "iwad": str(dirs.iwads / "DOOM2.WAD"),
                "files": [str(dirs.brutal / "brutal-doom.pk3")],
                "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
            },
        ]
    }

    options = build_doomrunner_options(dirs, manifest)

    assert choose_doomrunner_selected_preset(options["presets"]) == "Brutal Doom"
    assert options["selected_preset"] == "Brutal Doom"
    assert options["engines"]["default_engine"] == "doomdeck-uzdoom"
    assert options["IWADs"]["default_iwad"] == proton_windows_path(dirs.iwads / "DOOM2.WAD")
    assert options["engines"]["engine_list"][0]["path"] == proton_windows_path(dirs.uzdoom / "uzdoom.exe")
    assert options["content_groups"] == manifest.get("content_groups", {})
    assert options["video_options"]["resolution_x"] == 1280
    assert options["video_options"]["resolution_y"] == 800
