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
