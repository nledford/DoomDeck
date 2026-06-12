"""Inspect generated Doom Runner options for launchability."""
from __future__ import annotations

import dataclasses
import shlex
from collections.abc import Mapping
from typing import Any

from doomdeck.application.doomrunner import DOOMRUNNER_ENGINE_ID
from doomdeck.application.proton import proton_linux_path
from doomdeck.domain.deck import STEAM_DECK_HEIGHT, STEAM_DECK_WIDTH


@dataclasses.dataclass(frozen=True)
class DoomRunnerOptionsInspection:
    engine_ok: bool
    iwad_ok: bool
    launchable_preset_ok: bool
    resolved_preset_names: tuple[str, ...]
    steam_deck_resolution_ok: bool


def inspect_doomrunner_options(live_options: Mapping[str, Any]) -> DoomRunnerOptionsInspection:
    engine_list = _section_list(live_options, "engines", "engine_list")
    engines = {
        str(engine.get("id")): engine
        for engine in engine_list
        if isinstance(engine, dict) and bool(engine.get("id")) and proton_linux_path(engine.get("path", "")).exists()
    }
    engine_ok = DOOMRUNNER_ENGINE_ID in engines

    iwad_list = _section_list(live_options, "IWADs", "IWAD_list")
    iwad_ok = any(isinstance(iwad, dict) and bool(iwad.get("path")) and proton_linux_path(iwad.get("path", "")).exists() for iwad in iwad_list)

    live_presets = live_options.get("presets", [])
    if not isinstance(live_presets, list):
        live_presets = []
    launchable_preset_ok = any(
        isinstance(preset, dict) and preset.get("selected_engine") == DOOMRUNNER_ENGINE_ID and preset.get("selected_IWAD")
        for preset in live_presets
    )
    resolved_preset_names = tuple(_resolved_generated_preset_names(live_presets, engines))

    video_options = live_options.get("video_options", {})
    if not isinstance(video_options, dict):
        video_options = {}
    steam_deck_resolution_ok = (
        video_options.get("resolution_x") == STEAM_DECK_WIDTH
        and video_options.get("resolution_y") == STEAM_DECK_HEIGHT
    )

    return DoomRunnerOptionsInspection(
        engine_ok=engine_ok,
        iwad_ok=iwad_ok,
        launchable_preset_ok=launchable_preset_ok,
        resolved_preset_names=resolved_preset_names,
        steam_deck_resolution_ok=steam_deck_resolution_ok,
    )


def _section_list(options: Mapping[str, Any], section_name: str, list_name: str) -> list[Any]:
    section = options.get(section_name, {})
    if not isinstance(section, dict):
        return []
    value = section.get(list_name, [])
    return value if isinstance(value, list) else []


def _resolved_generated_preset_names(live_presets: list[Any], engines: Mapping[str, Mapping[str, Any]]) -> list[str]:
    names: list[str] = []
    for preset in live_presets:
        if not isinstance(preset, dict):
            continue
        selected_engine = str(preset.get("selected_engine", ""))
        if selected_engine not in engines:
            continue
        if not proton_linux_path(preset.get("selected_IWAD", "")).exists():
            continue
        mods = preset.get("mods", [])
        if isinstance(mods, list) and any(
            isinstance(mod, dict) and mod.get("checked", True) and not proton_linux_path(mod.get("path", "")).exists()
            for mod in mods
        ):
            continue
        if not _additional_args_paths_exist(str(preset.get("additional_args", ""))):
            continue
        names.append(str(preset.get("name", "")).strip() or "<unnamed>")
    return names


def _additional_args_paths_exist(additional_args: str) -> bool:
    try:
        tokens = shlex.split(additional_args)
    except ValueError:
        return False
    for option in ["-config", "+exec"]:
        if option not in tokens:
            return False
        index = tokens.index(option) + 1
        if index >= len(tokens) or not proton_linux_path(tokens[index]).exists():
            return False
    return True
