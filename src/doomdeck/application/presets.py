"""Build DoomDeck preset manifests from managed domain state."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Optional

from doomdeck.application.content_groups import content_groups_from_manifest
from doomdeck.domain.models import Dirs
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD
from doomdeck.domain.presets import EngineSpec, Preset, PresetManifest
from doomdeck.domain.wads import DEFAULT_PRESET_IWADS, iwad_dest_name


def choose_default_preset_iwad(dirs: Dirs) -> Optional[Path]:
    for iwad_name in DEFAULT_PRESET_IWADS:
        iwad_path = dirs.iwads / iwad_dest_name(iwad_name)
        if iwad_path.exists():
            return iwad_path
    return None


def build_preset_manifest_model(dirs: Dirs, brutal_path: Optional[Path], project_brutality_path: Optional[Path]) -> PresetManifest:
    presets: list[Preset] = []
    default_iwad = choose_default_preset_iwad(dirs)
    if default_iwad:
        presets.extend(
            [
                Preset(
                    name="Vanilla Doom",
                    category="Vanilla",
                    engine="UZDoom",
                    iwad=default_iwad,
                    config=dirs.uzdoom_config / "classic" / "uzdoom.ini",
                    autoexec=dirs.uzdoom_config / "classic" / "autoexec.cfg",
                    launcher=dirs.launchers / "Vanilla_Doom.sh",
                    notes="Classic-style UZDoom launch. Change the selected IWAD in Doom Runner to switch Doom, Doom II, TNT, or Plutonia.",
                ),
                Preset(
                    name="UZDoom",
                    category="UZDoom",
                    engine="UZDoom",
                    iwad=default_iwad,
                    config=dirs.uzdoom_config / "modern" / "uzdoom.ini",
                    autoexec=dirs.uzdoom_config / "modern" / "autoexec.cfg",
                    launcher=dirs.launchers / "UZDoom.sh",
                    notes="UZDoom without gameplay mods. Change the selected IWAD in Doom Runner to switch base games.",
                ),
                Preset(
                    name=BRUTAL_DOOM_MOD.name,
                    category=BRUTAL_DOOM_MOD.name,
                    engine="UZDoom",
                    iwad=default_iwad,
                    files=(brutal_path or BRUTAL_DOOM_MOD.alias_path(dirs.brutal),),
                    config=dirs.uzdoom_config / "modern" / "uzdoom.ini",
                    autoexec=dirs.uzdoom_config / "modern" / "autoexec.cfg",
                    launcher=dirs.launchers / "Brutal_Doom.sh",
                    missing_hint="Rerun install to check ModDB, or use --brutal-doom-file/--brutal-doom-url.",
                    notes=f"Requires mods/brutal-doom/{BRUTAL_DOOM_MOD.alias}. Change the selected IWAD in Doom Runner to switch base games.",
                ),
                Preset(
                    name=PROJECT_BRUTALITY_MOD.name,
                    category=PROJECT_BRUTALITY_MOD.name,
                    engine="UZDoom",
                    iwad=default_iwad,
                    files=(project_brutality_path or PROJECT_BRUTALITY_MOD.alias_path(dirs.project_brutality),),
                    config=dirs.uzdoom_config / "modern" / "uzdoom.ini",
                    autoexec=dirs.uzdoom_config / "modern" / "autoexec.cfg",
                    launcher=dirs.launchers / "Project_Brutality.sh",
                    missing_hint="Rerun install to download Project Brutality, or use --project-brutality-file /path/to/Project_Brutality.pk3.",
                    notes="Downloads Project Brutality from GitHub and installs it as mods/project-brutality/project-brutality.pk3.",
                ),
            ]
        )
    manifest = PresetManifest(
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
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
        mod_directories={
            "brutal_doom": dirs.brutal,
            "project_brutality": dirs.project_brutality,
        },
        presets=tuple(presets),
    )
    return manifest.with_content_groups(content_groups_from_manifest(dirs, manifest.as_json_object()))


def build_preset_manifest(dirs: Dirs, brutal_path: Optional[Path], project_brutality_path: Optional[Path]) -> dict[str, Any]:
    return build_preset_manifest_model(dirs, brutal_path, project_brutality_path).as_json_object()
