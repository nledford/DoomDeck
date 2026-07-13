"""Discover SteamOS, Steam libraries, and the active Steam user."""
from __future__ import annotations

import logging
import platform
import re
from dataclasses import dataclass
from pathlib import Path

from doomdeck.domain.models import SteamInfo
from doomdeck.domain.paths import expand_path

DOOM_PLUS_DOOM_II_APP_ID = "2280"
STEAM_ROOT_CANDIDATES = (
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".steam" / "steam",
    Path.home() / ".steam" / "root",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
)


@dataclass(frozen=True)
class SteamDiscoverySettings:
    steam_root: str | None
    steam_user_id: str | None


def detect_steamos() -> tuple[bool, str]:
    if platform.system() != "Linux":
        return False, f"Not Linux: {platform.system()}"
    os_release = Path("/etc/os-release")
    text = os_release.read_text(encoding="utf-8", errors="ignore") if os_release.exists() else ""
    markers = ["steam", "steamos", "valve"]
    if any(marker in text.lower() for marker in markers):
        return True, "/etc/os-release looks like SteamOS or Valve Linux"
    if Path("/run/host/usr/bin/steamos-session-select").exists() or Path("/usr/bin/steamos-session-select").exists():
        return True, "SteamOS session selector found"
    return False, "Linux detected, but SteamOS markers were not found"


def find_steam_root(explicit: str | None) -> Path | None:
    if explicit:
        path = expand_path(explicit)
        return path if path.exists() else None
    for candidate in STEAM_ROOT_CANDIDATES:
        try:
            resolved = candidate.expanduser().resolve()
        except FileNotFoundError:
            resolved = candidate.expanduser()
        if (resolved / "steamapps").exists() or (resolved / "userdata").exists():
            return resolved
    return None


def parse_library_folders(steam_root: Path, logger: logging.Logger) -> list[Path]:
    candidates = [
        steam_root / "steamapps" / "libraryfolders.vdf",
        steam_root / "config" / "libraryfolders.vdf",
    ]
    folders: list[Path] = [steam_root]
    path_pattern = re.compile(r'"path"\s+"([^"]+)"')
    for file_path in candidates:
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for raw in path_pattern.findall(text):
            path = Path(raw.replace("\\\\", "\\")).expanduser()
            if path.exists():
                folders.append(path.resolve())
    deduped = list(dict.fromkeys(str(folder) for folder in folders))
    result = [Path(folder) for folder in deduped]
    logger.debug("Steam library folders: %s", result)
    return result


def parse_installdir_from_manifest(manifest: Path) -> str | None:
    text = manifest.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'"installdir"\s+"([^"]+)"', text)
    return match.group(1) if match else None


def find_steam_app_install_dir(
    library_folders: list[Path],
    appid: str,
    logger: logging.Logger,
) -> Path | None:
    for library in library_folders:
        steamapps = library / "steamapps"
        manifest = steamapps / f"appmanifest_{appid}.acf"
        if not manifest.exists():
            continue
        install_dir_name = parse_installdir_from_manifest(manifest)
        if install_dir_name:
            install_dir = steamapps / "common" / install_dir_name
            if install_dir.exists():
                logger.info("Found Steam app %s at %s", appid, install_dir)
                return install_dir.resolve()
    return None


def find_steam_user_id(
    steam_root: Path,
    explicit: str | None,
    logger: logging.Logger,
) -> tuple[str | None, Path | None]:
    if explicit:
        shortcuts = steam_root / "userdata" / explicit / "config" / "shortcuts.vdf"
        return explicit, shortcuts
    userdata = steam_root / "userdata"
    if not userdata.exists():
        return None, None
    candidates = [path for path in userdata.iterdir() if path.is_dir() and path.name.isdigit()]
    if not candidates:
        return None, None

    def score(path: Path) -> tuple[int, float]:
        config = path / "config"
        shortcuts = config / "shortcuts.vdf"
        localconfig = config / "localconfig.vdf"
        nonzero = 1 if path.name != "0" else 0
        exists_score = (2 if shortcuts.exists() else 0) + (1 if localconfig.exists() else 0)
        mtime = max(
            [candidate.stat().st_mtime for candidate in [shortcuts, localconfig, config] if candidate.exists()],
            default=0.0,
        )
        return nonzero + exists_score, mtime

    chosen = sorted(candidates, key=score, reverse=True)[0]
    logger.info("Selected Steam user ID %s", chosen.name)
    return chosen.name, chosen / "config" / "shortcuts.vdf"


def discover_steam(
    settings: SteamDiscoverySettings,
    logger: logging.Logger,
    appid: str = DOOM_PLUS_DOOM_II_APP_ID,
) -> SteamInfo:
    steam_root = find_steam_root(settings.steam_root)
    if not steam_root:
        return SteamInfo(None, None, None, [], None)
    libraries = parse_library_folders(steam_root, logger)
    app_install_dir = find_steam_app_install_dir(libraries, appid, logger)
    user_id, shortcuts = find_steam_user_id(steam_root, settings.steam_user_id, logger)
    localconfig = shortcuts.parent / "localconfig.vdf" if shortcuts else None
    return SteamInfo(steam_root, user_id, shortcuts, libraries, app_install_dir, localconfig)
