from __future__ import annotations

import argparse
import json
import logging
import zipfile
from pathlib import Path

import pytest

from doomdeck.application.doomrunner import DoomRunnerLiveConfigSettings, doomrunner_options_paths, write_doomrunner_live_config
from doomdeck.application.launchers import write_launchers_and_manifest
from doomdeck.application.steam_input import write_managed_steam_input_profile
from doomdeck.application.uzdoom import write_uzdoom_configs
from doomdeck.application.validation import (
    InstallationValidator,
    add_validation_item,
    format_validation_report,
    validation_has_failures,
)
from doomdeck.cli import validate_internal
from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import all_managed_dirs, build_dirs
from doomdeck.infrastructure.binary_vdf import BinaryVDF
from doomdeck.infrastructure.steam_shortcuts import empty_shortcuts_root, make_shortcut_entry, shortcut_entries


def make_executable(path: Path) -> None:
    path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_validation_items_use_explicit_levels_and_format_report() -> None:
    report = []

    add_validation_item(report, "PASS", "First check passed")
    add_validation_item(report, "FAIL", "Second check failed")

    assert validation_has_failures(report)
    assert report[0].level == "PASS"
    assert format_validation_report(report) == (
        "\n"
        "Validation report\n"
        "=================\n"
        "[PASS] First check passed\n"
        "[FAIL] Second check failed\n"
    )


