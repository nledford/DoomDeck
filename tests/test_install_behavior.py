from __future__ import annotations

from doomdeck.application.install import build_install_actions
from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import build_dirs


def test_install_actions_include_optional_moddb_and_steam_shortcut_steps(tmp_path) -> None:
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
        moddb_wad_urls=["https://www.moddb.com/games/doom/addons/example"],
        skip_steam_shortcut=False,
    )

    assert f"Create/update managed layout under {dirs.root}" in actions
    assert "Download requested ModDB WAD archives into the PWAD map directory" in actions
    assert f"Add/update Steam non-Steam shortcut for Doom Runner at {steam.shortcuts_vdf}" in actions


def test_install_actions_omit_steam_shortcut_when_skipped(tmp_path) -> None:
    actions = build_install_actions(
        dirs=build_dirs(tmp_path / "Doom"),
        steam=SteamInfo(None, None, None, [], None),
        appid="2280",
        steamos_msg="Not SteamOS",
        moddb_wad_urls=[],
        skip_steam_shortcut=True,
    )

    assert all("Steam non-Steam shortcut" not in action for action in actions)
    assert "Download requested ModDB WAD archives into the PWAD map directory" not in actions
