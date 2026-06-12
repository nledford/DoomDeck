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
    entries: list[dict[str, str]] = []
    for iwad_name, display_name in DOOMRUNNER_IWAD_DISPLAY_NAMES.items():
        iwad_path = dirs.iwads / iwad_dest_name(iwad_name)
        if iwad_path.exists():
            entries.append({"name": display_name, "path": proton_windows_path(iwad_path)})
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


def _manifest_content_groups(manifest: ManifestInput) -> object:
    if isinstance(manifest, PresetManifest):
        return manifest.content_groups or {}
    return manifest.get("content_groups", {})


def build_doomrunner_preset(dirs: Dirs, preset: PresetInput) -> dict[str, Any]:
    name = _preset_name(preset)
    slug = launcher_slug(name).lower()
    config = _preset_path(preset, "config")
    autoexec = _preset_path(preset, "autoexec")
    save_dir = dirs.saves / slug
    screenshot_dir = dirs.screenshots / slug
    mods = [{"path": proton_windows_path(path), "checked": True} for path in _preset_files(preset)]
    additional_args = f"-noautoload -config {doomrunner_quote_arg(proton_windows_path(config))} +exec {doomrunner_quote_arg(proton_windows_path(autoexec))}"
    return {
        "name": name,
        "selected_engine": DOOMRUNNER_ENGINE_ID,
        "selected_config": "",
        "selected_IWAD": proton_windows_path(_preset_path(preset, "iwad")),
        "selected_mappacks": [],
        "mods": mods,
        "load_maps_after_mods": False,
        "alternative_paths": {
            "config_dir": proton_windows_path(config.parent),
            "save_dir": proton_windows_path(save_dir),
            "demo_dir": "",
            "screenshot_dir": proton_windows_path(screenshot_dir),
        },
        "additional_args": additional_args,
        "env_vars": {},
        "compatibility_options": {
            "compat_mode": -1,
            "compatflags1": 0,
            "compatflags2": 0,
        },
    }


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
    iwad_entries = build_doomrunner_iwad_entries(dirs)
    presets = [build_doomrunner_preset(dirs, preset) for preset in _manifest_presets(manifest)]
    return {
        "version": DOOMRUNNER_OPTIONS_VERSION,
        "engines": {
            "default_engine": DOOMRUNNER_ENGINE_ID,
            "engine_list": [
                {
                    "id": DOOMRUNNER_ENGINE_ID,
                    "name": DOOMRUNNER_ENGINE_NAME,
                    "path": proton_windows_path(dirs.uzdoom / "uzdoom.exe"),
                    "config_dir": proton_windows_path(dirs.uzdoom_config),
                    "data_dir": proton_windows_path(dirs.root),
                    "family": "ZDoom",
                }
            ],
        },
        "IWADs": {
            "auto_update": False,
            "directory": proton_windows_path(dirs.iwads),
            "search_subdirs": False,
            "default_iwad": choose_doomrunner_default_iwad(iwad_entries, dirs),
            "IWAD_list": iwad_entries,
        },
        "maps": {
            "directory": proton_windows_path(dirs.pwads),
            "sort_column": 0,
            "sort_order": 0,
            "show_icons": False,
        },
        "mods": {
            "last_used_dir": proton_windows_path(dirs.mods),
            "show_icons": True,
        },
        "launch_options": {
            "launch_mode": 0,
            "map_name": "",
            "save_file": "",
            "map_name_demo": "",
            "demo_file_record": "",
            "demo_file_replay": "",
            "demo_file_resume_from": "",
            "demo_file_resume_to": "",
        },
        "multiplayer_options": {
            "is_multiplayer": False,
            "mult_role": 0,
            "host_name": "",
            "port": 5029,
            "net_mode": 0,
            "game_mode": 0,
            "player_count": 2,
            "team_damage": 0,
            "time_limit": 0,
            "frag_limit": 0,
            "player_name": "",
            "player_color": None,
        },
        "gameplay_options": {
            "skill_idx": 1,
            "skill_num": 1,
            "no_monsters": False,
            "fast_monsters": False,
            "monsters_respawn": False,
            "pistol_start": False,
            "allow_cheats": False,
            "dmflags1": 0,
            "dmflags2": 0,
            "dmflags3": 0,
        },
        "video_options": {
            "monitor_idx": 0,
            "resolution_x": STEAM_DECK_WIDTH,
            "resolution_y": STEAM_DECK_HEIGHT,
            "show_fps": False,
        },
        "audio_options": {
            "no_sound": False,
            "no_sfx": False,
            "no_music": False,
        },
        "global_options": {
            "use_preset_name_as_config_dir": False,
            "use_preset_name_as_save_dir": False,
            "use_preset_name_as_demo_dir": False,
            "use_preset_name_as_screenshot_dir": False,
            "additional_args": "",
            "cmd_prefix": "",
            "env_vars": {},
        },
        "presets": presets,
        "selected_preset": choose_doomrunner_selected_preset(presets),
        "content_groups": _manifest_content_groups(manifest),
        "use_absolute_paths": True,
        "show_engine_output": True,
        "close_on_launch": False,
        "close_output_on_success": False,
        "check_for_updates": False,
        "ask_for_sandbox_permissions": False,
        "wrap_lines_in_txt_viewer": False,
        "options_storage": {
            "launch_opts": 1,
            "gameplay_opts": 1,
            "compat_opts": 2,
            "video_opts": 1,
            "audio_opts": 1,
        },
        "preset_search": {
            "panel_expanded": False,
            "case_sensitive": False,
            "use_regex": False,
        },
        "hide_map_label": False,
        "geometry": {
            "x": -2147483648,
            "y": -2147483648,
            "width": 0,
            "height": 0,
        },
        "app_style": None,
        "color_scheme": "system",
    }


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
