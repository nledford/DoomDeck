from __future__ import annotations

import argparse
import json
import logging
import shlex
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

import doomdeck.cli as cli
from doomdeck.application.doomrunner import build_doomrunner_options, doomrunner_options_paths
from doomdeck.application.launchers import write_launchers_and_manifest
from doomdeck.application.moddb_wads import install_moddb_wad_archive
from doomdeck.application.proton import proton_linux_path
from doomdeck.application.steam_input import steam_input_profile_path
from doomdeck.application.uzdoom import write_uzdoom_configs
from doomdeck.domain.paths import all_managed_dirs, build_dirs
from doomdeck.infrastructure.binary_vdf import BKV_OBJECT, BinaryVDF
from doomdeck.infrastructure.steam_shortcuts import (
    empty_shortcuts_root,
    get_bkv_str,
    load_shortcuts,
    make_shortcut_entry,
    shortcut_entries,
)

FEATURES_DIR = Path(__file__).parents[2] / "features"
LOGGER = logging.getLogger("test")

scenarios(str(FEATURES_DIR / "install_doomrunner_steam_flow.feature"))
scenarios(str(FEATURES_DIR / "install_optional_mod_presets.feature"))
scenarios(str(FEATURES_DIR / "install_moddb_wads.feature"))


@pytest.fixture
def bdd_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return {
        "root": tmp_path / "Doom",
        "steam_root": tmp_path / "Steam",
        "monkeypatch": monkeypatch,
    }


def _dirs(context: dict[str, Any]):
    return build_dirs(context["root"])


def _shortcuts_path(context: dict[str, Any]) -> Path:
    return context["steam_root"] / "userdata" / "123" / "config" / "shortcuts.vdf"


def _prepare_fake_steam_install(context: dict[str, Any]) -> None:
    steam_root = context["steam_root"]
    app_dir = steam_root / "steamapps" / "common" / "DOOM + DOOM II"
    (app_dir / "rerelease" / "base").mkdir(parents=True, exist_ok=True)
    (app_dir / "rerelease" / "base" / "doom2.wad").write_bytes(b"iwad")
    (steam_root / "steamapps").mkdir(parents=True, exist_ok=True)
    (steam_root / "steamapps" / "appmanifest_2280.acf").write_text(
        '"AppState"\n{\n    "appid" "2280"\n    "installdir" "DOOM + DOOM II"\n}\n',
        encoding="utf-8",
    )
    (_shortcuts_path(context).parent).mkdir(parents=True, exist_ok=True)


def _prepare_installable_artifacts(context: dict[str, Any]) -> None:
    dirs = _dirs(context)
    (dirs.doomrunner).mkdir(parents=True, exist_ok=True)
    (dirs.uzdoom).mkdir(parents=True, exist_ok=True)
    (dirs.brutal).mkdir(parents=True, exist_ok=True)
    (dirs.doomrunner / "DoomRunner.exe").write_bytes(b"doomrunner")
    (dirs.uzdoom / "uzdoom.exe").write_bytes(b"uzdoom")
    (dirs.brutal / "brutal-doom.pk3").write_bytes(b"brutal")


def _run_install(context: dict[str, Any]) -> None:
    context["monkeypatch"].setattr(cli, "detect_steamos", lambda: (True, "SteamOS test fixture"))
    result = cli.main(
        [
            "install",
            "--root",
            str(context["root"]),
            "--steam-root",
            str(context["steam_root"]),
            "--steam-user-id",
            "123",
            "--skip-downloads",
            "--skip-project-brutality",
            "--allow-steam-running",
        ]
    )
    context["install_result"] = result
    assert result == 0


def _shortcut_names(context: dict[str, Any]) -> list[str]:
    shortcuts = shortcut_entries(load_shortcuts(_shortcuts_path(context)))
    return [
        get_bkv_str(value.value, "appname", "AppName")
        for value in shortcuts.values()
        if value.type_code == BKV_OBJECT
    ]


def _doomrunner_options(context: dict[str, Any]) -> dict[str, Any]:
    path = doomrunner_options_paths(_dirs(context))[0]
    return json.loads(path.read_text(encoding="utf-8"))


