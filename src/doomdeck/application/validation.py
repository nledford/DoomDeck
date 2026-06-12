"""Installation validation rules and reporting helpers."""
from __future__ import annotations

import dataclasses
import json
import shlex
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, cast

from doomdeck.application.doomrunner import DOOMRUNNER_ENGINE_ID, doomrunner_options_paths
from doomdeck.application.proton import proton_linux_path
from doomdeck.application.steam import doomrunner_proton_options_path
from doomdeck.domain.deck import STEAM_DECK_HEIGHT, STEAM_DECK_WIDTH
from doomdeck.domain.models import Dirs, DoomDeckError, SteamInfo, ValidationItem, ValidationLevel
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD
from doomdeck.domain.presets import PresetManifest
from doomdeck.domain.wads import IWAD_CANONICAL_NAMES
from doomdeck.infrastructure.archives import zip_contains_markers
from doomdeck.infrastructure.binary_vdf import BKV_OBJECT
from doomdeck.infrastructure.steam_compat import compat_mapping_key, load_text_vdf
from doomdeck.infrastructure.steam_shortcuts import get_bkv_str, load_shortcuts, shortcut_entries

SteamOSDetector = Callable[[], tuple[bool, str]]
ShellSyntaxChecker = Callable[[Path], bool]

APPID_DOOM_PLUS_DOOM_II = "2280"
BRUTAL_DOOM_ALIAS = BRUTAL_DOOM_MOD.alias
PROJECT_BRUTALITY_ALIAS = PROJECT_BRUTALITY_MOD.alias


def add_validation_item(items: list[ValidationItem], level: ValidationLevel | str, message: str) -> None:
    items.append(ValidationItem(ValidationLevel.from_value(level), message))


def validation_has_failures(items: Iterable[ValidationItem]) -> bool:
    return any(item.level == ValidationLevel.FAIL for item in items)


def format_validation_report(items: Iterable[ValidationItem]) -> str:
    lines = ["", "Validation report", "================="]
    lines.extend(f"[{item.level.value}] {item.message}" for item in items)
    lines.append("")
    return "\n".join(lines)


