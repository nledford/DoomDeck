from __future__ import annotations

import logging
from pathlib import Path

import pytest

from doomdeck.application.doomrunner import (
    DoomRunnerLiveConfigSettings,
    build_doomrunner_iwad_entries,
    build_doomrunner_options,
    build_doomrunner_preset,
    choose_doomrunner_default_iwad,
    choose_doomrunner_selected_preset,
    doomrunner_options_paths,
    doomrunner_quote_arg,
    launcher_slug,
    write_doomrunner_live_config,
)
from doomdeck.application.proton import proton_windows_path
from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.paths import build_dirs
from doomdeck.domain.presets import EngineSpec, Preset, PresetManifest


def test_doomrunner_options_are_written_to_windows_portable_path_first(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")

    assert doomrunner_options_paths(dirs) == [
        dirs.doomrunner / "options.json",
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
    assert "-savedir" not in built["additional_args"]


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
    dirs.brutal.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_text("", encoding="utf-8")
    (dirs.brutal / "brutal-doom.pk3").write_text("", encoding="utf-8")
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


def test_doomrunner_options_omit_modded_presets_without_installed_mod_files(tmp_path) -> None:
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

    preset_names = [preset["name"] for preset in options["presets"]]
    assert preset_names == ["Vanilla Doom"]
    assert options["selected_preset"] == "Vanilla Doom"


def test_doomrunner_options_accept_typed_manifest(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    dirs.brutal.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_text("", encoding="utf-8")
    (dirs.brutal / "brutal-doom.pk3").write_text("", encoding="utf-8")
    manifest = PresetManifest(
        generated_at="2026-06-12T12:00:00",
        root=dirs.root,
        engine=EngineSpec(
            name="UZDoom",
            executable=dirs.uzdoom / "uzdoom.exe",
            family="UZDoom/ZDoom",
            config_directory=dirs.uzdoom_config,
            data_directory=dirs.root,
        ),
        iwad_directory=dirs.iwads,
        pwad_directory=dirs.pwads,
        mod_directories={"brutal_doom": dirs.brutal},
        presets=(
            Preset(
                name="Brutal Doom",
                category="Brutal Doom",
                engine="UZDoom",
                iwad=dirs.iwads / "DOOM2.WAD",
                files=(dirs.brutal / "brutal-doom.pk3",),
                config=dirs.uzdoom_config / "modern" / "uzdoom.ini",
                autoexec=dirs.uzdoom_config / "modern" / "autoexec.cfg",
                launcher=dirs.launchers / "Brutal_Doom.sh",
            ),
        ),
        content_groups={"mods": []},
    )

    options = build_doomrunner_options(dirs, manifest)

    assert options["selected_preset"] == "Brutal Doom"
    assert options["presets"][0]["mods"] == [{"path": proton_windows_path(dirs.brutal / "brutal-doom.pk3"), "checked": True}]
    assert options["content_groups"] == {"mods": []}


def test_doomrunner_live_config_refuses_to_write_while_doomrunner_is_running(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")

    with pytest.raises(DoomDeckError, match="Doom Runner appears to be running"):
        write_doomrunner_live_config(
            dirs,
            {"presets": []},
            DoomRunnerLiveConfigSettings(dry_run=False),
            logger,
            process_detector=lambda _patterns: True,
        )


def test_doomrunner_live_config_writes_options_and_preset_directories(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_text("", encoding="utf-8")
    extra_options_path = tmp_path / "compatdata" / "DoomRunner" / "options.json"
    logger = logging.getLogger("test")
    manifest = {
        "presets": [
            {
                "name": "Brutal Doom",
                "iwad": str(dirs.iwads / "DOOM2.WAD"),
                "files": [str(dirs.brutal / "brutal-doom.pk3")],
                "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
            },
        ]
    }

    write_doomrunner_live_config(
        dirs,
        manifest,
        DoomRunnerLiveConfigSettings(dry_run=False, extra_options_paths=(extra_options_path,)),
        logger,
        process_detector=lambda _patterns: False,
    )

    assert doomrunner_options_paths(dirs)[0].exists()
    assert doomrunner_options_paths(dirs)[1].exists()
    assert doomrunner_options_paths(dirs)[2].exists()
    assert extra_options_path.exists()
    assert (dirs.saves / "brutal_doom").is_dir()
    assert (dirs.screenshots / "brutal_doom").is_dir()
