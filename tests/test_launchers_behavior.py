from __future__ import annotations

import logging

from doomdeck.application.launchers import write_launchers_and_manifest
from doomdeck.domain.paths import build_dirs


def test_generated_launchers_point_to_single_doomrunner_shortcut(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")

    manifest = write_launchers_and_manifest(dirs, None, None, dry_run=False, logger=logging.getLogger("test"))

    assert all("steam_shortcut_name" not in preset for preset in manifest["presets"])
    assert all("launch_options" not in preset for preset in manifest["presets"])
    launcher = (dirs.launchers / "Vanilla_Doom.sh").read_text(encoding="utf-8")
    assert "Open the Steam shortcut 'Doom Runner'" in launcher
    assert "DoomDeck - Vanilla Doom" not in launcher


def test_generated_manifest_omits_modded_presets_when_mod_files_are_missing(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")

    manifest = write_launchers_and_manifest(dirs, None, None, dry_run=False, logger=logging.getLogger("test"))

    preset_names = [preset["name"] for preset in manifest["presets"]]
    assert preset_names == ["Vanilla Doom", "UZDoom"]
    assert not (dirs.launchers / "Brutal_Doom.sh").exists()
    assert not (dirs.launchers / "Project_Brutality.sh").exists()


def test_generated_manifest_uses_mod_specific_uzdoom_control_profiles(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    brutal = dirs.brutal / "brutal-doom.pk3"
    project_brutality = dirs.project_brutality / "project-brutality.pk3"
    brutal.parent.mkdir(parents=True)
    project_brutality.parent.mkdir(parents=True)
    brutal.write_bytes(b"brutal")
    project_brutality.write_bytes(b"project")

    manifest = write_launchers_and_manifest(dirs, brutal, project_brutality, dry_run=False, logger=logging.getLogger("test"))

    presets = {preset["name"]: preset for preset in manifest["presets"]}
    assert presets["Brutal Doom"]["autoexec"] == str(dirs.uzdoom_config / "brutal" / "autoexec.cfg")
    assert presets["Project Brutality"]["autoexec"] == str(dirs.uzdoom_config / "project-brutality" / "autoexec.cfg")
