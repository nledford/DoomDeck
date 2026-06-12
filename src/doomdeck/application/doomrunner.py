"""Build Doom Runner options from DoomDeck state."""
from __future__ import annotations

import dataclasses
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, cast

from doomdeck.application.proton import proton_windows_path
from doomdeck.domain.deck import STEAM_DECK_HEIGHT, STEAM_DECK_WIDTH
from doomdeck.domain.doomrunner import (
    DoomRunnerEngine,
    DoomRunnerIWAD,
    DoomRunnerMod,
    DoomRunnerOptions,
    DoomRunnerPreset,
    DoomRunnerPresetPaths,
)
from doomdeck.domain.models import Dirs, DoomDeckError
from doomdeck.domain.presets import Preset, PresetManifest
from doomdeck.domain.wads import DOOMRUNNER_IWAD_DISPLAY_NAMES, iwad_dest_name
from doomdeck.infrastructure.files import atomic_write_text, backup_path
from doomdeck.infrastructure.processes import is_process_running

DOOMRUNNER_OPTIONS_VERSION = "1.9.2"
DOOMRUNNER_ENGINE_ID = "doomdeck-uzdoom"
DOOMRUNNER_ENGINE_NAME = "UZDoom"
PresetInput = Preset | Mapping[str, object]
ManifestInput = PresetManifest | Mapping[str, object]
ProcessDetector = Callable[[list[str]], bool]


@dataclasses.dataclass(frozen=True)
class DoomRunnerLiveConfigSettings:
    dry_run: bool
    skip: bool = False
    extra_options_paths: tuple[Path, ...] = ()


def launcher_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def doomrunner_options_paths(dirs: Dirs) -> list[Path]:
    # Windows Doom Runner stores options beside DoomRunner.exe when that
    # directory is writable, which is true for DoomDeck's user-managed install.
    # The XDG mirrors cover Linux Doom Runner builds and older/future storage.
    return [
        dirs.doomrunner / "options.json",
        dirs.xdg_data / "DoomRunner" / "options.json",
        dirs.xdg_config / "DoomRunner" / "options.json",
    ]


def doomrunner_quote_arg(value: str | Path) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def build_doomrunner_iwad_entries(dirs: Dirs) -> list[dict[str, str]]:
    return [entry.as_json_object() for entry in build_doomrunner_iwad_models(dirs)]


def build_doomrunner_iwad_models(dirs: Dirs) -> list[DoomRunnerIWAD]:
    entries: list[DoomRunnerIWAD] = []
    for iwad_name, display_name in DOOMRUNNER_IWAD_DISPLAY_NAMES.items():
        iwad_path = dirs.iwads / iwad_dest_name(iwad_name)
        if iwad_path.exists():
            entries.append(DoomRunnerIWAD(name=display_name, path=proton_windows_path(iwad_path)))
    return entries


def choose_doomrunner_default_iwad(iwad_entries: list[dict[str, str]], dirs: Dirs) -> str:
    preferred = dirs.iwads / "DOOM2.WAD"
    for entry in iwad_entries:
        if entry["path"] == proton_windows_path(preferred):
            return entry["path"]
    return iwad_entries[0]["path"] if iwad_entries else ""


def _preset_name(preset: PresetInput) -> str:
    if isinstance(preset, Preset):
        return preset.name
    return str(preset["name"])


def _preset_path(preset: PresetInput, key: str) -> Path:
    if isinstance(preset, Preset):
        return getattr(preset, key)
    return Path(str(preset[key]))


def _preset_files(preset: PresetInput) -> tuple[Path, ...]:
    if isinstance(preset, Preset):
        return preset.files
    files = preset.get("files", [])
    if not isinstance(files, list):
        return ()
    return tuple(Path(str(path)) for path in files)


def _manifest_presets(manifest: ManifestInput) -> tuple[PresetInput, ...]:
    if isinstance(manifest, PresetManifest):
        return manifest.presets
    presets = manifest.get("presets", [])
    if not isinstance(presets, list):
        return ()
    return tuple(cast(Mapping[str, object], preset) for preset in presets if isinstance(preset, Mapping))


def _preset_mod_files_exist(preset: PresetInput) -> bool:
    return all(path.exists() for path in _preset_files(preset))


def _manifest_content_groups(manifest: ManifestInput) -> object:
    if isinstance(manifest, PresetManifest):
        return manifest.content_groups or {}
    return manifest.get("content_groups", {})


def build_doomrunner_preset(dirs: Dirs, preset: PresetInput) -> dict[str, Any]:
    return build_doomrunner_preset_model(dirs, preset).as_json_object()


