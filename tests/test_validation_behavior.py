from __future__ import annotations

import argparse
import logging
import zipfile
from pathlib import Path

import pytest

from doomdeck.application.doomrunner import doomrunner_options_paths
from doomdeck.application.validation import add_validation_item, format_validation_report, validation_has_failures
from doomdeck.cli import (
    validate_internal,
    write_doomrunner_live_config,
    write_launchers_and_manifest,
    write_uzdoom_configs,
    write_wrappers,
)
from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import all_managed_dirs, build_dirs


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
    assert f"Doom Runner live options JSON must be an object: {live_options_path}" in messages


def test_validation_accepts_a_generated_managed_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    logger = logging.getLogger("test")
    args = argparse.Namespace(dry_run=False, skip_doomrunner_live_config=False)

    for directory in all_managed_dirs(dirs):
        directory.mkdir(parents=True, exist_ok=True)

    make_executable(dirs.doomrunner / "DoomRunner.AppImage")
    make_executable(dirs.uzdoom / "uzdoom.AppImage")
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    (dirs.brutal / "brutal-doom.pk3").write_bytes(b"brutal")
    (dirs.brutal / "brutal-doom.json").write_text("{}", encoding="utf-8")
    with zipfile.ZipFile(dirs.project_brutality / "project-brutality.pk3", "w") as archive:
        archive.writestr("gameinfo.txt", "")
        archive.writestr("zscript.zc", "")
    (dirs.project_brutality / "project-brutality.json").write_text("{}", encoding="utf-8")
    (dirs.backups / "existing-backup").write_text("", encoding="utf-8")

    write_wrappers(dirs, dry_run=False, logger=logger)
    write_uzdoom_configs(dirs, dry_run=False, logger=logger)
    manifest = write_launchers_and_manifest(
        dirs,
        dirs.brutal / "brutal-doom.pk3",
        dirs.project_brutality / "project-brutality.pk3",
        dry_run=False,
        logger=logger,
    )
    monkeypatch.setattr("doomdeck.cli.is_process_running", lambda _patterns: False)
    monkeypatch.setattr("doomdeck.cli.detect_steamos", lambda: (True, "SteamOS test fixture"))
    write_doomrunner_live_config(dirs, manifest, args, logger)

    report = validate_internal(args, dirs, SteamInfo(None, None, None, [], None), logger)

    failures = [item.message for item in report if item.level == "FAIL"]
    assert failures == []
    assert any("Preset manifest includes Project Brutality preset" in item.message for item in report)
    assert any("Doom Runner live config has launchable presets" in item.message for item in report)
    assert any("Project Brutality archive has expected UZDoom root files" in item.message for item in report)
