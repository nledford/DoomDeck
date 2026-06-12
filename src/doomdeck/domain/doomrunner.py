"""Domain contract for generated Doom Runner options."""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping

from doomdeck.domain.models import DoomDeckError


def _required_text(value: object, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise DoomDeckError(f"{label} must not be empty")
    return text


@dataclasses.dataclass(frozen=True)
class DoomRunnerEngine:
    id: str
    name: str
    path: str
    config_dir: str
    data_dir: str
    family: str

    def __post_init__(self) -> None:
        for field_name, label in [
            ("id", "Doom Runner engine id"),
            ("name", "Doom Runner engine name"),
            ("path", "Doom Runner engine path"),
            ("config_dir", "Doom Runner engine config directory"),
            ("data_dir", "Doom Runner engine data directory"),
            ("family", "Doom Runner engine family"),
        ]:
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), label))

    def as_json_object(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "config_dir": self.config_dir,
            "data_dir": self.data_dir,
            "family": self.family,
        }


@dataclasses.dataclass(frozen=True)
class DoomRunnerIWAD:
    name: str
    path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "Doom Runner IWAD name"))
        object.__setattr__(self, "path", _required_text(self.path, "Doom Runner IWAD path"))

    def as_json_object(self) -> dict[str, str]:
        return {"name": self.name, "path": self.path}


@dataclasses.dataclass(frozen=True)
class DoomRunnerMod:
    path: str
    checked: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _required_text(self.path, "Doom Runner mod path"))

    def as_json_object(self) -> dict[str, object]:
        return {"path": self.path, "checked": self.checked}


@dataclasses.dataclass(frozen=True)
class DoomRunnerPresetPaths:
    config_dir: str
    save_dir: str
    screenshot_dir: str
    demo_dir: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_dir", _required_text(self.config_dir, "Doom Runner preset config directory"))
        object.__setattr__(self, "save_dir", _required_text(self.save_dir, "Doom Runner preset save directory"))
        object.__setattr__(self, "screenshot_dir", _required_text(self.screenshot_dir, "Doom Runner preset screenshot directory"))
        object.__setattr__(self, "demo_dir", str(self.demo_dir))

    def as_json_object(self) -> dict[str, str]:
        return {
            "config_dir": self.config_dir,
            "save_dir": self.save_dir,
            "demo_dir": self.demo_dir,
            "screenshot_dir": self.screenshot_dir,
        }


@dataclasses.dataclass(frozen=True)
class DoomRunnerPreset:
    name: str
    selected_engine: str
    selected_iwad: str
    mods: tuple[DoomRunnerMod, ...]
    alternative_paths: DoomRunnerPresetPaths
    additional_args: str
    selected_config: str = ""
    selected_mappacks: tuple[str, ...] = ()
    load_maps_after_mods: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "Doom Runner preset name"))
        object.__setattr__(self, "selected_engine", _required_text(self.selected_engine, "Doom Runner preset engine"))
        object.__setattr__(self, "selected_iwad", _required_text(self.selected_iwad, "Doom Runner preset IWAD"))
        object.__setattr__(self, "mods", tuple(self.mods))
        object.__setattr__(self, "additional_args", str(self.additional_args))
        object.__setattr__(self, "selected_config", str(self.selected_config))
        object.__setattr__(self, "selected_mappacks", tuple(str(path) for path in self.selected_mappacks))

    def as_json_object(self) -> dict[str, object]:
        return {
            "name": self.name,
            "selected_engine": self.selected_engine,
            "selected_config": self.selected_config,
            "selected_IWAD": self.selected_iwad,
            "selected_mappacks": list(self.selected_mappacks),
            "mods": [mod.as_json_object() for mod in self.mods],
            "load_maps_after_mods": self.load_maps_after_mods,
            "alternative_paths": self.alternative_paths.as_json_object(),
            "additional_args": self.additional_args,
            "env_vars": {},
            "compatibility_options": {
                "compat_mode": -1,
                "compatflags1": 0,
                "compatflags2": 0,
            },
        }


@dataclasses.dataclass(frozen=True)
class DoomRunnerOptions:
    version: str
    engine: DoomRunnerEngine
    iwad_directory: str
    default_iwad: str
    iwads: tuple[DoomRunnerIWAD, ...]
    maps_directory: str
    mods_last_used_dir: str
    presets: tuple[DoomRunnerPreset, ...]
    selected_preset: str
    screen_width: int
    screen_height: int
    content_groups: Mapping[str, object] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _required_text(self.version, "Doom Runner options version"))
        object.__setattr__(self, "iwad_directory", _required_text(self.iwad_directory, "Doom Runner IWAD directory"))
        object.__setattr__(self, "maps_directory", _required_text(self.maps_directory, "Doom Runner maps directory"))
        object.__setattr__(self, "mods_last_used_dir", _required_text(self.mods_last_used_dir, "Doom Runner mods directory"))
        object.__setattr__(self, "default_iwad", str(self.default_iwad))
        object.__setattr__(self, "iwads", tuple(self.iwads))
        object.__setattr__(self, "presets", tuple(self.presets))
        object.__setattr__(self, "selected_preset", str(self.selected_preset))
        if self.selected_preset and self.selected_preset not in {preset.name for preset in self.presets}:
            raise DoomDeckError(f"Selected Doom Runner preset is not generated: {self.selected_preset}")
        object.__setattr__(self, "content_groups", dict(self.content_groups))

    def as_json_object(self) -> dict[str, object]:
        return {
            "version": self.version,
            "engines": {
                "default_engine": self.engine.id,
                "engine_list": [self.engine.as_json_object()],
            },
            "IWADs": {
                "auto_update": False,
                "directory": self.iwad_directory,
                "search_subdirs": False,
                "default_iwad": self.default_iwad,
                "IWAD_list": [iwad.as_json_object() for iwad in self.iwads],
            },
            "maps": {
                "directory": self.maps_directory,
                "sort_column": 0,
                "sort_order": 0,
                "show_icons": False,
            },
            "mods": {
                "last_used_dir": self.mods_last_used_dir,
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
                "resolution_x": self.screen_width,
                "resolution_y": self.screen_height,
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
            "presets": [preset.as_json_object() for preset in self.presets],
            "selected_preset": self.selected_preset,
            "content_groups": dict(self.content_groups),
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