def test_installation_validator_uses_injected_environment_check(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    validator = InstallationValidator(
        steamos_detector=lambda: (True, "SteamOS test fixture"),
        shell_syntax_checker=lambda _path: True,
    )

    report = validator.validate(dirs, SteamInfo(None, None, None, [], None))

    messages = {item.message: item.level for item in report}
    assert messages["SteamOS test fixture"] == "PASS"
    assert messages[f"Required path exists: {dirs.root}"] == "FAIL"


def test_installation_validator_checks_shell_syntax_through_dependency(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    script_path = dirs.launchers / "example.sh"
    script_path.parent.mkdir(parents=True)
    make_executable(script_path)
    checked_paths: list[Path] = []

    def reject_shell_syntax(path: Path) -> bool:
        checked_paths.append(path)
        return False

    validator = InstallationValidator(
        steamos_detector=lambda: (True, "SteamOS test fixture"),
        shell_syntax_checker=reject_shell_syntax,
    )

    report = validator.validate(dirs, SteamInfo(None, None, None, [], None))

    assert script_path in checked_paths
    messages = {item.message: item.level for item in report}
    assert messages[f"Shell syntax valid for {script_path}"] == "FAIL"


def test_validation_reports_non_object_json_configs_without_crashing(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")
    args = argparse.Namespace(dry_run=False)
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    live_options_path = doomrunner_options_paths(dirs)[0]
    manifest_path.parent.mkdir(parents=True)
    live_options_path.parent.mkdir(parents=True)
    manifest_path.write_text("[]", encoding="utf-8")
    live_options_path.write_text("[]", encoding="utf-8")

    report = validate_internal(args, dirs, SteamInfo(None, None, None, [], None), logger)

    messages = {item.message for item in report}
    assert f"Preset manifest JSON must be an object: {manifest_path}" in messages
    assert f"Doom Runner generated options JSON must be an object: {live_options_path}" in messages


def test_validation_reports_malformed_preset_manifest_without_crashing(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")
    args = argparse.Namespace(dry_run=False)
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
{
  "schema": "doom-deck-setup/preset-manifest/v1",
  "generated_at": "2026-06-12T12:00:00",
  "root": "/tmp/Doom",
  "engine": {},
  "iwad_directory": "/tmp/Doom/iwads",
  "pwad_directory": "/tmp/Doom/pwads",
  "mod_directories": {},
  "presets": {}
}
""",
        encoding="utf-8",
    )

    report = validate_internal(args, dirs, SteamInfo(None, None, None, [], None), logger)

    failures = [item.message for item in report if item.level == "FAIL"]
    assert any("Preset manifest structure is invalid" in failure for failure in failures)
    assert any("Preset manifest presets must be a list" in failure for failure in failures)


def test_uzdoom_configs_bind_quicksave_keys_without_direct_stick_click_quickload(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")

    write_uzdoom_configs(dirs, dry_run=False, logger=logger)

    for profile in ["classic", "modern", "brutal", "project-brutality"]:
        autoexec = (dirs.uzdoom_config / profile / "autoexec.cfg").read_text(encoding="utf-8").lower()
        assert "bind f6 quicksave" in autoexec
        assert "bind f9 quickload" in autoexec
        assert "bind pad_lthumb quicksave" not in autoexec
        assert "bind pad_rthumb quickload" not in autoexec
        assert "bind e +deck_use_select" in autoexec


def test_validation_accepts_a_generated_managed_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")
    args = argparse.Namespace(dry_run=False, skip_doomrunner_live_config=False)

    for directory in all_managed_dirs(dirs):
        directory.mkdir(parents=True, exist_ok=True)

    (dirs.doomrunner / "DoomRunner.exe").write_bytes(b"exe")
    (dirs.uzdoom / "uzdoom.exe").write_bytes(b"exe")
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    (dirs.brutal / "brutal-doom.pk3").write_bytes(b"brutal")
    (dirs.brutal / "brutal-doom.json").write_text("{}", encoding="utf-8")
    with zipfile.ZipFile(dirs.project_brutality / "project-brutality.pk3", "w") as archive:
        archive.writestr("gameinfo.txt", "")
        archive.writestr("zscript.zc", "")
    (dirs.project_brutality / "project-brutality.json").write_text("{}", encoding="utf-8")
    (dirs.backups / "existing-backup").write_text("", encoding="utf-8")

    write_uzdoom_configs(dirs, dry_run=False, logger=logger)
    write_managed_steam_input_profile(dirs, dry_run=False, logger=logger)
    manifest = write_launchers_and_manifest(
        dirs,
        dirs.brutal / "brutal-doom.pk3",
        dirs.project_brutality / "project-brutality.pk3",
        dry_run=False,
        logger=logger,
    )
    monkeypatch.setattr("doomdeck.cli.detect_steamos", lambda: (True, "SteamOS test fixture"))
    write_doomrunner_live_config(
        dirs,
        manifest,
        DoomRunnerLiveConfigSettings(dry_run=False),
        logger,
        process_detector=lambda _patterns: False,
    )

    report = validate_internal(args, dirs, SteamInfo(None, None, None, [], None), logger)

    failures = [item.message for item in report if item.level == "FAIL"]
    assert failures == []
    assert any("Preset manifest includes Project Brutality preset" in item.message for item in report)
    assert any("Doom Runner generated config has launchable presets" in item.message for item in report)
    assert any("Project Brutality archive has expected UZDoom root files" in item.message for item in report)


def test_validation_fails_generated_preset_that_references_missing_mod_file(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")
    args = argparse.Namespace(dry_run=False, skip_doomrunner_live_config=False)

    for directory in all_managed_dirs(dirs):
        directory.mkdir(parents=True, exist_ok=True)
    (dirs.doomrunner / "DoomRunner.exe").write_bytes(b"exe")
    (dirs.uzdoom / "uzdoom.exe").write_bytes(b"exe")
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    write_uzdoom_configs(dirs, dry_run=False, logger=logger)
    write_managed_steam_input_profile(dirs, dry_run=False, logger=logger)
    manifest = {
        "schema": "doom-deck-setup/preset-manifest/v1",
        "generated_at": "2026-06-12T12:00:00",
        "warning": "Generated",
        "root": str(dirs.root),
        "engine": {
            "name": "UZDoom",
            "executable": str(dirs.uzdoom / "uzdoom.exe"),
            "family": "UZDoom/ZDoom",
            "config_directory": str(dirs.uzdoom_config),
            "data_directory": str(dirs.root),
        },
        "iwad_directory": str(dirs.iwads),
        "pwad_directory": str(dirs.pwads),
        "mod_directories": {"brutal_doom": str(dirs.brutal)},
        "presets": [
            {
                "name": "Brutal Doom",
                "category": "Brutal Doom",
                "engine": "UZDoom",
                "iwad": str(dirs.iwads / "DOOM2.WAD"),
                "files": [str(dirs.brutal / "brutal-doom.pk3")],
                "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
                "launcher": str(dirs.launchers / "Brutal_Doom.sh"),
            }
        ],
    }
    (dirs.doomrunner_config / "preset-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_doomrunner_live_config(
        dirs,
        manifest,
        DoomRunnerLiveConfigSettings(dry_run=False),
        logger,
        process_detector=lambda _patterns: False,
    )

    report = validate_internal(args, dirs, SteamInfo(None, None, None, [], None), logger)

    failures = [item.message for item in report if item.level == "FAIL"]
    assert any(f"Preset Brutal Doom mod file reference: {dirs.brutal / 'brutal-doom.pk3'}" == failure for failure in failures)
    assert any("Doom Runner generated config resolves UZDoom launch paths for presets" in failure for failure in failures)


def test_validation_reports_extra_doomdeck_steam_shortcuts(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    shortcuts_path = tmp_path / "Steam" / "userdata" / "123" / "config" / "shortcuts.vdf"
    shortcuts_path.parent.mkdir(parents=True)
    root = empty_shortcuts_root()
    shortcuts = shortcut_entries(root)
    shortcuts["0"] = make_shortcut_entry("Doom Runner", dirs.doomrunner / "DoomRunner.exe", dirs.doomrunner, tags=["Doom"])
    shortcuts["1"] = make_shortcut_entry(
        "DoomDeck - Project Brutality",
        dirs.uzdoom / "uzdoom.exe",
        dirs.uzdoom,
        tags=["Doom"],
        launch_options="-iwad DOOM2.WAD",
    )
    shortcuts_path.write_bytes(BinaryVDF.dumps(root))
    validator = InstallationValidator(
        steamos_detector=lambda: (True, "SteamOS test fixture"),
        shell_syntax_checker=lambda _path: True,
    )

    report = validator.validate(dirs, SteamInfo(tmp_path / "Steam", "123", shortcuts_path, [], None))

    messages = {item.message: item.level for item in report}
    assert messages["Exactly one Steam shortcut exists for Windows Doom Runner with expected executable path"] == "PASS"
    assert messages["No extra DoomDeck preset Steam shortcuts remain: DoomDeck - Project Brutality"] == "FAIL"
