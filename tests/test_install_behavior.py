from __future__ import annotations

from doomdeck.application.install import build_install_actions, build_install_plan
from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import build_dirs


def test_install_actions_include_optional_steam_shortcut_step(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    steam = SteamInfo(
        steam_root=tmp_path / "Steam",
        user_id="123",
        shortcuts_vdf=tmp_path / "Steam" / "userdata" / "123" / "config" / "shortcuts.vdf",
        library_folders=[tmp_path / "Steam"],
        app_install_dir=tmp_path / "Steam" / "steamapps" / "common" / "DOOM",
    )

    actions = build_install_actions(
        dirs=dirs,
        steam=steam,
        appid="2280",
        steamos_msg="SteamOS detected",
        skip_steam_shortcut=False,
    )

    assert f"Create/update managed layout under {dirs.root}" in actions
    assert f"Add/update the single Steam non-Steam shortcut for Windows Doom Runner at {steam.shortcuts_vdf}" in actions


def test_install_plan_preserves_rendered_action_contract(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    steam = SteamInfo(None, None, None, [], None)

    plan = build_install_plan(
        dirs=dirs,
        steam=steam,
        appid="2280",
        steamos_msg="SteamOS detected",
        skip_steam_shortcut=True,
    )

    assert [action.id for action in plan.actions] == [
        "managed-layout",
        "steamos-check",
        "steam-root-detection",
        "steam-app-detection",
        "doomrunner-windows",
        "uzdoom-windows",
        "steam-wads",
        "uzdoom-launchers",
        "steam-input-profile",
        "brutal-doom",
        "project-brutality",
        "doomrunner-config",
    ]
    assert plan.render_actions() == build_install_actions(
        dirs=dirs,
        steam=steam,
        appid="2280",
        steamos_msg="SteamOS detected",
        skip_steam_shortcut=True,
    )


def test_install_actions_omit_steam_shortcut_when_skipped(tmp_path) -> None:
    actions = build_install_actions(
        dirs=build_dirs(tmp_path / "Doom"),
        steam=SteamInfo(None, None, None, [], None),
        appid="2280",
        steamos_msg="Not SteamOS",
        skip_steam_shortcut=True,
    )

    assert all("Steam non-Steam shortcut" not in action for action in actions)
