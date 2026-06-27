from __future__ import annotations

import logging

from doomdeck.application.steam_input import (
    deploy_steam_input_profile,
    managed_steam_input_profile_path,
    steam_input_configset_path,
    steam_input_local_override_path,
    steam_input_profile_path,
    write_managed_steam_input_profile,
)
from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import build_dirs


def test_managed_steam_input_profile_is_written_under_configs(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")

    path = write_managed_steam_input_profile(dirs, dry_run=False, logger=logging.getLogger("test"))

    assert path == managed_steam_input_profile_path(dirs)
    assert path == dirs.steam_input_config / "doomrunner" / "controller_neptune.vdf"
    assert "DoomDeck Hybrid KB/M" in path.read_text(encoding="utf-8")


def test_steam_input_profile_deploys_to_user_config_and_app_override(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    steam = SteamInfo(tmp_path / "Steam", "123", None, [], None)
    appid = 123456789

    written = deploy_steam_input_profile(dirs, steam, appid, dry_run=False, logger=logging.getLogger("test"))

    profile_path = steam_input_profile_path(steam)
    configset_path = steam_input_configset_path(steam)
    override_path = steam_input_local_override_path(steam, appid)
    assert profile_path is not None and profile_path in written and profile_path.exists()
    assert configset_path is not None and configset_path in written and configset_path.exists()
    assert override_path is not None and override_path in written and override_path.exists()
    assert '"doom runner"' in configset_path.read_text(encoding="utf-8")
    assert "autosave" in configset_path.read_text(encoding="utf-8")
    assert f"autosave://{profile_path}" in profile_path.read_text(encoding="utf-8")


def test_existing_non_doomdeck_profile_is_not_silently_clobbered(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    steam = SteamInfo(tmp_path / "Steam", "123", None, [], None)
    existing = steam_input_profile_path(steam)
    assert existing is not None
    existing.parent.mkdir(parents=True)
    existing.write_text('"controller_mappings" { "title" "My Custom Layout" }\n', encoding="utf-8")

    deploy_steam_input_profile(dirs, steam, 123456789, dry_run=False, logger=logging.getLogger("test"))

    assert existing.read_text(encoding="utf-8") == '"controller_mappings" { "title" "My Custom Layout" }\n'
