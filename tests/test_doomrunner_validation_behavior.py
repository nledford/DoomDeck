from __future__ import annotations

from doomdeck.application.doomrunner import DOOMRUNNER_ENGINE_ID
from doomdeck.application.doomrunner_validation import inspect_doomrunner_options
from doomdeck.application.proton import proton_windows_path
from doomdeck.domain.deck import STEAM_DECK_HEIGHT, STEAM_DECK_WIDTH


def test_doomrunner_options_inspection_resolves_launchable_presets(tmp_path) -> None:
    engine = tmp_path / "uzdoom.exe"
    iwad = tmp_path / "DOOM2.WAD"
    config = tmp_path / "uzdoom.ini"
    autoexec = tmp_path / "autoexec.cfg"
    mod = tmp_path / "brutal-doom.pk3"
    for path in [engine, iwad, config, autoexec, mod]:
        path.write_text("", encoding="utf-8")

    inspection = inspect_doomrunner_options(
        {
            "engines": {
                "engine_list": [
                    {"id": DOOMRUNNER_ENGINE_ID, "path": proton_windows_path(engine)},
                ],
            },
            "IWADs": {
                "IWAD_list": [
                    {"path": proton_windows_path(iwad)},
                ],
            },
            "presets": [
                {
                    "name": "Brutal Doom",
                    "selected_engine": DOOMRUNNER_ENGINE_ID,
                    "selected_IWAD": proton_windows_path(iwad),
                    "mods": [{"path": proton_windows_path(mod), "checked": True}],
                    "additional_args": f'-config "{proton_windows_path(config)}" +exec "{proton_windows_path(autoexec)}"',
                },
            ],
            "video_options": {
                "resolution_x": STEAM_DECK_WIDTH,
                "resolution_y": STEAM_DECK_HEIGHT,
            },
        }
    )

    assert inspection.engine_ok
    assert inspection.iwad_ok
    assert inspection.launchable_preset_ok
    assert inspection.resolved_preset_names == ("Brutal Doom",)
    assert inspection.steam_deck_resolution_ok


def test_doomrunner_options_inspection_rejects_missing_checked_mod(tmp_path) -> None:
    engine = tmp_path / "uzdoom.exe"
    iwad = tmp_path / "DOOM2.WAD"
    config = tmp_path / "uzdoom.ini"
    autoexec = tmp_path / "autoexec.cfg"
    for path in [engine, iwad, config, autoexec]:
        path.write_text("", encoding="utf-8")

    inspection = inspect_doomrunner_options(
        {
            "engines": {"engine_list": [{"id": DOOMRUNNER_ENGINE_ID, "path": proton_windows_path(engine)}]},
            "IWADs": {"IWAD_list": [{"path": proton_windows_path(iwad)}]},
            "presets": [
                {
                    "name": "Brutal Doom",
                    "selected_engine": DOOMRUNNER_ENGINE_ID,
                    "selected_IWAD": proton_windows_path(iwad),
                    "mods": [{"path": proton_windows_path(tmp_path / "missing.pk3"), "checked": True}],
                    "additional_args": f'-config "{proton_windows_path(config)}" +exec "{proton_windows_path(autoexec)}"',
                },
            ],
            "video_options": {"resolution_x": STEAM_DECK_WIDTH, "resolution_y": STEAM_DECK_HEIGHT},
        }
    )

    assert inspection.launchable_preset_ok
    assert inspection.resolved_preset_names == ()


def test_doomrunner_options_inspection_handles_malformed_sections() -> None:
    inspection = inspect_doomrunner_options(
        {
            "engines": {"engine_list": "not-a-list"},
            "IWADs": {"IWAD_list": "not-a-list"},
            "presets": "not-a-list",
            "video_options": {},
        }
    )

    assert not inspection.engine_ok
    assert not inspection.iwad_ok
    assert not inspection.launchable_preset_ok
    assert inspection.resolved_preset_names == ()
    assert not inspection.steam_deck_resolution_ok
