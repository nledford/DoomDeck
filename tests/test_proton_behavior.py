from __future__ import annotations

from pathlib import Path

from doomdeck.application.proton import (
    build_uzdoom_launch_options,
    proton_linux_path,
    proton_quote_arg,
    proton_windows_path,
)
from doomdeck.domain.paths import build_dirs


def test_absolute_linux_paths_are_converted_to_proton_z_drive_paths() -> None:
    assert proton_windows_path(Path("/home/deck/Games/Doom/iwads/DOOM2.WAD")) == r"Z:\home\deck\Games\Doom\iwads\DOOM2.WAD"
    assert proton_linux_path(r"Z:\home\deck\Games\Doom\iwads\DOOM2.WAD") == Path("/home/deck/Games/Doom/iwads/DOOM2.WAD")


def test_proton_launch_arguments_quote_windows_paths() -> None:
    assert proton_quote_arg(r'Z:\home\deck\Games\Doom\mods\quoted "mod".pk3') == r'"Z:\home\deck\Games\Doom\mods\quoted \"mod\".pk3"'


def test_uzdoom_launch_options_use_windows_paths_for_iwad_config_autoexec_and_mods(tmp_path: Path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    iwad = dirs.iwads / "DOOM2.WAD"
    config = dirs.uzdoom_config / "modern" / "uzdoom.ini"
    autoexec = dirs.uzdoom_config / "modern" / "autoexec.cfg"
    mod = dirs.brutal / "brutal-doom.pk3"
    preset = {
        "iwad": str(iwad),
        "files": [str(mod)],
        "config": str(config),
        "autoexec": str(autoexec),
    }

    launch_options = build_uzdoom_launch_options(preset)

    assert "-noautoload" in launch_options
    assert f"-iwad {proton_quote_arg(proton_windows_path(iwad))}" in launch_options
    assert f"-config {proton_quote_arg(proton_windows_path(config))}" in launch_options
    assert f"+exec {proton_quote_arg(proton_windows_path(autoexec))}" in launch_options
    assert f"-file {proton_quote_arg(proton_windows_path(mod))}" in launch_options