def build_doomrunner_preset_model(dirs: Dirs, preset: PresetInput) -> DoomRunnerPreset:
    name = _preset_name(preset)
    slug = launcher_slug(name).lower()
    config = _preset_path(preset, "config")
    autoexec = _preset_path(preset, "autoexec")
    save_dir = dirs.saves / slug
    screenshot_dir = dirs.screenshots / slug
    mods = tuple(DoomRunnerMod(path=proton_windows_path(path)) for path in _preset_files(preset))
    additional_args = f"-noautoload -config {doomrunner_quote_arg(proton_windows_path(config))} +exec {doomrunner_quote_arg(proton_windows_path(autoexec))}"
    return DoomRunnerPreset(
        name=name,
        selected_engine=DOOMRUNNER_ENGINE_ID,
        selected_iwad=proton_windows_path(_preset_path(preset, "iwad")),
        mods=mods,
        alternative_paths=DoomRunnerPresetPaths(
            config_dir=proton_windows_path(config.parent),
            save_dir=proton_windows_path(save_dir),
            screenshot_dir=proton_windows_path(screenshot_dir),
        ),
        additional_args=additional_args,
    )


def choose_doomrunner_selected_preset(presets: list[dict[str, Any]]) -> str:
    preferred_names = [
        "Project Brutality",
        "Brutal Doom",
        "UZDoom",
        "Vanilla Doom",
    ]
    names = {str(preset.get("name", "")) for preset in presets}
    for name in preferred_names:
        if name in names:
            return name
    return str(presets[0]["name"]) if presets else ""


def build_doomrunner_options(dirs: Dirs, manifest: ManifestInput) -> dict[str, Any]:
    return build_doomrunner_options_model(dirs, manifest).as_json_object()


def build_doomrunner_options_model(dirs: Dirs, manifest: ManifestInput) -> DoomRunnerOptions:
    iwad_models = build_doomrunner_iwad_models(dirs)
    iwad_entries = [entry.as_json_object() for entry in iwad_models]
    presets = tuple(
        build_doomrunner_preset_model(dirs, preset)
        for preset in _manifest_presets(manifest)
        if _preset_mod_files_exist(preset)
    )
    preset_entries = [preset.as_json_object() for preset in presets]
    content_groups = _manifest_content_groups(manifest)
    if not isinstance(content_groups, Mapping):
        content_groups = {}
    return DoomRunnerOptions(
        version=DOOMRUNNER_OPTIONS_VERSION,
        engine=DoomRunnerEngine(
            id=DOOMRUNNER_ENGINE_ID,
            name=DOOMRUNNER_ENGINE_NAME,
            path=proton_windows_path(dirs.uzdoom / "uzdoom.exe"),
            config_dir=proton_windows_path(dirs.uzdoom_config),
            data_dir=proton_windows_path(dirs.root),
            family="ZDoom",
        ),
        iwad_directory=proton_windows_path(dirs.iwads),
        default_iwad=choose_doomrunner_default_iwad(iwad_entries, dirs),
        iwads=tuple(iwad_models),
        maps_directory=proton_windows_path(dirs.pwads),
        mods_last_used_dir=proton_windows_path(dirs.mods),
        presets=presets,
        selected_preset=choose_doomrunner_selected_preset(preset_entries),
        content_groups=cast(Mapping[str, object], content_groups),
        screen_width=STEAM_DECK_WIDTH,
        screen_height=STEAM_DECK_HEIGHT,
    )


def write_doomrunner_live_config(
    dirs: Dirs,
    manifest: ManifestInput,
    settings: DoomRunnerLiveConfigSettings,
    logger: logging.Logger,
    *,
    process_detector: ProcessDetector = is_process_running,
) -> None:
    if settings.skip:
        logger.info("Skipping Doom Runner generated options.json copies")
        return
    if process_detector(["DoomRunner.exe", "DoomRunner "]):
        raise DoomDeckError("Doom Runner appears to be running. Close it before rewriting options.json.")

    options = build_doomrunner_options(dirs, manifest)
    content = json.dumps(options, indent=4) + "\n"
    for preset in _manifest_presets(manifest):
        slug = launcher_slug(_preset_name(preset)).lower()
        if slug:
            _ensure_dir(dirs.saves / slug, settings.dry_run, logger)
            _ensure_dir(dirs.screenshots / slug, settings.dry_run, logger)

    for options_path in [*doomrunner_options_paths(dirs), *settings.extra_options_paths]:
        if options_path.exists():
            try:
                current = options_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                current = ""
            if current == content:
                logger.info("Doom Runner generated options already current: %s", options_path)
                continue
            label = f"doomrunner-options-{options_path.parent.parent.name}.json"
            backup_path(options_path, dirs.backups, settings.dry_run, logger, label=label)
        atomic_write_text(options_path, content, settings.dry_run, logger)


def _ensure_dir(path: Path, dry_run: bool, logger: logging.Logger) -> None:
    if path.exists():
        return
    logger.info("Create directory: %s", path)
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)