@given("a Steam user has DOOM + DOOM II installed")
def steam_user_has_doom_installed(bdd_context: dict[str, Any]) -> None:
    _prepare_fake_steam_install(bdd_context)


@given("DoomDeck can install DoomRunner, UZDoom, an IWAD, and Brutal Doom")
def doomdeck_can_install_tools_and_brutal_doom(bdd_context: dict[str, Any]) -> None:
    _prepare_installable_artifacts(bdd_context)


@given("DoomDeck has already created a Doom Runner shortcut")
def doomdeck_has_existing_doomrunner_shortcut(bdd_context: dict[str, Any]) -> None:
    _prepare_fake_steam_install(bdd_context)
    _prepare_installable_artifacts(bdd_context)
    shortcuts_path = _shortcuts_path(bdd_context)
    root = empty_shortcuts_root()
    shortcuts = shortcut_entries(root)
    shortcuts["0"] = make_shortcut_entry(
        "Doom Runner",
        Path("/old/DoomRunner.exe"),
        Path("/old"),
        tags=["Doom"],
    )
    shortcuts_path.write_bytes(BinaryVDF.dumps(root))


@given("an older DoomDeck preset shortcut also exists")
def older_preset_shortcut_exists(bdd_context: dict[str, Any]) -> None:
    shortcuts_path = _shortcuts_path(bdd_context)
    root = load_shortcuts(shortcuts_path)
    shortcuts = shortcut_entries(root)
    shortcuts["1"] = make_shortcut_entry(
        "DoomDeck - Brutal Doom",
        _dirs(bdd_context).uzdoom / "uzdoom.exe",
        _dirs(bdd_context).uzdoom,
        tags=["Doom"],
        launch_options="-iwad DOOM2.WAD",
    )
    shortcuts_path.write_bytes(BinaryVDF.dumps(root))


@when("the user runs DoomDeck install")
def user_runs_doomdeck_install(bdd_context: dict[str, Any]) -> None:
    _run_install(bdd_context)


@when("the user runs DoomDeck install again")
def user_runs_doomdeck_install_again(bdd_context: dict[str, Any]) -> None:
    _run_install(bdd_context)


@then("Steam has exactly one Doom Runner shortcut")
@then("Steam still has exactly one Doom Runner shortcut")
def steam_has_one_doomrunner_shortcut(bdd_context: dict[str, Any]) -> None:
    assert _shortcut_names(bdd_context).count("Doom Runner") == 1


@then("Steam has a DoomDeck Steam Input profile for the Doom Runner shortcut")
def steam_has_doomdeck_steam_input_profile(bdd_context: dict[str, Any]) -> None:
    steam = cli.discover_steam(
        argparse.Namespace(steam_root=str(bdd_context["steam_root"]), steam_user_id="123"),
        LOGGER,
    )
    profile_path = steam_input_profile_path(steam)
    assert profile_path is not None
    text = profile_path.read_text(encoding="utf-8")
    assert "DoomDeck Hybrid KB/M" in text
    assert "gyro active" not in text.lower()


@then("no DoomDeck preset shortcuts remain")
def no_doomdeck_preset_shortcuts_remain(bdd_context: dict[str, Any]) -> None:
    assert all(not name.startswith("DoomDeck - ") for name in _shortcut_names(bdd_context))