def script_has_execve_shebang(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


@dataclasses.dataclass(frozen=True)
class InstallationValidator:
    """Validate a managed DoomDeck installation without depending on the CLI."""

    steamos_detector: SteamOSDetector
    shell_syntax_checker: ShellSyntaxChecker
    steam_appid: str = APPID_DOOM_PLUS_DOOM_II

    def validate(self, dirs: Dirs, steam: SteamInfo) -> list[ValidationItem]:
        items: list[ValidationItem] = []
        self._validate_environment(items, dirs)
        self._validate_tool_executables(items, dirs)
        self._validate_wads(items, dirs)
        self._validate_managed_mods(items, dirs)
        manifest = self._validate_preset_manifest(items, dirs)
        if manifest is not None:
            self._validate_preset_references(items, manifest, dirs)
        self._validate_uzdoom_configs(items, dirs)
        self._validate_doomrunner_live_options(items, dirs)
        self._validate_shell_scripts(items, dirs)
        self._validate_steam(items, dirs, steam)
        self._validate_backups(items, dirs)
        return items

    def _validate_environment(self, items: list[ValidationItem], dirs: Dirs) -> None:
        steamos_ok, steamos_msg = self.steamos_detector()
        add_validation_item(items, "PASS" if steamos_ok else "WARN", steamos_msg)

        for path in [dirs.root, dirs.iwads, dirs.launchers, dirs.configs, dirs.docs]:
            add_validation_item(items, "PASS" if path.exists() else "FAIL", f"Required path exists: {path}")

    def _validate_tool_executables(self, items: list[ValidationItem], dirs: Dirs) -> None:
        doomrunner_app = dirs.doomrunner / "DoomRunner.exe"
        uzdoom_app = dirs.uzdoom / "uzdoom.exe"
        for label, path in [
            ("Windows Doom Runner executable", doomrunner_app),
            ("Windows UZDoom executable", uzdoom_app),
        ]:
            exists = path.exists()
            add_validation_item(items, "PASS" if exists else "FAIL", f"{label} exists: {path}")

    def _validate_wads(self, items: list[ValidationItem], dirs: Dirs) -> None:
        copied_iwads = sorted(
            p.name
            for pattern in ["*.WAD", "*.wad"]
            for p in dirs.iwads.glob(pattern)
            if p.name.lower() in IWAD_CANONICAL_NAMES
        )
        if copied_iwads:
            add_validation_item(items, "PASS", f"IWADs present: {', '.join(copied_iwads)}")
        else:
            add_validation_item(items, "FAIL", f"No IWADs found in {dirs.iwads}")
        for required in ["DOOM.WAD", "DOOM2.WAD"]:
            add_validation_item(items, "PASS" if (dirs.iwads / required).exists() else "WARN", f"Expected common IWAD: {dirs.iwads / required}")

        addon_wads = sorted(p.name for pattern in ["*.WAD", "*.wad"] for p in dirs.pwads.glob(pattern))
        if addon_wads:
            sample = ", ".join(addon_wads[:8])
            suffix = "" if len(addon_wads) <= 8 else f", ... ({len(addon_wads)} total)"
            add_validation_item(items, "PASS", f"Add-on WADs present in {dirs.pwads}: {sample}{suffix}")
        else:
            add_validation_item(items, "WARN", f"No add-on WADs found in {dirs.pwads}")

    def _validate_managed_mods(self, items: list[ValidationItem], dirs: Dirs) -> None:
        brutal_alias = dirs.brutal / BRUTAL_DOOM_ALIAS
        add_validation_item(
            items,
            "PASS" if brutal_alias.exists() else "WARN",
            f"Brutal Doom alias exists for Brutal presets: {brutal_alias}",
        )
        if brutal_alias.exists():
            brutal_metadata = dirs.brutal / "brutal-doom.json"
            add_validation_item(
                items,
                "PASS" if brutal_metadata.exists() else "WARN",
                f"Brutal Doom managed update metadata exists: {brutal_metadata}",
            )
        project_brutality_alias = dirs.project_brutality / PROJECT_BRUTALITY_ALIAS
        add_validation_item(
            items,
            "PASS" if project_brutality_alias.exists() else "WARN",
            f"Project Brutality alias exists for Project Brutality preset: {project_brutality_alias}",
        )
        if project_brutality_alias.exists():
            project_brutality_metadata = dirs.project_brutality / "project-brutality.json"
            add_validation_item(
                items,
                "PASS" if project_brutality_metadata.exists() else "WARN",
                f"Project Brutality managed update metadata exists: {project_brutality_metadata}",
            )
            markers_ok = zip_contains_markers(project_brutality_alias, {"zscript.zc", "gameinfo.txt"})
            add_validation_item(
                items,
                "PASS" if markers_ok else "WARN",
                f"Project Brutality archive has expected UZDoom root files: {project_brutality_alias}",
            )

    def _read_json_object_for_validation(
        self,
        items: list[ValidationItem],
        path: Path,
        label: str,
    ) -> Optional[dict[str, Any]]:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            add_validation_item(items, "FAIL", f"{label} is invalid: {path}: {exc}")
            return None
        if not isinstance(parsed, dict):
            add_validation_item(items, "FAIL", f"{label} must be an object: {path}")
            return None
        add_validation_item(items, "PASS", f"{label} is valid: {path}")
        return parsed

    def _validate_preset_manifest(self, items: list[ValidationItem], dirs: Dirs) -> Optional[PresetManifest]:
        manifest_path = dirs.doomrunner_config / "preset-manifest.json"
        if not manifest_path.exists():
            add_validation_item(items, "FAIL", f"Preset manifest missing: {manifest_path}")
            return None
        parsed = self._read_json_object_for_validation(items, manifest_path, "Preset manifest JSON")
        if parsed is None:
            return None
        try:
            return PresetManifest.from_json_object(parsed)
        except DoomDeckError as exc:
            add_validation_item(items, "FAIL", f"Preset manifest structure is invalid: {manifest_path}: {exc}")
            return None

    def _validate_preset_references(self, items: list[ValidationItem], manifest: PresetManifest, dirs: Dirs) -> None:
        manifest_path = dirs.doomrunner_config / "preset-manifest.json"
        project_brutality_preset_ok = any(preset.name == "Project Brutality" for preset in manifest.presets)
        add_validation_item(items, "PASS" if project_brutality_preset_ok else "FAIL", f"Preset manifest includes Project Brutality preset: {manifest_path}")
        for preset in manifest.presets:
            for key, path in [
                ("iwad", preset.iwad),
                ("config", preset.config),
                ("autoexec", preset.autoexec),
                ("launcher", preset.launcher),
            ]:
                add_validation_item(items, "PASS" if path.exists() else "FAIL", f"Preset {preset.name} references existing {key}: {path}")
            for p in preset.files:
                level = "PASS" if p.exists() else "WARN"
                add_validation_item(items, level, f"Preset {preset.name} mod file reference: {p}")

    def _validate_uzdoom_configs(self, items: list[ValidationItem], dirs: Dirs) -> None:
        for profile, back_binding in [("classic", "bind pad_b menu_back"), ("modern", "bind pad_b +deck_crouch_back")]:
            autoexec_path = dirs.uzdoom_config / profile / "autoexec.cfg"
            if autoexec_path.exists():
                text = autoexec_path.read_text(encoding="utf-8").lower()
                controller_ok = all(
                    needle in text
                    for needle in [
                        "use_joystick true",
                        "bind pad_a +deck_use_select",
                        back_binding,
                        "bind pad_start menu_main",
                        "bind f6 quicksave",
                        "bind f9 quickload",
                        "bind pad_lthumb quicksave",
                        "bind pad_rthumb quickload",
                    ]
                )
                add_validation_item(items, "PASS" if controller_ok else "FAIL", f"{profile} UZDoom Steam Deck controller bindings: {autoexec_path}")
            else:
                add_validation_item(items, "FAIL", f"{profile} UZDoom autoexec missing: {autoexec_path}")

            ini_path = dirs.uzdoom_config / profile / "uzdoom.ini"
            if ini_path.exists():
                text = ini_path.read_text(encoding="utf-8").lower()
                display_ok = all(
                    needle in text
                    for needle in [
                        f"vid_defwidth={STEAM_DECK_WIDTH}",
                        f"vid_defheight={STEAM_DECK_HEIGHT}",
                        "vid_fullscreen=true",
                        "use_joystick=true",
                    ]
                )
                add_validation_item(items, "PASS" if display_ok else "FAIL", f"{profile} UZDoom Steam Deck display settings: {ini_path}")
            else:
                add_validation_item(items, "FAIL", f"{profile} UZDoom ini missing: {ini_path}")

    def _validate_doomrunner_live_options(self, items: list[ValidationItem], dirs: Dirs) -> None:
        live_options_path = doomrunner_options_paths(dirs)[0]
        self._validate_doomrunner_options_path(items, dirs, live_options_path, "Doom Runner generated", missing_level="FAIL")

    def _validate_doomrunner_options_path(
        self,
        items: list[ValidationItem],
        dirs: Dirs,
        live_options_path: Path,
        label: str,
        *,
        missing_level: ValidationLevel | str,
    ) -> None:
        if live_options_path.exists():
            live_options = self._read_json_object_for_validation(items, live_options_path, f"{label} options JSON")
            if live_options is None:
                return
            engine_list = live_options.get("engines", {}).get("engine_list", [])
            engine_ok = any(
                engine.get("id") == DOOMRUNNER_ENGINE_ID
                and bool(engine.get("path"))
                and proton_linux_path(engine.get("path", "")).exists()
                for engine in engine_list
            )
            add_validation_item(items, "PASS" if engine_ok else "FAIL", f"{label} config has usable UZDoom engine: {live_options_path}")
            iwad_list = live_options.get("IWADs", {}).get("IWAD_list", [])
            iwad_ok = any(bool(iwad.get("path")) and proton_linux_path(iwad.get("path", "")).exists() for iwad in iwad_list)
            add_validation_item(items, "PASS" if iwad_ok else "FAIL", f"{label} config has IWAD entries: {live_options_path}")
            live_presets = live_options.get("presets", [])
            preset_ok = any(preset.get("selected_engine") == DOOMRUNNER_ENGINE_ID and preset.get("selected_IWAD") for preset in live_presets)
            add_validation_item(items, "PASS" if preset_ok else "FAIL", f"{label} config has launchable presets: {live_options_path}")
            resolved_presets = self._resolved_generated_preset_names(live_options)
            add_validation_item(
                items,
                "PASS" if resolved_presets else "FAIL",
                f"{label} config resolves UZDoom launch paths for presets: {', '.join(resolved_presets) if resolved_presets else live_options_path}",
            )
            video_options = live_options.get("video_options", {})
            resolution_ok = (
                video_options.get("resolution_x") == STEAM_DECK_WIDTH
                and video_options.get("resolution_y") == STEAM_DECK_HEIGHT
            )
            add_validation_item(items, "PASS" if resolution_ok else "FAIL", f"{label} config uses Steam Deck resolution: {live_options_path}")
        else:
            add_validation_item(items, missing_level, f"{label} options missing: {live_options_path}")

    def _resolved_generated_preset_names(self, live_options: dict[str, Any]) -> list[str]:
        engine_list = live_options.get("engines", {}).get("engine_list", [])
        if not isinstance(engine_list, list):
            return []
        engines = {
            str(engine.get("id")): engine
            for engine in engine_list
            if isinstance(engine, dict) and bool(engine.get("id")) and proton_linux_path(engine.get("path", "")).exists()
        }
        live_presets = live_options.get("presets", [])
        if not isinstance(live_presets, list):
            return []
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
            if not self._additional_args_paths_exist(str(preset.get("additional_args", ""))):
                continue
            names.append(str(preset.get("name", "")).strip() or "<unnamed>")
        return names

    def _additional_args_paths_exist(self, additional_args: str) -> bool:
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

    def _validate_shell_scripts(self, items: list[ValidationItem], dirs: Dirs) -> None:
        shell_scripts = sorted(dirs.launchers.glob("*.sh"))
        seen_scripts: set[Path] = set()
        for script in shell_scripts:
            if script in seen_scripts:
                continue
            seen_scripts.add(script)
            if script.exists():
                shebang_ok = script_has_execve_shebang(script)
                add_validation_item(
                    items,
                    "PASS" if shebang_ok else "FAIL",
                    f"Shell script has execve-compatible shebang on first line: {script}",
                )
                syntax_ok = self.shell_syntax_checker(script)
                add_validation_item(items, "PASS" if syntax_ok else "FAIL", f"Shell syntax valid for {script}")

    def _validate_steam(self, items: list[ValidationItem], dirs: Dirs, steam: SteamInfo) -> None:
        doomrunner_exe = dirs.doomrunner / "DoomRunner.exe"
        if steam.steam_root:
            add_validation_item(items, "PASS", f"Steam root detected: {steam.steam_root}")
        else:
            add_validation_item(items, "WARN", "Steam root not detected")
        if steam.app_install_dir:
            add_validation_item(items, "PASS", f"Steam app {self.steam_appid} install detected: {steam.app_install_dir}")
        else:
            add_validation_item(items, "WARN", f"Steam app {self.steam_appid} install not detected")

        if steam.shortcuts_vdf and steam.shortcuts_vdf.exists():
            try:
                root = load_shortcuts(steam.shortcuts_vdf)
                shortcuts_obj = shortcut_entries(root)
                doomrunner_shortcuts: list[tuple[int | None, str]] = []
                extra_preset_shortcuts: list[str] = []
                for value in shortcuts_obj.values():
                    if value.type_code != BKV_OBJECT:
                        continue
                    appname = get_bkv_str(value.value, "appname", "AppName")
                    if appname == "Doom Runner":
                        exe = get_bkv_str(value.value, "exe", "Exe")
                        appid_value = value.value.get("appid")
                        appid = int(appid_value.value) if appid_value is not None else None
                        doomrunner_shortcuts.append((appid, exe))
                    elif appname.startswith("DoomDeck - "):
                        extra_preset_shortcuts.append(appname)
                expected_doomrunner_shortcuts = [
                    (appid, exe) for appid, exe in doomrunner_shortcuts if str(doomrunner_exe) in exe
                ]
                if len(doomrunner_shortcuts) == 1 and expected_doomrunner_shortcuts:
                    add_validation_item(items, "PASS", "Exactly one Steam shortcut exists for Windows Doom Runner with expected executable path")
                elif not doomrunner_shortcuts:
                    add_validation_item(items, "WARN", f"No Doom Runner shortcut found in {steam.shortcuts_vdf}")
                elif len(doomrunner_shortcuts) == 1:
                    add_validation_item(items, "WARN", f"Steam shortcut named Doom Runner exists but exe differs: {doomrunner_shortcuts[0][1]}")
                else:
                    add_validation_item(items, "FAIL", f"Multiple Doom Runner Steam shortcuts exist: {len(doomrunner_shortcuts)}")
                if extra_preset_shortcuts:
                    add_validation_item(
                        items,
                        "FAIL",
                        f"No extra DoomDeck preset Steam shortcuts remain: {', '.join(sorted(extra_preset_shortcuts))}",
                    )
                else:
                    add_validation_item(items, "PASS", "No extra DoomDeck preset Steam shortcuts remain")
                doomdeck_appids = [appid for appid, _exe in expected_doomrunner_shortcuts if appid is not None]
                add_validation_item(
                    items,
                    "PASS" if doomdeck_appids else "WARN",
                    "Steam shortcut appid is available for Doom Runner Proton mapping",
                )
                self._validate_steam_compat_mapping(items, steam, doomdeck_appids)
                self._validate_doomrunner_proton_options(items, dirs, steam, doomdeck_appids)
            except DoomDeckError as exc:
                add_validation_item(items, "FAIL", f"Could not parse shortcuts.vdf: {exc}")
        else:
            add_validation_item(items, "WARN", "Steam shortcuts.vdf does not exist yet or Steam user was not detected")

    def _validate_doomrunner_proton_options(self, items: list[ValidationItem], dirs: Dirs, steam: SteamInfo, appids: list[int]) -> None:
        for appid in appids:
            proton_options = doomrunner_proton_options_path(steam, appid)
            if proton_options is not None and proton_options.exists():
                self._validate_doomrunner_options_path(
                    items,
                    dirs,
                    proton_options,
                    "Doom Runner Proton-prefix",
                    missing_level="WARN",
                )
            elif proton_options is not None:
                add_validation_item(items, "WARN", f"Doom Runner Proton-prefix options missing: {proton_options}")

    def _validate_steam_compat_mapping(self, items: list[ValidationItem], steam: SteamInfo, appids: list[int]) -> None:
        if not appids:
            return
        localconfig = steam.localconfig_vdf or (steam.shortcuts_vdf.parent / "localconfig.vdf" if steam.shortcuts_vdf else None)
        if not localconfig or not localconfig.exists():
            add_validation_item(items, "WARN", "Steam localconfig.vdf does not exist yet; Proton compatibility mapping cannot be confirmed")
            return
        root = load_text_vdf(localconfig)
        mapping: object = root
        for key in ["UserLocalConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"]:
            if not isinstance(mapping, dict):
                mapping = {}
                break
            mapping = cast(dict[str, object], mapping).get(key, {})
        if not isinstance(mapping, dict):
            add_validation_item(items, "WARN", f"Steam Proton compatibility mapping is missing or malformed: {localconfig}")
            return
        mapping_dict = cast(dict[str, object], mapping)
        mapped = [appid for appid in appids if isinstance(mapping_dict.get(compat_mapping_key(appid)), dict)]
        add_validation_item(
            items,
            "PASS" if mapped else "WARN",
            f"Steam Proton compatibility mapping exists for DoomDeck shortcuts: {localconfig}",
        )

    def _validate_backups(self, items: list[ValidationItem], dirs: Dirs) -> None:
        if not any(dirs.backups.glob("*")):
            add_validation_item(items, "WARN", f"No backups found yet in {dirs.backups}; this is normal before the first replacement or Steam shortcut update")
        else:
            add_validation_item(items, "PASS", f"Backups directory contains backup files: {dirs.backups}")
