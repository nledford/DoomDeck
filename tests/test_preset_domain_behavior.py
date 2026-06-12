from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.presets import EngineSpec, Preset, PresetManifest


def test_preset_rejects_empty_names() -> None:
    with pytest.raises(DoomDeckError, match="Preset name"):
        Preset(
            name="",
            category="UZDoom",
            engine="UZDoom",
            iwad=Path("/doom/iwads/DOOM2.WAD"),
            config=Path("/doom/configs/uzdoom.ini"),
            autoexec=Path("/doom/configs/autoexec.cfg"),
            launcher=Path("/doom/launchers/UZDoom.sh"),
        )


def test_preset_serializes_existing_manifest_shape() -> None:
    preset = Preset(
        name="Brutal Doom",
        category="Brutal Doom",
        engine="UZDoom",
        iwad=Path("/doom/iwads/DOOM2.WAD"),
        files=(Path("/doom/mods/brutal-doom/brutal-doom.pk3"),),
        config=Path("/doom/configs/uzdoom/modern/uzdoom.ini"),
        autoexec=Path("/doom/configs/uzdoom/modern/autoexec.cfg"),
        launcher=Path("/doom/launchers/Brutal_Doom.sh"),
        missing_hint="Install Brutal Doom.",
        notes="Requires Brutal Doom.",
    )

    assert preset.as_json_object() == {
        "name": "Brutal Doom",
        "category": "Brutal Doom",
        "engine": "UZDoom",
        "iwad": "/doom/iwads/DOOM2.WAD",
        "files": ["/doom/mods/brutal-doom/brutal-doom.pk3"],
        "config": "/doom/configs/uzdoom/modern/uzdoom.ini",
        "autoexec": "/doom/configs/uzdoom/modern/autoexec.cfg",
        "launcher": "/doom/launchers/Brutal_Doom.sh",
        "missing_hint": "Install Brutal Doom.",
        "notes": "Requires Brutal Doom.",
    }


def test_preset_launch_metadata_is_explicit() -> None:
    preset = Preset(
        name="UZDoom",
        category="UZDoom",
        engine="UZDoom",
        iwad=Path("/doom/iwads/DOOM2.WAD"),
        config=Path("/doom/configs/uzdoom/modern/uzdoom.ini"),
        autoexec=Path("/doom/configs/uzdoom/modern/autoexec.cfg"),
        launcher=Path("/doom/launchers/UZDoom.sh"),
    ).with_launch_metadata("DoomDeck - UZDoom", "-iwad DOOM2.WAD")

    data = preset.as_json_object()

    assert data["steam_shortcut_name"] == "DoomDeck - UZDoom"
    assert data["launch_options"] == "-iwad DOOM2.WAD"


def test_preset_manifest_serializes_current_schema() -> None:
    manifest = PresetManifest(
        generated_at="2026-06-12T12:00:00",
        root=Path("/doom"),
        engine=EngineSpec(
            name="UZDoom",
            executable=Path("/doom/source-ports/uzdoom/uzdoom.exe"),
            family="UZDoom/ZDoom",
            config_directory=Path("/doom/configs/uzdoom"),
            data_directory=Path("/doom"),
        ),
        iwad_directory=Path("/doom/iwads"),
        pwad_directory=Path("/doom/pwads"),
        mod_directories={
            "brutal_doom": Path("/doom/mods/brutal-doom"),
        },
        presets=(),
        content_groups={"presets": []},
    )

    serialized = manifest.as_json_object()
    engine = serialized["engine"]

    assert isinstance(engine, dict)
    engine_data = cast(dict[str, object], engine)
    assert serialized["schema"] == "doom-deck-setup/preset-manifest/v1"
    assert engine_data["executable"] == "/doom/source-ports/uzdoom/uzdoom.exe"
    assert serialized["mod_directories"] == {"brutal_doom": "/doom/mods/brutal-doom"}
    assert serialized["content_groups"] == {"presets": []}


def test_preset_manifest_round_trips_from_json_shape(tmp_path: Path) -> None:
    engine = EngineSpec(
        name="UZDoom",
        executable=tmp_path / "uzdoom.exe",
        family="UZDoom/ZDoom",
        config_directory=tmp_path / "configs" / "uzdoom",
        data_directory=tmp_path,
    )
    preset = Preset(
        name="Vanilla Doom",
        category="Vanilla",
        engine="UZDoom",
        iwad=tmp_path / "iwads" / "DOOM2.WAD",
        files=(tmp_path / "mods" / "example.pk3",),
        config=tmp_path / "configs" / "uzdoom.ini",
        autoexec=tmp_path / "configs" / "autoexec.cfg",
        launcher=tmp_path / "launchers" / "Vanilla_Doom.sh",
        missing_hint="Install the mod",
        notes="Generated preset",
    ).with_launch_metadata("DoomDeck - Vanilla Doom", "-iwad DOOM2.WAD")
    manifest = PresetManifest(
        generated_at="2026-06-12T12:00:00",
        root=tmp_path,
        engine=engine,
        iwad_directory=tmp_path / "iwads",
        pwad_directory=tmp_path / "pwads",
        mod_directories={"mods": tmp_path / "mods"},
        presets=(preset,),
        content_groups={"presets": []},
    )

    parsed = PresetManifest.from_json_object(manifest.as_json_object())

    assert parsed == manifest


def test_preset_manifest_rejects_malformed_preset_json(tmp_path: Path) -> None:
    engine = EngineSpec(
        name="UZDoom",
        executable=tmp_path / "uzdoom.exe",
        family="UZDoom/ZDoom",
        config_directory=tmp_path / "configs" / "uzdoom",
        data_directory=tmp_path,
    ).as_json_object()
    data = {
        "schema": "doom-deck-setup/preset-manifest/v1",
        "generated_at": "2026-06-12T12:00:00",
        "warning": "Generated",
        "root": str(tmp_path),
        "engine": engine,
        "iwad_directory": str(tmp_path / "iwads"),
        "pwad_directory": str(tmp_path / "pwads"),
        "mod_directories": {"mods": str(tmp_path / "mods")},
        "presets": {"name": "not-a-list"},
    }

    with pytest.raises(DoomDeckError, match="Preset manifest presets must be a list"):
        PresetManifest.from_json_object(data)