@then("DoomRunner has a UZDoom engine configured")
def doomrunner_has_uzdoom_engine(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    options = _doomrunner_options(bdd_context)
    engine = next(engine for engine in options["engines"]["engine_list"] if engine["id"] == "doomdeck-uzdoom")
    assert engine["name"] == "UZDoom"
    assert proton_linux_path(engine["path"]) == dirs.uzdoom / "uzdoom.exe"


@then("DoomRunner has a Brutal Doom preset with an existing IWAD and mod file")
def doomrunner_has_brutal_doom_preset(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    options = _doomrunner_options(bdd_context)
    preset = next(preset for preset in options["presets"] if preset["name"] == "Brutal Doom")
    assert proton_linux_path(preset["selected_IWAD"]) == dirs.iwads / "DOOM2.WAD"
    checked_mods = [proton_linux_path(mod["path"]) for mod in preset["mods"] if mod["checked"]]
    assert checked_mods == [dirs.brutal / "brutal-doom.pk3"]


@then("the preset launch paths resolve to existing files")
def preset_launch_paths_resolve(bdd_context: dict[str, Any]) -> None:
    options = _doomrunner_options(bdd_context)
    preset = next(preset for preset in options["presets"] if preset["name"] == "Brutal Doom")
    assert proton_linux_path(preset["selected_IWAD"]).exists()
    assert all(proton_linux_path(mod["path"]).exists() for mod in preset["mods"] if mod["checked"])
    tokens = shlex.split(preset["additional_args"])
    for option in ["-config", "+exec"]:
        assert option in tokens
        assert proton_linux_path(tokens[tokens.index(option) + 1]).exists()


@given("DoomDeck has a usable Doom II IWAD")
def doomdeck_has_doom2_iwad(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    dirs.iwads.mkdir(parents=True, exist_ok=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")


@given("Brutal Doom is not installed")
def brutal_doom_is_not_installed(bdd_context: dict[str, Any]) -> None:
    assert not (_dirs(bdd_context).brutal / "brutal-doom.pk3").exists()


@given("Project Brutality is not installed")
def project_brutality_is_not_installed(bdd_context: dict[str, Any]) -> None:
    assert not (_dirs(bdd_context).project_brutality / "project-brutality.pk3").exists()


@given("Brutal Doom is installed as a managed mod alias")
def brutal_doom_is_installed_as_alias(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    dirs.brutal.mkdir(parents=True, exist_ok=True)
    (dirs.brutal / "brutal-doom.pk3").write_bytes(b"brutal")


@when("DoomDeck generates DoomRunner presets")
def doomdeck_generates_doomrunner_presets(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    for directory in all_managed_dirs(dirs):
        directory.mkdir(parents=True, exist_ok=True)
    write_uzdoom_configs(dirs, dry_run=False, logger=LOGGER)
    brutal_path = dirs.brutal / "brutal-doom.pk3" if (dirs.brutal / "brutal-doom.pk3").exists() else None
    project_path = (
        dirs.project_brutality / "project-brutality.pk3"
        if (dirs.project_brutality / "project-brutality.pk3").exists()
        else None
    )
    manifest = write_launchers_and_manifest(dirs, brutal_path, project_path, dry_run=False, logger=LOGGER)
    bdd_context["manifest"] = manifest
    bdd_context["doomrunner_options"] = build_doomrunner_options(dirs, manifest)


@then("DoomRunner includes Vanilla Doom and UZDoom presets")
def doomrunner_includes_vanilla_and_uzdoom(bdd_context: dict[str, Any]) -> None:
    names = [preset["name"] for preset in bdd_context["doomrunner_options"]["presets"]]
    assert names == ["Vanilla Doom", "UZDoom"]


@then("DoomRunner does not include Brutal Doom or Project Brutality presets")
def doomrunner_omits_missing_mod_presets(bdd_context: dict[str, Any]) -> None:
    names = {preset["name"] for preset in bdd_context["doomrunner_options"]["presets"]}
    assert "Brutal Doom" not in names
    assert "Project Brutality" not in names


@then("DoomRunner includes the Brutal Doom preset")
def doomrunner_includes_brutal_doom(bdd_context: dict[str, Any]) -> None:
    names = {preset["name"] for preset in bdd_context["doomrunner_options"]["presets"]}
    assert "Brutal Doom" in names


@then("the preset references the managed Brutal Doom file")
def preset_references_managed_brutal_doom_file(bdd_context: dict[str, Any]) -> None:
    dirs = _dirs(bdd_context)
    preset = next(preset for preset in bdd_context["doomrunner_options"]["presets"] if preset["name"] == "Brutal Doom")
    checked_mods = [proton_linux_path(mod["path"]) for mod in preset["mods"] if mod["checked"]]
    assert checked_mods == [dirs.brutal / "brutal-doom.pk3"]


@given("the user has an existing DoomDeck managed folder")
def user_has_existing_managed_folder(bdd_context: dict[str, Any]) -> None:
    for directory in all_managed_dirs(_dirs(bdd_context)):
        directory.mkdir(parents=True, exist_ok=True)


@given("a ModDB archive contains a playable WAD and documentation")
def moddb_archive_contains_wad_and_docs(bdd_context: dict[str, Any]) -> None:
    archive_path = bdd_context["root"].parent / "dtwid.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("dtwid/dtwid.wad", b"wad bytes")
        archive.writestr("dtwid/docs/readme.txt", "documentation")
    bdd_context["moddb_archive"] = archive_path


@given("the user only wants to add PWAD content")
def user_only_wants_to_add_pwad_content(bdd_context: dict[str, Any]) -> None:
    bdd_context["discover_steam_called"] = False
    bdd_context["steam_shortcut_called"] = False


@when("the user runs DoomDeck install-wads for that archive")
def user_runs_install_wads_for_archive(bdd_context: dict[str, Any]) -> None:
    archive_path = bdd_context["moddb_archive"]

    def fake_install_moddb_wad_urls(
        _page_urls: list[str],
        _downloads_dir: Path,
        pwads_dir: Path,
        backups_dir: Path,
        dry_run: bool,
        logger: logging.Logger,
        force_download: bool = False,
        user_agent: str = "",
    ) -> list[Path]:
        assert not force_download
        assert user_agent
        return install_moddb_wad_archive(archive_path, pwads_dir, backups_dir, dry_run, logger)

    bdd_context["monkeypatch"].setattr(cli, "install_moddb_wad_urls", fake_install_moddb_wad_urls)
    result = cli.main(["install-wads", "--root", str(bdd_context["root"]), "https://www.moddb.com/games/doom/addons/dtwid"])
    bdd_context["install_wads_result"] = result
    assert result == 0


@when("the user runs DoomDeck install-wads")
def user_runs_install_wads(bdd_context: dict[str, Any]) -> None:
    def fake_discover_steam(*_args: object, **_kwargs: object) -> None:
        bdd_context["discover_steam_called"] = True

    def fake_shortcut_update(*_args: object, **_kwargs: object) -> int:
        bdd_context["steam_shortcut_called"] = True
        return 0

    def fake_install_moddb_wad_urls(*_args: object, **_kwargs: object) -> list[Path]:
        return []

    bdd_context["monkeypatch"].setattr(cli, "discover_steam", fake_discover_steam)
    bdd_context["monkeypatch"].setattr(cli, "add_or_update_doomrunner_shortcut", fake_shortcut_update)
    bdd_context["monkeypatch"].setattr(cli, "install_moddb_wad_urls", fake_install_moddb_wad_urls)
    result = cli.main(["install-wads", "--root", str(bdd_context["root"]), "https://www.moddb.com/games/doom/addons/dtwid"])
    bdd_context["install_wads_result"] = result
    assert result == 0


@then("the playable WAD is installed in the PWAD folder")
def playable_wad_is_installed(bdd_context: dict[str, Any]) -> None:
    assert (_dirs(bdd_context).pwads / "DTWID.WAD").read_bytes() == b"wad bytes"


@then("documentation files are not installed as playable content")
def docs_are_not_installed_as_content(bdd_context: dict[str, Any]) -> None:
    assert not (_dirs(bdd_context).pwads / "README.TXT").exists()


@then("DoomRunner content groups are refreshed")
def doomrunner_content_groups_are_refreshed(bdd_context: dict[str, Any]) -> None:
    content_groups_path = _dirs(bdd_context).doomrunner_config / "content-groups.json"
    content_groups = json.loads(content_groups_path.read_text(encoding="utf-8"))
    assert content_groups["schema"] == "doom-deck-setup/content-groups/v1"
    map_groups = content_groups["content_groups"]["map_packs"]
    items = [item for group in map_groups for item in group["items"]]
    assert any(item["path"].endswith("DTWID.WAD") for item in items)


@then("DoomDeck does not require Steam app discovery")
def doomdeck_does_not_require_steam_discovery(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["discover_steam_called"] is False


@then("DoomDeck does not add or update Steam shortcuts")
def doomdeck_does_not_update_steam_shortcuts(bdd_context: dict[str, Any]) -> None:
    assert bdd_context["steam_shortcut_called"] is False
    assert not _shortcuts_path(bdd_context).exists()
