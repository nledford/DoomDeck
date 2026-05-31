#!/usr/bin/env python3
"""
DoomDeck CLI

Steam Deck Doom modding setup automation for:
- Steam DOOM + DOOM II app 2280 IWAD discovery/copy
- Doom Runner AppImage installation
- UZDoom AppImage installation
- Brutal Doom manual-drop validation
- Steam non-Steam shortcut integration for Doom Runner
- Direct UZDoom launcher scripts for vanilla-style, UZDoom, Brutal Doom, and Project Brutality presets
- Doom Runner live options.json generation for current Linux/AppImage builds

Design goals:
- User-space only by default
- Safe, idempotent, rerunnable
- No root requirement
- Back up Steam shortcuts.vdf before modification
- Back up Doom Runner options.json before modification

Tested for syntax on Python 3.11. Should work on Python 3.10+.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import fnmatch
import hashlib
import html
import json
import logging
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, Optional

APPID_DOOM_PLUS_DOOM_II = "2280"
DEFAULT_ROOT = Path.home() / "Games" / "Doom"
SCRIPT_VERSION = "2026.05.31"
DOOMRUNNER_OPTIONS_VERSION = "1.9.2"
DOOMRUNNER_ENGINE_ID = "doomdeck-uzdoom"
DOOMRUNNER_ENGINE_NAME = "UZDoom"

IWAD_CANONICAL_NAMES = {
    "doom.wad": "Doom",
    "doom1.wad": "Doom Shareware",
    "doom2.wad": "Doom II",
    "tnt.wad": "Final Doom: TNT Evilution",
    "plutonia.wad": "Final Doom: The Plutonia Experiment",
}

DOOMRUNNER_IWAD_DISPLAY_NAMES = {
    "doom.wad": "The Ultimate Doom",
    "doom1.wad": "Doom Shareware",
    "doom2.wad": "Doom II: Hell on Earth",
    "tnt.wad": "Final Doom: TNT Evilution",
    "plutonia.wad": "Final Doom: The Plutonia Experiment",
}

DEFAULT_PRESET_IWADS = ["doom2.wad", "doom.wad", "tnt.wad", "plutonia.wad", "doom1.wad"]
MODDB_BASE_URL = "https://www.moddb.com"
BRUTAL_DOOM_ALIAS = "brutal-doom.pk3"
BRUTAL_DOOM_MODDB_URL = "https://www.moddb.com/mods/brutal-doom"
BRUTAL_DOOM_DOWNLOADS_URL = "https://www.moddb.com/mods/brutal-doom/downloads"
PROJECT_BRUTALITY_REPO = "pa1nki113r/Project_Brutality"
PROJECT_BRUTALITY_ALIAS = "project-brutality.pk3"
STEAM_DECK_WIDTH = 1280
STEAM_DECK_HEIGHT = 800
STEAM_DECK_TARGET_FPS = 60

UZDOOM_STEAM_DECK_GLOBAL_SETTINGS = [
    ("vid_fullscreen", "true"),
    ("vid_defwidth", str(STEAM_DECK_WIDTH)),
    ("vid_defheight", str(STEAM_DECK_HEIGHT)),
    ("vid_aspect", "0"),
    ("vid_cropaspect", "false"),
    ("vid_vsync", "true"),
    ("vid_maxfps", str(STEAM_DECK_TARGET_FPS)),
    ("vid_preferbackend", "1"),
    ("vid_rendermode", "4"),
    ("vk_exclusivefullscreen", "false"),
    ("autoloadwidescreen", "true"),
    ("gl_fxaa", "0"),
    ("gl_multisample", "1"),
    ("gl_ssao", "0"),
    ("gl_light_shadowmap", "false"),
    ("gl_texture_filter", "0"),
    ("gl_texture_filter_anisotropic", "4"),
    ("vid_scale_linear", "false"),
    ("vid_scalefactor", "1"),
    ("vid_scalemode", "0"),
    ("m_blockcontrollers", "false"),
    ("use_joystick", "true"),
]

WAD_COPY_EXCLUDES = {
    # DOSBox and engine support archives are not playable WAD content.
    "dosbox.wad",
}

STEAM_ROOT_CANDIDATES = [
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".steam" / "steam",
    Path.home() / ".steam" / "root",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
]

GITHUB_USER_AGENT = f"doomdeck/{SCRIPT_VERSION}"

# Binary VDF value type bytes used by Steam shortcuts.vdf.
BKV_OBJECT = 0x00
BKV_STRING = 0x01
BKV_INT32 = 0x02
BKV_FLOAT32 = 0x03
BKV_UINT64 = 0x07
BKV_END = 0x08


class DoomDeckError(RuntimeError):
    """A predictable setup/validation error with a human-actionable message."""


@dataclasses.dataclass
class Dirs:
    root: Path
    tools: Path
    doomrunner: Path
    ports: Path
    uzdoom: Path
    iwads: Path
    pwads: Path
    mods: Path
    brutal: Path
    project_brutality: Path
    configs: Path
    xdg_config: Path
    xdg_data: Path
    doomrunner_config: Path
    uzdoom_config: Path
    launchers: Path
    saves: Path
    screenshots: Path
    logs: Path
    backups: Path
    downloads: Path
    docs: Path


@dataclasses.dataclass
class SteamInfo:
    steam_root: Optional[Path]
    user_id: Optional[str]
    shortcuts_vdf: Optional[Path]
    library_folders: list[Path]
    app_install_dir: Optional[Path]


@dataclasses.dataclass
class GitHubAsset:
    name: str
    url: str
    size: Optional[int]
    tag_name: str


@dataclasses.dataclass
class ModDBDownload:
    title: str
    page_url: str
    filename: str
    download_url: str
    updated: str
    md5: str


@dataclasses.dataclass
class ValidationItem:
    level: str  # PASS, WARN, FAIL
    message: str


@dataclasses.dataclass
class BKVValue:
    type_code: int
    value: Any


class BinaryVDF:
    """Minimal binary KeyValues reader/writer for Steam shortcuts.vdf.

    This intentionally supports only the value types normally seen in
    shortcuts.vdf and fails closed on unknown types so the script will not
    silently corrupt a user's Steam shortcut database.
    """

    def __init__(self, data: bytes = b"") -> None:
        self.data = data
        self.offset = 0

    @staticmethod
    def loads(data: bytes) -> OrderedDict[str, BKVValue]:
        parser = BinaryVDF(data)
        root = parser._read_object(implicit_root=True)
        return root

    @staticmethod
    def dumps(root: OrderedDict[str, BKVValue]) -> bytes:
        out = bytearray()
        for key, value in root.items():
            BinaryVDF._write_entry(out, key, value)
        out.append(BKV_END)
        return bytes(out)

    def _read_cstring(self) -> str:
        try:
            end = self.data.index(b"\x00", self.offset)
        except ValueError as exc:
            raise DoomDeckError("Invalid binary VDF: unterminated string") from exc
        raw = self.data[self.offset : end]
        self.offset = end + 1
        return raw.decode("utf-8", errors="replace")

    def _read_object(self, implicit_root: bool = False) -> OrderedDict[str, BKVValue]:
        obj: OrderedDict[str, BKVValue] = OrderedDict()
        while self.offset < len(self.data):
            type_code = self.data[self.offset]
            self.offset += 1
            if type_code == BKV_END:
                break

            key = self._read_cstring()

            if type_code == BKV_OBJECT:
                obj[key] = BKVValue(type_code, self._read_object())
            elif type_code == BKV_STRING:
                obj[key] = BKVValue(type_code, self._read_cstring())
            elif type_code == BKV_INT32:
                self._require_bytes(4)
                obj[key] = BKVValue(type_code, struct.unpack_from("<i", self.data, self.offset)[0])
                self.offset += 4
            elif type_code == BKV_FLOAT32:
                self._require_bytes(4)
                obj[key] = BKVValue(type_code, struct.unpack_from("<f", self.data, self.offset)[0])
                self.offset += 4
            elif type_code == BKV_UINT64:
                self._require_bytes(8)
                obj[key] = BKVValue(type_code, struct.unpack_from("<Q", self.data, self.offset)[0])
                self.offset += 8
            else:
                scope = "top-level" if implicit_root else "nested"
                raise DoomDeckError(
                    f"Unsupported binary VDF type byte 0x{type_code:02x} in {scope} object near offset {self.offset - 1}. "
                    "Not modifying shortcuts.vdf."
                )
        return obj

    def _require_bytes(self, count: int) -> None:
        if self.offset + count > len(self.data):
            raise DoomDeckError("Invalid binary VDF: truncated scalar value")

    @staticmethod
    def _write_cstring(out: bytearray, text: str) -> None:
        out.extend(text.encode("utf-8"))
        out.append(0)

    @staticmethod
    def _write_entry(out: bytearray, key: str, value: BKVValue) -> None:
        out.append(value.type_code)
        BinaryVDF._write_cstring(out, key)
        if value.type_code == BKV_OBJECT:
            for child_key, child_value in value.value.items():
                BinaryVDF._write_entry(out, child_key, child_value)
            out.append(BKV_END)
        elif value.type_code == BKV_STRING:
            BinaryVDF._write_cstring(out, str(value.value))
        elif value.type_code == BKV_INT32:
            out.extend(struct.pack("<i", int(value.value)))
        elif value.type_code == BKV_FLOAT32:
            out.extend(struct.pack("<f", float(value.value)))
        elif value.type_code == BKV_UINT64:
            out.extend(struct.pack("<Q", int(value.value)))
        else:
            raise DoomDeckError(f"Cannot write unsupported binary VDF type 0x{value.type_code:02x}")


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def build_dirs(root: Path) -> Dirs:
    return Dirs(
        root=root,
        tools=root / "tools",
        doomrunner=root / "tools" / "doomrunner",
        ports=root / "source-ports",
        uzdoom=root / "source-ports" / "uzdoom",
        iwads=root / "iwads",
        pwads=root / "pwads",
        mods=root / "mods",
        brutal=root / "mods" / "brutal-doom",
        project_brutality=root / "mods" / "project-brutality",
        configs=root / "configs",
        xdg_config=root / "configs" / "xdg-config",
        xdg_data=root / "configs" / "xdg-data",
        doomrunner_config=root / "configs" / "doomrunner",
        uzdoom_config=root / "configs" / "uzdoom",
        launchers=root / "launchers",
        saves=root / "saves",
        screenshots=root / "screenshots",
        logs=root / "logs",
        backups=root / "backups",
        downloads=root / "downloads",
        docs=root / "docs",
    )


def all_managed_dirs(dirs: Dirs) -> list[Path]:
    return [
        dirs.root,
        dirs.tools,
        dirs.doomrunner,
        dirs.ports,
        dirs.uzdoom,
        dirs.iwads,
        dirs.pwads,
        dirs.mods,
        dirs.brutal,
        dirs.project_brutality,
        dirs.configs,
        dirs.xdg_config,
        dirs.xdg_data,
        dirs.doomrunner_config,
        dirs.uzdoom_config,
        dirs.launchers,
        dirs.saves,
        dirs.screenshots,
        dirs.logs,
        dirs.backups,
        dirs.downloads,
        dirs.docs,
    ]


def configure_logging(dirs: Dirs, verbose: bool, dry_run: bool) -> logging.Logger:
    logger = logging.getLogger("doom_deck_setup")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)

    if not dry_run:
        dirs.logs.mkdir(parents=True, exist_ok=True)
        logfile = dirs.logs / f"doom-deck-setup-{now_stamp()}.log"
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
        logger.info("Logging to %s", logfile)
    else:
        logger.info("Dry run: no log file will be written")
    return logger


def ensure_dir(path: Path, dry_run: bool, logger: logging.Logger) -> None:
    if path.exists():
        return
    logger.info("Create directory: %s", path)
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, content: str, dry_run: bool, logger: logging.Logger, mode: int = 0o644) -> None:
    logger.info("Write file: %s", path)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    tmp_path.replace(path)


def atomic_write_bytes(path: Path, content: bytes, dry_run: bool, logger: logging.Logger, mode: int = 0o644) -> None:
    logger.info("Write file: %s", path)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    tmp_path.replace(path)


def make_executable(path: Path, dry_run: bool, logger: logging.Logger) -> None:
    logger.info("Mark executable: %s", path)
    if dry_run:
        return
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def script_has_execve_shebang(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_equal(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return sha256_file(a) == sha256_file(b)


def backup_path(path: Path, backups_dir: Path, dry_run: bool, logger: logging.Logger, label: Optional[str] = None) -> Optional[Path]:
    if not path.exists():
        return None
    label_text = label or path.name
    dest = backups_dir / f"{label_text}.{now_stamp()}"
    logger.info("Back up %s -> %s", path, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, symlinks=True)
    else:
        shutil.copy2(path, dest)
    return dest


def replace_file_safely(src: Path, dest: Path, backups_dir: Path, dry_run: bool, logger: logging.Logger) -> None:
    if dest.exists() and files_equal(src, dest):
        logger.info("Already current: %s", dest)
        make_executable(dest, dry_run, logger)
        return
    if dest.exists():
        backup_path(dest, backups_dir, dry_run, logger, label=dest.name)
    logger.info("Install file: %s -> %s", src, dest)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    make_executable(dest, dry_run, logger)


def run_command(
    cmd: list[str],
    logger: logging.Logger,
    dry_run: bool = False,
    check: bool = False,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    logger.debug("Run command: %s", " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if check and result.returncode != 0:
        raise DoomDeckError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def print_plan(title: str, actions: Iterable[str]) -> None:
    print(f"\n{title}")
    print("=" * len(title))
    for action in actions:
        print(f"- {action}")
    print()


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


def find_steam_root(explicit: Optional[str]) -> Optional[Path]:
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
            p = Path(raw.replace("\\\\", "\\")).expanduser()
            if p.exists():
                folders.append(p.resolve())
    deduped: list[Path] = []
    seen: set[str] = set()
    for folder in folders:
        key = str(folder)
        if key not in seen:
            seen.add(key)
            deduped.append(folder)
    logger.debug("Steam library folders: %s", deduped)
    return deduped


def parse_installdir_from_manifest(manifest: Path) -> Optional[str]:
    text = manifest.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'"installdir"\s+"([^"]+)"', text)
    return match.group(1) if match else None


def find_steam_app_install_dir(library_folders: list[Path], appid: str, logger: logging.Logger) -> Optional[Path]:
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
        # Fallback: app manifest exists but installdir was absent or moved.
        common = steamapps / "common"
        if common.exists():
            for child in common.iterdir():
                if child.is_dir() and list(child.rglob("*.wad")):
                    logger.debug("Fallback candidate for app %s: %s", appid, child)
    return None


def find_steam_user_id(steam_root: Path, explicit: Optional[str], logger: logging.Logger) -> tuple[Optional[str], Optional[Path]]:
    if explicit:
        shortcuts = steam_root / "userdata" / explicit / "config" / "shortcuts.vdf"
        return explicit, shortcuts
    userdata = steam_root / "userdata"
    if not userdata.exists():
        return None, None
    candidates = [p for p in userdata.iterdir() if p.is_dir() and p.name.isdigit()]
    if not candidates:
        return None, None

    def score(path: Path) -> tuple[int, float]:
        cfg = path / "config"
        shortcuts = cfg / "shortcuts.vdf"
        localconfig = cfg / "localconfig.vdf"
        nonzero = 1 if path.name != "0" else 0
        exists_score = (2 if shortcuts.exists() else 0) + (1 if localconfig.exists() else 0)
        mtime = max(
            [x.stat().st_mtime for x in [shortcuts, localconfig, cfg] if x.exists()],
            default=0.0,
        )
        return (nonzero + exists_score, mtime)

    chosen = sorted(candidates, key=score, reverse=True)[0]
    logger.info("Selected Steam user ID %s", chosen.name)
    return chosen.name, chosen / "config" / "shortcuts.vdf"


def discover_steam(args: argparse.Namespace, logger: logging.Logger) -> SteamInfo:
    steam_root = find_steam_root(args.steam_root)
    if not steam_root:
        return SteamInfo(None, None, None, [], None)
    libraries = parse_library_folders(steam_root, logger)
    app_install_dir = find_steam_app_install_dir(libraries, APPID_DOOM_PLUS_DOOM_II, logger)
    user_id, shortcuts = find_steam_user_id(steam_root, args.steam_user_id, logger)
    return SteamInfo(steam_root, user_id, shortcuts, libraries, app_install_dir)


def score_iwad_candidate(path: Path) -> tuple[int, float]:
    parts = [p.lower() for p in path.parts]
    score = 0
    if "rerelease" in parts:
        score += 50
    if "base" in parts:
        score += 40
    if "dosbox" in parts:
        score += 10
    if any(part in {"soundtrack", "music", "manual"} for part in parts):
        score -= 100
    try:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
    except OSError:
        size = 0
        mtime = 0.0
    if size > 1_000_000:
        score += 10
    return score, mtime


def find_wads_in_install(install_dir: Optional[Path], logger: logging.Logger) -> tuple[dict[str, Path], dict[str, Path]]:
    found_iwads: dict[str, list[Path]] = {name: [] for name in IWAD_CANONICAL_NAMES}
    found_pwads: dict[str, list[Path]] = {}
    if not install_dir or not install_dir.exists():
        return {}, {}
    for file_path in install_dir.rglob("*"):
        if not file_path.is_file():
            continue
        name = file_path.name.lower()
        if file_path.suffix.lower() != ".wad" or name in WAD_COPY_EXCLUDES:
            continue
        if name in found_iwads:
            found_iwads[name].append(file_path)
        else:
            found_pwads.setdefault(name, []).append(file_path)

    best: dict[str, Path] = {}
    for name, candidates in found_iwads.items():
        if not candidates:
            continue
        chosen = sorted(candidates, key=score_iwad_candidate, reverse=True)[0]
        best[name] = chosen.resolve()
        logger.info("Selected IWAD %s from %s", name, chosen)

    extras: dict[str, Path] = {}
    for name, candidates in found_pwads.items():
        chosen = sorted(candidates, key=score_iwad_candidate, reverse=True)[0]
        extras[name] = chosen.resolve()
        logger.info("Selected add-on WAD %s from %s", name, chosen)
    return best, extras


def copy_wads(wads: dict[str, Path], dest_dir: Path, backups_dir: Path, dry_run: bool, logger: logging.Logger, label: str) -> None:
    for name, src in wads.items():
        dest = dest_dir / name.upper()
        if dest.exists() and files_equal(src, dest):
            logger.info("%s already copied: %s", label, dest)
            continue
        if dest.exists():
            backup_path(dest, backups_dir, dry_run, logger, label=dest.name)
        logger.info("Copy %s: %s -> %s", label, src, dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def copy_iwads(iwads: dict[str, Path], dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    copy_wads(iwads, dirs.iwads, dirs.backups, dry_run, logger, "IWAD")


def copy_addon_wads(wads: dict[str, Path], dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    copy_wads(wads, dirs.pwads, dirs.backups, dry_run, logger, "add-on WAD")


def github_request_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": GITHUB_USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text_url(url: str, logger: Optional[logging.Logger] = None) -> str:
    if logger:
        logger.debug("Fetch metadata page: %s", url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": GITHUB_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace")


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def html_text_lines(text: str) -> list[str]:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|dt|dd|tr|td|th)>", "\n", text)
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    lines = [re.sub(r"\s+", " ", html.unescape(line)).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def html_links(text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"""(?is)<a\b[^>]*\bhref\s*=\s*["'](?P<href>[^"']+)["'][^>]*>(?P<body>.*?)</a>""", text):
        href = html.unescape(match.group("href")).strip()
        body = strip_html(match.group("body"))
        if href:
            links.append((href, body))
    return links


def absolute_moddb_url(href: str, base: str = MODDB_BASE_URL) -> str:
    return urllib.parse.urljoin(base, html.unescape(href).strip())


def select_release_asset(repo: str, prefer_legacy_appimage: bool, logger: logging.Logger) -> GitHubAsset:
    release = github_request_json(f"https://api.github.com/repos/{repo}/releases/latest")
    tag_name = release.get("tag_name") or release.get("name") or "latest"
    assets = release.get("assets", [])
    if not assets:
        raise DoomDeckError(f"GitHub release {repo}@{tag_name} has no downloadable assets")

    repo_key = repo.split("/")[-1].lower().replace("_", "").replace("-", "")

    def score(asset: dict[str, Any]) -> int:
        name = asset.get("name", "")
        lower = name.lower()
        value = 0
        if "appimage" in lower:
            value += 100
        if "linux" in lower:
            value += 50
        if any(token in lower for token in ["x86_64", "x64", "amd64"]):
            value += 30
        if repo_key in lower.replace("_", "").replace("-", ""):
            value += 10
        if "legacy" in lower:
            value += 20 if prefer_legacy_appimage else -25
        if any(token in lower for token in ["windows", "win64", ".exe", "mac", "dmg", "arm64", "aarch64"]):
            value -= 100
        return value

    ranked = sorted(assets, key=score, reverse=True)
    chosen = ranked[0]
    if score(chosen) < 50:
        names = ", ".join(a.get("name", "<unnamed>") for a in assets)
        raise DoomDeckError(f"Could not identify a suitable Linux AppImage for {repo}@{tag_name}. Assets: {names}")
    logger.info("Selected GitHub asset for %s: %s", repo, chosen.get("name"))
    return GitHubAsset(
        name=chosen["name"],
        url=chosen["browser_download_url"],
        size=chosen.get("size"),
        tag_name=str(tag_name),
    )


def download_url(
    url: str,
    dest: Path,
    dry_run: bool,
    logger: logging.Logger,
    force: bool = False,
    headers: Optional[dict[str, str]] = None,
) -> Path:
    if dest.exists() and not force:
        logger.info("Download already exists: %s", dest)
        return dest
    logger.info("Download: %s -> %s", url, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {"User-Agent": GITHUB_USER_AGENT}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        tmp.replace(dest)
    except urllib.error.URLError as exc:
        if tmp.exists():
            tmp.unlink()
        raise DoomDeckError(f"Failed to download {url}: {exc}") from exc
    return dest


def safe_download_name(value: str, fallback: str) -> str:
    name = value.rstrip("/").split("/")[-1].split("?")[0]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or fallback


def install_appimage_from_github(
    repo: str,
    target: Path,
    dirs: Dirs,
    args: argparse.Namespace,
    logger: logging.Logger,
    explicit_url: Optional[str] = None,
) -> Optional[Path]:
    if args.skip_downloads and not explicit_url:
        if target.exists():
            logger.info("Skipping download; using existing %s", target)
            return target
        logger.warning("Skipping download and target does not exist: %s", target)
        return None
    if explicit_url:
        asset_name = safe_download_name(explicit_url, f"{repo.split('/')[-1]}.AppImage")
        url = explicit_url
    else:
        asset = select_release_asset(repo, args.prefer_legacy_appimage, logger)
        asset_name = asset.name
        url = asset.url
    download_dest = dirs.downloads / asset_name
    downloaded = download_url(url, download_dest, args.dry_run, logger, force=args.force_download)
    if not args.dry_run and not downloaded.exists():
        raise DoomDeckError(f"Expected downloaded asset at {downloaded}")
    replace_file_safely(downloaded, target, dirs.backups, args.dry_run, logger)
    return target


def split_zip_name(name: str) -> list[str]:
    return [part for part in name.replace("\\", "/").split("/") if part not in {"", "."}]


def common_zip_toplevel(names: Iterable[str]) -> Optional[str]:
    split_names = [split_zip_name(name) for name in names]
    split_names = [parts for parts in split_names if parts]
    if not split_names:
        return None
    candidate = split_names[0][0]
    if all(len(parts) > 1 and parts[0] == candidate for parts in split_names):
        return candidate
    return None


def normalized_zip_member_name(raw_name: str, prefix: Optional[str]) -> Optional[str]:
    parts = split_zip_name(raw_name)
    if not parts or any(part == ".." for part in parts):
        return None
    if prefix and parts[0] == prefix:
        parts = parts[1:]
    if not parts:
        return None
    return "/".join(parts)


def zip_contains_markers(path: Path, markers: set[str]) -> bool:
    if not path.exists() or not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            prefix = common_zip_toplevel(names)
            normalized = {
                (normalized_zip_member_name(name, prefix) or "").lower()
                for name in names
            }
    except (OSError, zipfile.BadZipFile):
        return False
    return markers.issubset(normalized)


def metadata_matches(metadata_path: Path, expected: dict[str, str], keys: Iterable[str]) -> bool:
    if not metadata_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return all(str(metadata.get(key, "")) == str(expected.get(key, "")) for key in keys)


def write_mod_zip_as_pk3(
    src: Path,
    dest: Path,
    backups_dir: Path,
    metadata_path: Path,
    dry_run: bool,
    logger: logging.Logger,
    source: dict[str, str],
    force: bool = False,
) -> Path:
    if not src.exists() and not dry_run:
        raise DoomDeckError(f"Project Brutality download is missing: {src}")
    source_sha = sha256_file(src) if src.exists() else ""
    if dest.exists() and metadata_path.exists() and not force:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
        if metadata.get("source_sha256") == source_sha:
            logger.info("Project Brutality already current: %s", dest)
            return dest

    logger.info("Install Project Brutality archive: %s -> %s", src, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup_path(dest, backups_dir, dry_run, logger, label=dest.name)

    if src.suffix.lower() == ".wad" or not zipfile.is_zipfile(src):
        shutil.copy2(src, dest)
    else:
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            with zipfile.ZipFile(src) as source_zip:
                infos = [info for info in source_zip.infolist() if not info.is_dir()]
                if not infos:
                    raise DoomDeckError(f"Project Brutality archive has no files: {src}")
                prefix = common_zip_toplevel(info.filename for info in infos)
                with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as out_zip:
                    written = 0
                    for info in infos:
                        new_name = normalized_zip_member_name(info.filename, prefix)
                        if not new_name:
                            continue
                        out_info = zipfile.ZipInfo(new_name, date_time=info.date_time)
                        out_info.external_attr = info.external_attr
                        out_info.compress_type = zipfile.ZIP_DEFLATED
                        out_zip.writestr(out_info, source_zip.read(info))
                        written += 1
                    if written == 0:
                        raise DoomDeckError(f"Project Brutality archive had no safe file entries: {src}")
            tmp.replace(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    metadata = {
        "name": "Project Brutality",
        "installed": str(dest),
        "source_sha256": source_sha,
        **source,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    atomic_write_text(metadata_path, json.dumps(metadata, indent=2) + "\n", dry_run, logger)
    return dest


def select_project_brutality_download(logger: logging.Logger) -> GitHubAsset:
    try:
        release = github_request_json(f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise DoomDeckError(f"Could not read Project Brutality release metadata: {exc}") from exc
        release = {}
    tag_name = str(release.get("tag_name") or release.get("name") or "latest")
    assets = release.get("assets") or []

    def score(asset: dict[str, Any]) -> int:
        name = str(asset.get("name", ""))
        lower = name.lower()
        value = 0
        if lower.endswith(".pk3"):
            value += 120
        if lower.endswith(".zip"):
            value += 80
        if lower.endswith(".wad"):
            value += 60
        compact = lower.replace("_", "").replace("-", "")
        if "projectbrutality" in compact:
            value += 50
        if re.search(r"\bpb\b", lower):
            value += 20
        if any(token in lower for token in ["source", "src", "windows", ".exe", ".txt"]):
            value -= 50
        return value

    ranked = sorted(assets, key=score, reverse=True)
    if ranked and score(ranked[0]) > 0:
        chosen = ranked[0]
        logger.info("Selected Project Brutality release asset: %s", chosen.get("name"))
        return GitHubAsset(
            name=str(chosen["name"]),
            url=str(chosen["browser_download_url"]),
            size=chosen.get("size"),
            tag_name=tag_name,
        )

    zipball_url = release.get("zipball_url")
    if not zipball_url:
        repo_meta = github_request_json(f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}")
        default_branch = str(repo_meta.get("default_branch") or "master")
        tag_name = default_branch
        zipball_url = f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/zipball/{default_branch}"
    fallback_name = f"Project_Brutality-{safe_download_name(tag_name, 'latest')}.zip"
    logger.info("Using Project Brutality source zipball: %s", tag_name)
    return GitHubAsset(name=fallback_name, url=str(zipball_url), size=None, tag_name=tag_name)


def resolve_project_brutality(args: argparse.Namespace, dirs: Dirs, dry_run: bool, logger: logging.Logger) -> Optional[Path]:
    canonical = dirs.project_brutality / PROJECT_BRUTALITY_ALIAS
    metadata_path = dirs.project_brutality / "project-brutality.json"
    if args.project_brutality_file:
        src = expand_path(args.project_brutality_file)
        if not src.exists():
            raise DoomDeckError(f"--project-brutality-file does not exist: {src}")
        if src.suffix.lower() not in {".pk3", ".wad", ".zip"}:
            raise DoomDeckError(f"Project Brutality file should be a .pk3/.wad/.zip, got: {src}")
        return write_mod_zip_as_pk3(
            src,
            canonical,
            dirs.backups,
            metadata_path,
            dry_run,
            logger,
            {"source_type": "local_file", "source_path": str(src)},
            force=True,
        )

    if args.skip_project_brutality:
        if canonical.exists():
            logger.info("Skipping Project Brutality download; using existing %s", canonical)
            return canonical
        logger.info("Skipping Project Brutality download")
        return None

    if args.skip_downloads and not args.project_brutality_url:
        if canonical.exists():
            logger.info("Skipping downloads; using existing Project Brutality file %s", canonical)
            return canonical
        logger.warning("Skipping downloads and Project Brutality is not installed: %s", canonical)
        return None

    if args.project_brutality_url:
        url = args.project_brutality_url
        asset_name = safe_download_name(url, "Project_Brutality.zip")
        tag_name = "explicit-url"
    else:
        asset = select_project_brutality_download(logger)
        url = asset.url
        asset_name = safe_download_name(asset.name, "Project_Brutality.zip")
        tag_name = asset.tag_name
    downloaded = download_url(url, dirs.downloads / asset_name, dry_run, logger, force=args.force_download)
    return write_mod_zip_as_pk3(
        downloaded,
        canonical,
        dirs.backups,
        metadata_path,
        dry_run,
        logger,
        {"source_type": "github", "source_url": url, "source_tag": tag_name},
        force=args.force_download,
    )


def line_after_label(lines: list[str], label: str) -> str:
    label_lower = label.lower()
    for idx, line in enumerate(lines):
        normalized = line.rstrip(":").strip().lower()
        if normalized != label_lower:
            continue
        for candidate in lines[idx + 1 : idx + 4]:
            if candidate.rstrip(":").strip().lower() != label_lower:
                return candidate.strip()
    return ""


def extract_moddb_download_link(page_html: str, page_url: str) -> str:
    for href, text in html_links(page_html):
        if "/downloads/start/" in href and "download" in text.lower():
            return absolute_moddb_url(href, page_url)
    for href, _text in html_links(page_html):
        if "/downloads/start/" in href:
            return absolute_moddb_url(href, page_url)
    match = re.search(r"""(?i)href\s*=\s*["'](?P<href>[^"']*/downloads/start/\d+[^"']*)["']""", page_html)
    if match:
        return absolute_moddb_url(match.group("href"), page_url)
    raise DoomDeckError(f"Could not find a ModDB start-download link on {page_url}")


def resolve_moddb_download_url(start_url: str, page_url: str, logger: logging.Logger) -> str:
    def first_mirror(html_text: str, base_url: str) -> Optional[str]:
        for href, _text in html_links(html_text):
            if "/downloads/mirror/" in href:
                return absolute_moddb_url(href, base_url)
        return None

    try:
        start_html = fetch_text_url(start_url, logger)
    except urllib.error.URLError as exc:
        raise DoomDeckError(f"Could not read ModDB download page {start_url}: {exc}") from exc

    mirror = first_mirror(start_html, start_url)
    if mirror:
        return mirror

    mirrors_url = start_url.rstrip("/") + "/all"
    try:
        mirrors_html = fetch_text_url(mirrors_url, logger)
    except urllib.error.URLError as exc:
        logger.warning("Could not read ModDB mirror list %s: %s", mirrors_url, exc)
        return start_url
    mirror = first_mirror(mirrors_html, mirrors_url)
    if mirror:
        return mirror
    logger.warning("No explicit ModDB mirror found; using start URL directly: %s", start_url)
    return start_url


def extract_brutal_doom_pages(page_html: str, base_url: str) -> list[tuple[str, str]]:
    pages: OrderedDict[str, str] = OrderedDict()

    def title_quality(value: str) -> int:
        lower = value.lower()
        if "brutal doom" in lower:
            return 100
        if re.search(r"\bbd\s*v?\d+", lower):
            return 80
        if "comments" in lower or lower.startswith("image:"):
            return 0
        return 10 if value else 0

    for href, text in html_links(page_html):
        url = absolute_moddb_url(href, base_url)
        parsed = urllib.parse.urlparse(url)
        if not parsed.path.startswith("/mods/brutal-doom/downloads/"):
            continue
        title = text.strip()
        if not title:
            title = parsed.path.rstrip("/").split("/")[-1].replace("-", " ").title()
        if url not in pages or title_quality(title) > title_quality(pages[url]):
            pages[url] = title
    return [(title, url) for url, title in pages.items()]


def brutal_doom_candidate_score(title: str, url: str, channel: str, index: int) -> int:
    slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    lower = f"{title} {slug}".lower()
    title_compact = re.sub(r"[^a-z0-9]+", "", title.lower())
    slug_compact = re.sub(r"[^a-z0-9]+", "", slug.lower())
    if "brutaldoom" not in title_compact and "brutaldoomv" not in slug_compact and not re.search(r"\bbd\s*v?\d+", title.lower()):
        return -1000
    rejected = [
        "platinum",
        "kickass",
        "monsters only",
        "monster only",
        "metal soundtrack",
        "soundtrack",
        "eday",
        "extermination day",
        "bolognese",
        "meatgrinder",
        "black edition",
        "addon",
        "launcher",
    ]
    if any(token in lower for token in rejected):
        return -1000
    score = 100 - index
    versions: list[int] = []
    for value in re.findall(r"\bv\s*(\d+)", lower):
        # ModDB slugs sometimes collapse dots, e.g. v21.50.0 -> v21500.
        major_text = value[:2] if len(value) >= 4 else value
        versions.append(int(major_text))
    if versions:
        score += max(versions) * 10
    is_test = any(token in lower for token in ["beta", "test", "demo"])
    if channel == "stable":
        score += 100 if not is_test else -200
    else:
        score += 30 if is_test else 0
    if "full version" in lower:
        score += 20
    return score


def select_brutal_doom_download(channel: str, logger: logging.Logger) -> ModDBDownload:
    pages: list[tuple[str, str]] = []
    errors: list[str] = []
    for source_url in [BRUTAL_DOOM_MODDB_URL, BRUTAL_DOOM_DOWNLOADS_URL]:
        try:
            pages.extend(extract_brutal_doom_pages(fetch_text_url(source_url, logger), source_url))
        except urllib.error.URLError as exc:
            errors.append(f"{source_url}: {exc}")

    seen: set[str] = set()
    unique_pages: list[tuple[str, str]] = []
    for title, url in pages:
        if url in seen:
            continue
        seen.add(url)
        unique_pages.append((title, url))
    if not unique_pages:
        detail = "; ".join(errors) if errors else "no matching download links found"
        raise DoomDeckError(f"Could not discover Brutal Doom downloads on ModDB: {detail}")

    ranked = sorted(
        enumerate(unique_pages),
        key=lambda item: brutal_doom_candidate_score(item[1][0], item[1][1], channel, item[0]),
        reverse=True,
    )
    for index, (title, page_url) in ranked:
        if brutal_doom_candidate_score(title, page_url, channel, index) <= 0:
            continue
        logger.info("Selected Brutal Doom ModDB page: %s", title)
        try:
            page_html = fetch_text_url(page_url, logger)
        except urllib.error.URLError as exc:
            logger.warning("Could not read Brutal Doom page %s: %s", page_url, exc)
            continue
        lines = html_text_lines(page_html)
        filename = line_after_label(lines, "Filename") or safe_download_name(page_url, "brutal-doom.zip")
        updated = line_after_label(lines, "Updated")
        md5 = line_after_label(lines, "MD5 Hash")
        start_url = extract_moddb_download_link(page_html, page_url)
        return ModDBDownload(
            title=title,
            page_url=page_url,
            filename=safe_download_name(filename, "brutal-doom.zip"),
            download_url=resolve_moddb_download_url(start_url, page_url, logger),
            updated=updated,
            md5=md5,
        )

    raise DoomDeckError(f"Could not find a suitable Brutal Doom ModDB download for channel '{channel}'")


def choose_payload_member(infos: list[zipfile.ZipInfo]) -> Optional[zipfile.ZipInfo]:
    payloads = [info for info in infos if Path(info.filename).suffix.lower() in {".pk3", ".wad"}]
    if not payloads:
        return None

    def score(info: zipfile.ZipInfo) -> int:
        name = info.filename.replace("\\", "/").split("/")[-1].lower()
        value = 0
        if name.endswith(".pk3"):
            value += 100
        if name.endswith(".wad"):
            value += 60
        if "brutal" in name:
            value += 50
        if "bd" in name:
            value += 10
        if any(token in name for token in ["readme", "manual", "credits", "optional", "extras"]):
            value -= 100
        return value

    return sorted(payloads, key=score, reverse=True)[0]


def install_brutal_doom_archive(
    src: Path,
    dest: Path,
    backups_dir: Path,
    metadata_path: Path,
    dry_run: bool,
    logger: logging.Logger,
    source: dict[str, str],
    force: bool = False,
) -> Path:
    if not src.exists() and not dry_run:
        raise DoomDeckError(f"Brutal Doom download is missing: {src}")
    source_sha = sha256_file(src) if src.exists() else ""
    if dest.exists() and metadata_path.exists() and not force:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
        if metadata.get("source_sha256") == source_sha:
            logger.info("Brutal Doom already current: %s", dest)
            return dest

    logger.info("Install Brutal Doom archive: %s -> %s", src, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        backup_path(dest, backups_dir, dry_run, logger, label=dest.name)

    payload_member = ""
    if src.suffix.lower() in {".pk3", ".wad"}:
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(src, tmp)
        tmp.replace(dest)
    elif zipfile.is_zipfile(src):
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            with zipfile.ZipFile(src) as source_zip:
                infos = [info for info in source_zip.infolist() if not info.is_dir()]
                chosen = choose_payload_member(infos)
                if chosen:
                    payload_member = chosen.filename
                    with source_zip.open(chosen) as source_handle, tmp.open("wb") as dest_handle:
                        shutil.copyfileobj(source_handle, dest_handle)
                elif zip_contains_markers(src, {"gameinfo.txt"}):
                    shutil.copy2(src, tmp)
                else:
                    raise DoomDeckError(f"Brutal Doom archive has no .pk3/.wad payload: {src}")
            tmp.replace(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    else:
        raise DoomDeckError(f"Brutal Doom file should be a .pk3/.wad/.zip, got: {src}")

    metadata = {
        "name": "Brutal Doom",
        "installed": str(dest),
        "installed_sha256": sha256_file(dest),
        "payload_member": payload_member,
        "source_sha256": source_sha,
        **source,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    atomic_write_text(metadata_path, json.dumps(metadata, indent=2) + "\n", dry_run, logger)
    return dest


def write_wrappers(dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    doomrunner_appimage = dirs.doomrunner / "DoomRunner.AppImage"
    doomrunner_wrapper = dirs.launchers / "doom-runner.sh"
    uzdoom_appimage = dirs.uzdoom / "uzdoom.AppImage"
    uzdoom_wrapper = dirs.uzdoom / "uzdoom.sh"

    common_shell = """# This wrapper is generated by doomdeck.
# It keeps config/data inside the managed Doom tree when possible.
"""

    doomrunner_content = f"""#!/usr/bin/env bash
{common_shell}set -euo pipefail
ROOT={shell_quote(str(dirs.root))}
APPIMAGE={shell_quote(str(doomrunner_appimage))}
export XDG_CONFIG_HOME="$ROOT/configs/xdg-config"
export XDG_DATA_HOME="$ROOT/configs/xdg-data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
if [[ ! -x "$APPIMAGE" ]]; then
  echo "Doom Runner AppImage is missing or not executable: $APPIMAGE" >&2
  exit 1
fi
if [[ ! -e /dev/fuse ]]; then
  export APPIMAGE_EXTRACT_AND_RUN=1
fi
exec "$APPIMAGE" "$@"
"""
    uzdoom_content = f"""#!/usr/bin/env bash
{common_shell}set -euo pipefail
ROOT={shell_quote(str(dirs.root))}
APPIMAGE={shell_quote(str(uzdoom_appimage))}
export XDG_CONFIG_HOME="$ROOT/configs/xdg-config"
export XDG_DATA_HOME="$ROOT/configs/xdg-data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
if [[ ! -x "$APPIMAGE" ]]; then
  echo "UZDoom AppImage is missing or not executable: $APPIMAGE" >&2
  exit 1
fi
if [[ ! -e /dev/fuse ]]; then
  export APPIMAGE_EXTRACT_AND_RUN=1
fi
exec "$APPIMAGE" "$@"
"""
    atomic_write_text(doomrunner_wrapper, doomrunner_content, dry_run, logger, mode=0o755)
    atomic_write_text(uzdoom_wrapper, uzdoom_content, dry_run, logger, mode=0o755)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def build_uzdoom_ini() -> str:
    lines = ["; Generated by doomdeck", "[GlobalSettings]"]
    lines.extend(f"{key}={value}" for key, value in UZDOOM_STEAM_DECK_GLOBAL_SETTINGS)
    lines.append("")
    return "\n".join(lines)


def build_uzdoom_deck_autoexec_settings() -> str:
    return "\n".join(f"{key} {value}" for key, value in UZDOOM_STEAM_DECK_GLOBAL_SETTINGS)


def write_uzdoom_configs(dirs: Dirs, dry_run: bool, logger: logging.Logger) -> None:
    deck_settings = build_uzdoom_deck_autoexec_settings()
    classic_cfg = f"""// Generated by doomdeck
// Classic-style Doom behavior for UZDoom/GZDoom-family source ports.
// Steam Deck display, graphics, and gamepad defaults.

{deck_settings}

freelook false
lookstrafe false
m_pitch 0
sv_allowjump false
sv_allowcrouch false
cl_run true
crosshair 0

alias +deck_use_select "+use; menu_select"
alias -deck_use_select "-use"

bind w +forward
bind s +back
bind a +moveleft
bind d +moveright
bind leftarrow +left
bind rightarrow +right
bind mouse1 +attack
bind e +use
bind space +use
bind tab +showscores
bind escape menu_main
bind enter menu_select
bind backspace menu_back
bind Pad_A +deck_use_select
bind Pad_B menu_back
bind Pad_Start menu_main
bind Pad_Back pause
bind RTrigger +attack
bind LShoulder weapprev
bind RShoulder weapnext
bind mwheelup weapnext
bind mwheeldown weapprev
bind 1 slot 1
bind 2 slot 2
bind 3 slot 3
bind 4 slot 4
bind 5 slot 5
bind 6 slot 6
bind 7 slot 7
"""
    modern_cfg = f"""// Generated by doomdeck
// Modern dual-stick/FPS-style behavior for UZDoom and Brutal Doom.
// Steam Deck display, graphics, and gamepad defaults.

{deck_settings}

freelook true
lookstrafe false
m_pitch 1
sv_allowjump true
sv_allowcrouch true
cl_run true
crosshair 1

alias +deck_use_select "+use; menu_select"
alias -deck_use_select "-use"
alias +deck_crouch_back "+crouch; menu_back"
alias -deck_crouch_back "-crouch"

bind w +forward
bind s +back
bind a +moveleft
bind d +moveright
bind mouse1 +attack
bind mouse2 +altattack
bind e +use
bind space +jump
bind leftctrl +crouch
bind c +crouch
bind r +reload
bind q weapprev
bind mwheelup weapnext
bind mwheeldown weapprev
bind f +zoom
bind tab +showscores
bind escape menu_main
bind enter menu_select
bind backspace menu_back
bind Pad_A +deck_use_select
bind Pad_B +deck_crouch_back
bind Pad_X +reload
bind Pad_Y +jump
bind Pad_Start menu_main
bind Pad_Back pause
bind RTrigger +attack
bind LTrigger +altattack
bind LShoulder weapprev
bind RShoulder weapnext
bind 1 slot 1
bind 2 slot 2
bind 3 slot 3
bind 4 slot 4
bind 5 slot 5
bind 6 slot 6
bind 7 slot 7
"""
    classic_ini = build_uzdoom_ini()
    modern_ini = build_uzdoom_ini()
    atomic_write_text(dirs.uzdoom_config / "classic" / "autoexec.cfg", classic_cfg, dry_run, logger)
    atomic_write_text(dirs.uzdoom_config / "modern" / "autoexec.cfg", modern_cfg, dry_run, logger)
    atomic_write_text(dirs.uzdoom_config / "classic" / "uzdoom.ini", classic_ini, dry_run, logger)
    atomic_write_text(dirs.uzdoom_config / "modern" / "uzdoom.ini", modern_ini, dry_run, logger)


def resolve_brutal_doom(args: argparse.Namespace, dirs: Dirs, dry_run: bool, logger: logging.Logger) -> Optional[Path]:
    canonical = dirs.brutal / BRUTAL_DOOM_ALIAS
    metadata_path = dirs.brutal / "brutal-doom.json"

    def alias_existing_candidate() -> Optional[Path]:
        candidates = sorted(
            [
                p
                for p in dirs.brutal.glob("*")
                if p.is_file() and p.resolve() != canonical.resolve() and p.suffix.lower() in {".pk3", ".wad", ".zip"}
            ],
            key=lambda p: ("brutal" in p.name.lower(), p.stat().st_mtime),
            reverse=True,
        )
        if not candidates:
            return None
        install_brutal_doom_archive(
            candidates[0],
            canonical,
            dirs.backups,
            metadata_path,
            dry_run,
            logger,
            {"source_type": "local_existing", "source_path": str(candidates[0])},
            force=False,
        )
        return canonical

    if args.brutal_doom_file:
        src = expand_path(args.brutal_doom_file)
        if not src.exists():
            raise DoomDeckError(f"--brutal-doom-file does not exist: {src}")
        if src.suffix.lower() not in {".pk3", ".wad", ".zip"}:
            raise DoomDeckError(f"Brutal Doom file should be a .pk3/.wad/.zip, got: {src}")
        return install_brutal_doom_archive(
            src,
            canonical,
            dirs.backups,
            metadata_path,
            dry_run,
            logger,
            {"source_type": "local_file", "source_path": str(src)},
            force=True,
        )

    if args.skip_brutal_doom:
        if canonical.exists():
            logger.info("Skipping Brutal Doom update; using existing %s", canonical)
            return canonical
        logger.info("Skipping Brutal Doom update")
        return None

    if args.skip_downloads and not args.brutal_doom_url:
        if canonical.exists():
            logger.info("Skipping downloads; using existing Brutal Doom file %s", canonical)
            return canonical
        candidate = alias_existing_candidate()
        if candidate:
            logger.info("Skipping downloads; aliased existing Brutal Doom file %s", candidate)
            return candidate
        logger.warning("Skipping downloads and Brutal Doom is not installed: %s", canonical)
        return None

    if args.brutal_doom_url:
        url = args.brutal_doom_url
        asset_name = safe_download_name(url, "brutal-doom.zip")
        source = {
            "source_type": "explicit_url",
            "source_url": url,
            "source_filename": asset_name,
        }
        downloaded = download_url(url, dirs.downloads / asset_name, dry_run, logger, force=args.force_download)
        return install_brutal_doom_archive(downloaded, canonical, dirs.backups, metadata_path, dry_run, logger, source, force=args.force_download)

    try:
        selected = select_brutal_doom_download(args.brutal_doom_channel, logger)
    except DoomDeckError as exc:
        if canonical.exists():
            logger.warning("Could not check Brutal Doom updates automatically; using existing alias: %s", exc)
            return canonical
        logger.warning("Could not install Brutal Doom automatically: %s", exc)
        return None

    source = {
        "source_type": "moddb",
        "source_channel": args.brutal_doom_channel,
        "source_title": selected.title,
        "source_page_url": selected.page_url,
        "source_filename": selected.filename,
        "source_updated": selected.updated,
        "source_md5": selected.md5,
    }
    compare_keys = ["source_type", "source_channel", "source_page_url", "source_filename", "source_updated", "source_md5"]
    already_current = canonical.exists() and metadata_matches(metadata_path, source, compare_keys)
    if already_current and not args.force_download:
        logger.info("Brutal Doom already current from ModDB: %s", canonical)
        return canonical

    download_dest = dirs.downloads / selected.filename
    downloaded = download_url(
        selected.download_url,
        download_dest,
        dry_run,
        logger,
        force=args.force_download or not already_current,
        headers={"Referer": selected.page_url},
    )
    return install_brutal_doom_archive(
        downloaded,
        canonical,
        dirs.backups,
        metadata_path,
        dry_run,
        logger,
        {**source, "source_download_url": selected.download_url},
        force=args.force_download or not already_current,
    )


def create_or_replace_symlink_or_copy(src: Path, dest: Path, dry_run: bool, logger: logging.Logger) -> None:
    if dest.exists() or dest.is_symlink():
        try:
            if dest.is_symlink() and dest.resolve() == src.resolve():
                logger.info("Symlink already current: %s -> %s", dest, src)
                return
        except FileNotFoundError:
            pass
        logger.info("Replace existing alias: %s", dest)
        if not dry_run:
            dest.unlink()
    logger.info("Create symlink: %s -> %s", dest, src)
    if dry_run:
        return
    try:
        dest.symlink_to(src)
    except OSError:
        shutil.copy2(src, dest)


def launcher_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def iwad_dest_name(iwad_lower_name: str) -> str:
    return iwad_lower_name.upper()


def choose_default_preset_iwad(dirs: Dirs) -> Optional[Path]:
    for iwad_name in DEFAULT_PRESET_IWADS:
        iwad_path = dirs.iwads / iwad_dest_name(iwad_name)
        if iwad_path.exists():
            return iwad_path
    return None


def generate_preset_manifest(dirs: Dirs, brutal_path: Optional[Path], project_brutality_path: Optional[Path]) -> dict[str, Any]:
    presets: list[dict[str, Any]] = []
    default_iwad = choose_default_preset_iwad(dirs)
    if default_iwad:
        presets.extend(
            [
                {
                    "name": "Vanilla Doom",
                    "category": "Vanilla",
                    "engine": "UZDoom",
                    "iwad": str(default_iwad),
                    "files": [],
                    "config": str(dirs.uzdoom_config / "classic" / "uzdoom.ini"),
                    "autoexec": str(dirs.uzdoom_config / "classic" / "autoexec.cfg"),
                    "launcher": str(dirs.launchers / "Vanilla_Doom.sh"),
                    "notes": "Classic-style UZDoom launch. Change the selected IWAD in Doom Runner to switch Doom, Doom II, TNT, or Plutonia.",
                },
                {
                    "name": "UZDoom",
                    "category": "UZDoom",
                    "engine": "UZDoom",
                    "iwad": str(default_iwad),
                    "files": [],
                    "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                    "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
                    "launcher": str(dirs.launchers / "UZDoom.sh"),
                    "notes": "UZDoom without gameplay mods. Change the selected IWAD in Doom Runner to switch base games.",
                },
                {
                    "name": "Brutal Doom",
                    "category": "Brutal Doom",
                    "engine": "UZDoom",
                    "iwad": str(default_iwad),
                    "files": [str(brutal_path or (dirs.brutal / BRUTAL_DOOM_ALIAS))],
                    "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                    "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
                    "launcher": str(dirs.launchers / "Brutal_Doom.sh"),
                    "missing_hint": "Rerun install to check ModDB, or use --brutal-doom-file/--brutal-doom-url.",
                    "notes": f"Requires mods/brutal-doom/{BRUTAL_DOOM_ALIAS}. Change the selected IWAD in Doom Runner to switch base games.",
                },
                {
                    "name": "Project Brutality",
                    "category": "Project Brutality",
                    "engine": "UZDoom",
                    "iwad": str(default_iwad),
                    "files": [str(project_brutality_path or (dirs.project_brutality / PROJECT_BRUTALITY_ALIAS))],
                    "config": str(dirs.uzdoom_config / "modern" / "uzdoom.ini"),
                    "autoexec": str(dirs.uzdoom_config / "modern" / "autoexec.cfg"),
                    "launcher": str(dirs.launchers / "Project_Brutality.sh"),
                    "missing_hint": "Rerun install to download Project Brutality, or use --project-brutality-file /path/to/Project_Brutality.pk3.",
                    "notes": "Downloads Project Brutality from GitHub and installs it as mods/project-brutality/project-brutality.pk3.",
                },
            ]
        )
    return {
        "schema": "doom-deck-setup/preset-manifest/v1",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "warning": "This is a stable manifest generated by DoomDeck. Doom Runner's live options.json is generated separately.",
        "root": str(dirs.root),
        "engine": {
            "name": "UZDoom",
            "executable": str(dirs.uzdoom / "uzdoom.sh"),
            "family": "UZDoom/ZDoom",
            "config_directory": str(dirs.uzdoom_config),
            "data_directory": str(dirs.root),
        },
        "iwad_directory": str(dirs.iwads),
        "pwad_directory": str(dirs.pwads),
        "mod_directories": {
            "brutal_doom": str(dirs.brutal),
            "project_brutality": str(dirs.project_brutality),
        },
        "presets": presets,
    }


def is_generated_preset_launcher(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return (
        "UZDOOM=" in text
        and "IWAD=" in text
        and 'exec "$UZDOOM" -noautoload -iwad "$IWAD"' in text
    )


def remove_stale_generated_launchers(dirs: Dirs, keep_launchers: set[Path], dry_run: bool, logger: logging.Logger) -> None:
    keep = {path.resolve() for path in keep_launchers if path.exists()}
    keep.add((dirs.launchers / "doom-runner.sh").resolve())
    for script in sorted(dirs.launchers.glob("*.sh")):
        try:
            resolved = script.resolve()
        except FileNotFoundError:
            continue
        if resolved in keep or not is_generated_preset_launcher(script):
            continue
        backup_path(script, dirs.backups, dry_run, logger, label=script.name)
        logger.info("Remove stale generated launcher: %s", script)
        if not dry_run:
            script.unlink()


def write_launchers_and_manifest(
    dirs: Dirs,
    brutal_path: Optional[Path],
    project_brutality_path: Optional[Path],
    dry_run: bool,
    logger: logging.Logger,
) -> dict[str, Any]:
    manifest = generate_preset_manifest(dirs, brutal_path, project_brutality_path)
    uzdoom = dirs.uzdoom / "uzdoom.sh"
    written_launchers: set[Path] = set()
    for preset in manifest["presets"]:
        launcher = Path(preset["launcher"])
        written_launchers.add(launcher)
        iwad = Path(preset["iwad"])
        config = Path(preset["config"])
        autoexec = Path(preset["autoexec"])
        files = [Path(p) for p in preset.get("files", [])]
        file_args = ""
        missing_guard = ""
        if files:
            missing_hint = str(preset.get("missing_hint", "Install the required mod file, then rerun this launcher."))
            for idx, file_path in enumerate(files):
                missing_guard += f"if [[ ! -f {shell_quote(str(file_path))} ]]; then\n"
                missing_guard += f"  echo 'Missing required mod file: {file_path}' >&2\n"
                missing_guard += f"  echo {shell_quote(missing_hint)} >&2\n"
                missing_guard += "  exit 2\nfi\n"
            quoted = " ".join(shell_quote(str(p)) for p in files)
            file_args = f" -file {quoted}"
        content = f"""#!/usr/bin/env bash
set -euo pipefail
UZDOOM={shell_quote(str(uzdoom))}
IWAD={shell_quote(str(iwad))}
CONFIG={shell_quote(str(config))}
AUTOEXEC={shell_quote(str(autoexec))}
if [[ ! -x "$UZDOOM" ]]; then
  echo "UZDoom wrapper is missing or not executable: $UZDOOM" >&2
  exit 1
fi
if [[ ! -f "$IWAD" ]]; then
  echo "Missing IWAD: $IWAD" >&2
  exit 1
fi
{missing_guard}exec "$UZDOOM" -noautoload -iwad "$IWAD" -config "$CONFIG" +exec "$AUTOEXEC"{file_args} "$@"
"""
        atomic_write_text(launcher, content, dry_run, logger, mode=0o755)

    remove_stale_generated_launchers(dirs, written_launchers, dry_run, logger)
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n", dry_run, logger)
    return manifest


def doomrunner_options_paths(dirs: Dirs) -> list[Path]:
    # Doom Runner stores options in QStandardPaths::AppDataLocation on Linux,
    # which honors XDG_DATA_HOME. The config mirror covers older/future builds
    # that may use XDG_CONFIG_HOME instead.
    return [
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
            entries.append({"name": display_name, "path": str(iwad_path)})
    return entries


def choose_doomrunner_default_iwad(iwad_entries: list[dict[str, str]], dirs: Dirs) -> str:
    preferred = dirs.iwads / "DOOM2.WAD"
    for entry in iwad_entries:
        if entry["path"] == str(preferred):
            return entry["path"]
    return iwad_entries[0]["path"] if iwad_entries else ""


def build_doomrunner_preset(dirs: Dirs, preset: dict[str, Any]) -> dict[str, Any]:
    name = str(preset["name"])
    slug = launcher_slug(name).lower()
    config = Path(preset["config"])
    autoexec = Path(preset["autoexec"])
    save_dir = dirs.saves / slug
    screenshot_dir = dirs.screenshots / slug
    mods = [{"path": str(path), "checked": True} for path in preset.get("files", [])]
    additional_args = (
        f"-noautoload -config {doomrunner_quote_arg(config)} "
        f"-savedir {doomrunner_quote_arg(save_dir)} +exec {doomrunner_quote_arg(autoexec)}"
    )
    return {
        "name": name,
        "selected_engine": DOOMRUNNER_ENGINE_ID,
        "selected_config": "",
        "selected_IWAD": str(preset["iwad"]),
        "selected_mappacks": [],
        "mods": mods,
        "load_maps_after_mods": False,
        "alternative_paths": {
            "config_dir": str(config.parent),
            "save_dir": str(save_dir),
            "demo_dir": "",
            "screenshot_dir": str(screenshot_dir),
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


def build_doomrunner_options(dirs: Dirs, manifest: dict[str, Any]) -> dict[str, Any]:
    iwad_entries = build_doomrunner_iwad_entries(dirs)
    presets = [build_doomrunner_preset(dirs, preset) for preset in manifest.get("presets", [])]
    return {
        "version": DOOMRUNNER_OPTIONS_VERSION,
        "engines": {
            "default_engine": DOOMRUNNER_ENGINE_ID,
            "engine_list": [
                {
                    "id": DOOMRUNNER_ENGINE_ID,
                    "name": DOOMRUNNER_ENGINE_NAME,
                    "path": str(dirs.uzdoom / "uzdoom.sh"),
                    "config_dir": str(dirs.uzdoom_config),
                    "data_dir": str(dirs.root),
                    "family": "ZDoom",
                }
            ],
        },
        "IWADs": {
            "auto_update": False,
            "directory": str(dirs.iwads),
            "search_subdirs": False,
            "default_iwad": choose_doomrunner_default_iwad(iwad_entries, dirs),
            "IWAD_list": iwad_entries,
        },
        "maps": {
            "directory": str(dirs.pwads),
            "sort_column": 0,
            "sort_order": 0,
            "show_icons": False,
        },
        "mods": {
            "last_used_dir": str(dirs.mods),
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


def write_doomrunner_live_config(dirs: Dirs, manifest: dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> None:
    if getattr(args, "skip_doomrunner_live_config", False):
        logger.info("Skipping Doom Runner live options.json generation")
        return
    if is_process_running(["DoomRunner.AppImage", "DoomRunner ", "doom-runner.sh"]):
        raise DoomDeckError("Doom Runner appears to be running. Close it before rewriting options.json.")

    options = build_doomrunner_options(dirs, manifest)
    content = json.dumps(options, indent=4) + "\n"
    for preset in options["presets"]:
        for key in ["save_dir", "screenshot_dir"]:
            path_text = preset.get("alternative_paths", {}).get(key, "")
            if path_text:
                ensure_dir(Path(path_text), args.dry_run, logger)

    for options_path in doomrunner_options_paths(dirs):
        if options_path.exists():
            try:
                current = options_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                current = ""
            if current == content:
                logger.info("Doom Runner live config already current: %s", options_path)
                continue
            label = f"doomrunner-options-{options_path.parent.parent.name}.json"
            backup_path(options_path, dirs.backups, args.dry_run, logger, label=label)
        atomic_write_text(options_path, content, args.dry_run, logger)


def write_docs(
    dirs: Dirs,
    manifest: dict[str, Any],
    brutal_path: Optional[Path],
    project_brutality_path: Optional[Path],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    layout = f"""# Doom Deck Setup Layout

Generated by `doomdeck`.

```text
{dirs.root}/
├── tools/doomrunner/              Doom Runner AppImage
├── source-ports/uzdoom/           UZDoom AppImage and wrapper
├── iwads/                         Legal IWAD copies from Steam app {APPID_DOOM_PLUS_DOOM_II}
├── pwads/                         User PWADs and map packs
├── mods/brutal-doom/              Managed Brutal Doom .pk3 and update metadata
├── mods/project-brutality/         Downloaded Project Brutality .pk3
├── configs/doomrunner/            Generated manifest and Doom Runner setup guide
├── configs/uzdoom/                Classic and modern UZDoom config templates
├── launchers/                     Direct generated preset shell launchers
├── saves/                         Save-game location for future use
├── screenshots/                   Screenshot location for future use
├── downloads/                     Downloaded upstream release assets
├── backups/                       Backups made before replacement/modification
└── logs/                          Script logs
```
"""
    steam_input = f"""# Steam Input Profiles for Doom Runner / UZDoom

The generated UZDoom configs enable joystick input and bind common Steam Deck gamepad buttons directly. Steam's standard Gamepad layout should work for the generated presets; use Steam's controller configurator only if you want a custom layout.

The generated UZDoom configs also default to fullscreen {STEAM_DECK_WIDTH}x{STEAM_DECK_HEIGHT}, vsync on, and a {STEAM_DECK_TARGET_FPS} FPS cap.

## Classic Doom controls

Recommended Steam Deck layout for the `Vanilla Doom` preset:

- Left stick: movement.
- Right stick or right trackpad: horizontal turn only, low-to-moderate sensitivity.
- Right trigger: attack.
- A: use in-game and select in menus.
- B: back in menus.
- Left/right bumpers: weapon cycling.
- Menu/Start: open menu.
- Disable gyro and vertical mouse if you want a stricter classic feel.

The generated `configs/uzdoom/classic/autoexec.cfg` sets `freelook false`, `sv_allowjump false`, and `sv_allowcrouch false`.

## Modern Doom / Brutal Doom controls

Recommended Steam Deck layout for the `UZDoom` and `Brutal Doom` presets:

- Left stick: movement.
- Right stick: mouse look or joystick look, conservative sensitivity.
- Right trigger: primary fire.
- Left trigger: secondary fire or alt-fire.
- A: use in-game and select in menus.
- B: crouch in-game and back in menus.
- X: reload.
- Y: jump.
- Bumpers: weapon cycle.
- Menu/Start: open menu.
- Optional gyro: mouse as gyro, active on right-stick touch or left trigger.

The generated `configs/uzdoom/modern/autoexec.cfg` enables freelook, jump, crouch, reload, and alt-fire bindings.
"""
    live_options_primary = doomrunner_options_paths(dirs)[0]
    doomrunner_guide = f"""# Doom Runner Setup Guide

DoomDeck installs Doom Runner and UZDoom, copies Steam IWADs, creates direct shell launchers, writes Doom Runner's live options file, and writes a stable preset manifest:

`{live_options_primary}`

`{dirs.doomrunner_config / 'preset-manifest.json'}`

Doom Runner should open with the generated UZDoom engine, IWADs, and presets already listed. Existing live Doom Runner options are backed up under:

`{dirs.backups}`

## Initial Doom Runner check

1. Launch `Doom Runner` from Steam Gaming Mode or run:

   ```bash
   {dirs.launchers / 'doom-runner.sh'}
   ```

2. Confirm this engine exists:

   - Engine name: `UZDoom`
   - Executable path: `{dirs.uzdoom / 'uzdoom.sh'}`
   - Engine family: `UZDoom` if shown, otherwise `ZDoom` / `GZDoom-family`
   - Config directory: `{dirs.uzdoom_config}`
   - Data directory: `{dirs.root}`

3. Confirm IWADs are listed from:

   `{dirs.iwads}`

4. Confirm these presets are listed:

"""
    for preset in manifest.get("presets", []):
        files = ", ".join(preset.get("files") or []) or "none"
        doomrunner_guide += f"- `{preset['name']}`\n  - IWAD: `{preset['iwad']}`\n  - Config: `{preset['config']}`\n  - Autoexec: `{preset['autoexec']}`\n  - Files/mods: `{files}`\n"
    doomrunner_guide += """
## Direct launchers

The scripts in `launchers/` can be added to Steam individually if you later decide you want one-click launches for each preset instead of launching Doom Runner first.
"""
    brutal = f"""# Brutal Doom

Brutal Doom is checked from the official ModDB project/download pages when you rerun:

```bash
doomdeck install
```

The default update channel is `latest`, which can include beta/test builds such as v22 test releases. To prefer the newest non-beta candidate DoomDeck can identify, use:

```bash
doomdeck install --brutal-doom-channel stable
```

Managed file:

`{brutal_path or 'not found yet'}`

Metadata:

`{dirs.brutal / 'brutal-doom.json'}`

To use a specific browser-downloaded file instead:

```bash
doomdeck install --brutal-doom-file /path/to/brutal-doom.pk3
```

To skip Brutal Doom update checks:

```bash
doomdeck install --skip-brutal-doom
```

Source project:

`{BRUTAL_DOOM_MODDB_URL}`
"""
    project_brutality = f"""# Project Brutality

Project Brutality is checked from GitHub and installed as a root-normalized `.pk3` for UZDoom/Doom Runner.

Managed file:

`{project_brutality_path or (dirs.project_brutality / PROJECT_BRUTALITY_ALIAS)}`

To update it, rerun:

```bash
doomdeck install
```

To use a manually downloaded file instead:

```bash
doomdeck install --project-brutality-file /path/to/Project_Brutality.pk3
```

Source repository:

`https://github.com/{PROJECT_BRUTALITY_REPO}`
"""
    atomic_write_text(dirs.docs / "DIRECTORY_LAYOUT.md", layout, dry_run, logger)
    atomic_write_text(dirs.docs / "STEAM_INPUT_PROFILES.md", steam_input, dry_run, logger)
    atomic_write_text(dirs.docs / "DOOM_RUNNER_SETUP.md", doomrunner_guide, dry_run, logger)
    atomic_write_text(dirs.brutal / "README.md", brutal, dry_run, logger)
    atomic_write_text(dirs.project_brutality / "README.md", project_brutality, dry_run, logger)


def is_process_running(patterns: list[str]) -> bool:
    try:
        result = subprocess.run(["pgrep", "-fa", "."], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    this_pid = os.getpid()
    for line in result.stdout.splitlines():
        if str(this_pid) in line:
            continue
        lowered = line.lower()
        if any(pattern.lower() in lowered for pattern in patterns):
            return True
    return False


def shutdown_steam(logger: logging.Logger, dry_run: bool) -> None:
    logger.info("Request Steam shutdown")
    if dry_run:
        return
    candidates = [["steam", "-shutdown"], ["steam-runtime", "-shutdown"]]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(8)
            return
    logger.warning("Steam command not found; close Steam manually before modifying shortcuts.vdf")


def steam_quote_path(path: Path) -> str:
    return f'"{path}"'


def generate_shortcut_appid(exe_value: str, appname: str) -> int:
    # Stable non-Steam shortcut appid. Steam stores this as int32 in shortcuts.vdf.
    unsigned = (zlib.crc32(f"{exe_value}{appname}".encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
    return unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned


def load_shortcuts(path: Path) -> OrderedDict[str, BKVValue]:
    if not path.exists():
        return OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict())})
    data = path.read_bytes()
    if not data:
        return OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict())})
    parsed = BinaryVDF.loads(data)
    if "shortcuts" not in parsed or parsed["shortcuts"].type_code != BKV_OBJECT:
        raise DoomDeckError("shortcuts.vdf does not contain a top-level shortcuts object")
    return parsed


def get_bkv_str(obj: OrderedDict[str, BKVValue], *names: str) -> str:
    lower_map = {key.lower(): key for key in obj.keys()}
    for name in names:
        key = name if name in obj else lower_map.get(name.lower())
        if key and obj[key].type_code == BKV_STRING:
            return str(obj[key].value)
    return ""


def make_shortcut_entry(appname: str, exe: Path, start_dir: Path, tags: list[str]) -> BKVValue:
    exe_value = steam_quote_path(exe)
    start_dir_value = steam_quote_path(start_dir)
    fields: OrderedDict[str, BKVValue] = OrderedDict()
    fields["appid"] = BKVValue(BKV_INT32, generate_shortcut_appid(exe_value, appname))
    fields["appname"] = BKVValue(BKV_STRING, appname)
    fields["exe"] = BKVValue(BKV_STRING, exe_value)
    fields["StartDir"] = BKVValue(BKV_STRING, start_dir_value)
    fields["icon"] = BKVValue(BKV_STRING, "")
    fields["ShortcutPath"] = BKVValue(BKV_STRING, "")
    fields["LaunchOptions"] = BKVValue(BKV_STRING, "")
    fields["IsHidden"] = BKVValue(BKV_INT32, 0)
    fields["AllowDesktopConfig"] = BKVValue(BKV_INT32, 1)
    fields["AllowOverlay"] = BKVValue(BKV_INT32, 1)
    fields["OpenVR"] = BKVValue(BKV_INT32, 0)
    fields["Devkit"] = BKVValue(BKV_INT32, 0)
    fields["DevkitGameID"] = BKVValue(BKV_STRING, "")
    fields["DevkitOverrideAppID"] = BKVValue(BKV_INT32, 0)
    fields["LastPlayTime"] = BKVValue(BKV_INT32, 0)
    fields["FlatpakAppID"] = BKVValue(BKV_STRING, "")
    tag_obj: OrderedDict[str, BKVValue] = OrderedDict()
    for idx, tag in enumerate(tags):
        tag_obj[str(idx)] = BKVValue(BKV_STRING, tag)
    fields["tags"] = BKVValue(BKV_OBJECT, tag_obj)
    return BKVValue(BKV_OBJECT, fields)


def add_or_update_steam_shortcut(
    shortcuts_path: Path,
    appname: str,
    exe: Path,
    start_dir: Path,
    dirs: Dirs,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    if is_process_running(["steamwebhelper", "steam -", "/steam"]):
        if args.shutdown_steam:
            shutdown_steam(logger, args.dry_run)
        elif not args.allow_steam_running:
            raise DoomDeckError(
                "Steam appears to be running. Close Steam first, rerun with --shutdown-steam, "
                "or use --skip-steam-shortcut."
            )
        else:
            logger.warning("Steam appears to be running; modifying shortcuts.vdf anyway because --allow-steam-running was set")

    shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
    if shortcuts_path.exists():
        backup_path(shortcuts_path, dirs.backups, args.dry_run, logger, label="shortcuts.vdf")
    root = load_shortcuts(shortcuts_path)
    shortcuts_obj = root["shortcuts"].value
    target_exe = steam_quote_path(exe)
    existing_key: Optional[str] = None
    for key, value in shortcuts_obj.items():
        if value.type_code != BKV_OBJECT:
            continue
        entry = value.value
        existing_name = get_bkv_str(entry, "appname", "AppName")
        existing_exe = get_bkv_str(entry, "exe", "Exe")
        if existing_name == appname or existing_exe == target_exe:
            existing_key = key
            break
    entry_value = make_shortcut_entry(appname, exe, start_dir, tags=["Doom", "Tools"])
    if existing_key is not None:
        logger.info("Update existing Steam shortcut %s in %s", appname, shortcuts_path)
        shortcuts_obj[existing_key] = entry_value
    else:
        used = {int(k) for k in shortcuts_obj.keys() if k.isdigit()}
        index = 0
        while index in used:
            index += 1
        logger.info("Add Steam shortcut %s at index %s in %s", appname, index, shortcuts_path)
        shortcuts_obj[str(index)] = entry_value
    atomic_write_bytes(shortcuts_path, BinaryVDF.dumps(root), args.dry_run, logger)


def write_experimental_doomrunner_note(dirs: Dirs, args: argparse.Namespace, dry_run: bool, logger: logging.Logger) -> None:
    note = {
        "note": "Live Doom Runner options.json generation is enabled by default.",
        "primary_options_json": str(doomrunner_options_paths(dirs)[0]),
        "compatibility_options_json": str(doomrunner_options_paths(dirs)[1]),
        "backup_directory": str(dirs.backups),
        "generated_from": [
            str(dirs.doomrunner_config / "preset-manifest.json"),
            str(dirs.docs / "DOOM_RUNNER_SETUP.md"),
        ],
    }
    if args.experimental_doomrunner_config:
        note["experimental_requested"] = True
        note["result"] = "This flag is kept for compatibility; live options.json is now written by default."
    atomic_write_text(dirs.doomrunner_config / "options-json-policy.json", json.dumps(note, indent=2) + "\n", dry_run, logger)


def install(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    steamos_ok, steamos_msg = detect_steamos()
    steam = discover_steam(args, logger)
    actions = [
        f"Create/update managed layout under {dirs.root}",
        f"SteamOS suitability check: {steamos_msg}",
        f"Detect Steam root: {steam.steam_root if steam.steam_root else 'not found'}",
        f"Detect Steam DOOM + DOOM II app {APPID_DOOM_PLUS_DOOM_II}: {steam.app_install_dir if steam.app_install_dir else 'not found'}",
        "Install or reuse Doom Runner AppImage",
        "Install or reuse UZDoom AppImage",
        "Copy legal IWADs and add-on WADs from the Steam install into the managed Doom tree",
        "Create UZDoom classic/modern config templates and direct launcher scripts",
        "Check/update Brutal Doom from ModDB or install a supplied .pk3/.zip",
        "Check/update Project Brutality from GitHub and add a Doom Runner preset",
        "Generate Doom Runner live options.json, setup guide, and stable preset manifest",
    ]
    if not args.skip_steam_shortcut:
        actions.append(f"Add/update Steam non-Steam shortcut for Doom Runner at {steam.shortcuts_vdf if steam.shortcuts_vdf else 'unknown shortcuts.vdf'}")
    print_plan("Planned install actions", actions)

    if not steamos_ok:
        logger.warning("Environment warning: %s", steamos_msg)
    for directory in all_managed_dirs(dirs):
        ensure_dir(directory, args.dry_run, logger)

    install_appimage_from_github(
        "Youda008/DoomRunner",
        dirs.doomrunner / "DoomRunner.AppImage",
        dirs,
        args,
        logger,
        explicit_url=args.doomrunner_asset_url,
    )
    install_appimage_from_github(
        "UZDoom/UZDoom",
        dirs.uzdoom / "uzdoom.AppImage",
        dirs,
        args,
        logger,
        explicit_url=args.uzdoom_asset_url,
    )
    write_wrappers(dirs, args.dry_run, logger)
    write_uzdoom_configs(dirs, args.dry_run, logger)

    if steam.app_install_dir:
        iwads, addon_wads = find_wads_in_install(steam.app_install_dir, logger)
        if iwads:
            copy_iwads(iwads, dirs, args.dry_run, logger)
        else:
            logger.warning("No expected IWADs found under %s", steam.app_install_dir)
        if addon_wads:
            copy_addon_wads(addon_wads, dirs, args.dry_run, logger)
        else:
            logger.warning("No add-on WADs found under %s", steam.app_install_dir)
    else:
        logger.warning("Steam app %s not found. Install DOOM + DOOM II in Steam, then rerun install.", APPID_DOOM_PLUS_DOOM_II)

    brutal_path = resolve_brutal_doom(args, dirs, args.dry_run, logger)
    if brutal_path:
        logger.info("Brutal Doom alias: %s", brutal_path)
    else:
        logger.warning("Brutal Doom is not installed. Rerun without --skip-downloads/--skip-brutal-doom or use --brutal-doom-file.")

    project_brutality_path = resolve_project_brutality(args, dirs, args.dry_run, logger)
    if project_brutality_path:
        logger.info("Project Brutality alias: %s", project_brutality_path)
    else:
        logger.warning("Project Brutality is not installed. Rerun without --skip-downloads/--skip-project-brutality or use --project-brutality-file.")

    manifest = write_launchers_and_manifest(dirs, brutal_path, project_brutality_path, args.dry_run, logger)
    write_doomrunner_live_config(dirs, manifest, args, logger)
    write_docs(dirs, manifest, brutal_path, project_brutality_path, args.dry_run, logger)
    write_experimental_doomrunner_note(dirs, args, args.dry_run, logger)

    if not args.skip_steam_shortcut:
        if not steam.shortcuts_vdf:
            raise DoomDeckError("Could not locate Steam userdata/config/shortcuts.vdf path. Use --steam-root and/or --steam-user-id.")
        add_or_update_steam_shortcut(
            steam.shortcuts_vdf,
            "Doom Runner",
            dirs.launchers / "doom-runner.sh",
            dirs.root,
            dirs,
            args,
            logger,
        )
        logger.info("Restart Steam before expecting the non-Steam shortcut to appear in Gaming Mode")

    report = validate_internal(args, dirs, steam, logger, print_report=True)
    return 1 if any(item.level == "FAIL" for item in report) else 0


def validate(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    steam = discover_steam(args, logger)
    report = validate_internal(args, dirs, steam, logger, print_report=True)
    return 1 if any(item.level == "FAIL" for item in report) else 0


def add_item(items: list[ValidationItem], level: str, message: str) -> None:
    items.append(ValidationItem(level, message))


def validate_internal(
    args: argparse.Namespace,
    dirs: Dirs,
    steam: SteamInfo,
    logger: logging.Logger,
    print_report: bool = False,
) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    steamos_ok, steamos_msg = detect_steamos()
    add_item(items, "PASS" if steamos_ok else "WARN", steamos_msg)

    for path in [dirs.root, dirs.iwads, dirs.launchers, dirs.configs, dirs.docs]:
        add_item(items, "PASS" if path.exists() else "FAIL", f"Required path exists: {path}")

    doomrunner_app = dirs.doomrunner / "DoomRunner.AppImage"
    doomrunner_wrapper = dirs.launchers / "doom-runner.sh"
    uzdoom_app = dirs.uzdoom / "uzdoom.AppImage"
    uzdoom_wrapper = dirs.uzdoom / "uzdoom.sh"
    for label, path in [
        ("Doom Runner AppImage", doomrunner_app),
        ("Doom Runner wrapper", doomrunner_wrapper),
        ("UZDoom AppImage", uzdoom_app),
        ("UZDoom wrapper", uzdoom_wrapper),
    ]:
        executable = path.exists() and os.access(path, os.X_OK)
        add_item(items, "PASS" if executable else "FAIL", f"{label} exists and is executable: {path}")

    copied_iwads = sorted(
        p.name
        for pattern in ["*.WAD", "*.wad"]
        for p in dirs.iwads.glob(pattern)
        if p.name.lower() in IWAD_CANONICAL_NAMES
    )
    if copied_iwads:
        add_item(items, "PASS", f"IWADs present: {', '.join(copied_iwads)}")
    else:
        add_item(items, "FAIL", f"No IWADs found in {dirs.iwads}")
    for required in ["DOOM.WAD", "DOOM2.WAD"]:
        add_item(items, "PASS" if (dirs.iwads / required).exists() else "WARN", f"Expected common IWAD: {dirs.iwads / required}")

    addon_wads = sorted(p.name for pattern in ["*.WAD", "*.wad"] for p in dirs.pwads.glob(pattern))
    if addon_wads:
        sample = ", ".join(addon_wads[:8])
        suffix = "" if len(addon_wads) <= 8 else f", ... ({len(addon_wads)} total)"
        add_item(items, "PASS", f"Add-on WADs present in {dirs.pwads}: {sample}{suffix}")
    else:
        add_item(items, "WARN", f"No add-on WADs found in {dirs.pwads}")

    brutal_alias = dirs.brutal / BRUTAL_DOOM_ALIAS
    add_item(
        items,
        "PASS" if brutal_alias.exists() else "WARN",
        f"Brutal Doom alias exists for Brutal presets: {brutal_alias}",
    )
    if brutal_alias.exists():
        brutal_metadata = dirs.brutal / "brutal-doom.json"
        add_item(
            items,
            "PASS" if brutal_metadata.exists() else "WARN",
            f"Brutal Doom managed update metadata exists: {brutal_metadata}",
        )
    project_brutality_alias = dirs.project_brutality / PROJECT_BRUTALITY_ALIAS
    add_item(
        items,
        "PASS" if project_brutality_alias.exists() else "WARN",
        f"Project Brutality alias exists for Project Brutality preset: {project_brutality_alias}",
    )
    if project_brutality_alias.exists():
        project_brutality_metadata = dirs.project_brutality / "project-brutality.json"
        add_item(
            items,
            "PASS" if project_brutality_metadata.exists() else "WARN",
            f"Project Brutality managed update metadata exists: {project_brutality_metadata}",
        )
        markers_ok = zip_contains_markers(project_brutality_alias, {"zscript.zc", "gameinfo.txt"})
        add_item(
            items,
            "PASS" if markers_ok else "WARN",
            f"Project Brutality archive has expected UZDoom root files: {project_brutality_alias}",
        )

    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    manifest: Optional[dict[str, Any]] = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            add_item(items, "PASS", f"Preset manifest JSON is valid: {manifest_path}")
        except json.JSONDecodeError as exc:
            add_item(items, "FAIL", f"Preset manifest JSON is invalid: {manifest_path}: {exc}")
    else:
        add_item(items, "FAIL", f"Preset manifest missing: {manifest_path}")

    if manifest:
        project_brutality_preset_ok = any(preset.get("name") == "Project Brutality" for preset in manifest.get("presets", []))
        add_item(items, "PASS" if project_brutality_preset_ok else "FAIL", f"Preset manifest includes Project Brutality preset: {manifest_path}")
        for preset in manifest.get("presets", []):
            name = preset.get("name", "<unnamed>")
            for key in ["iwad", "config", "autoexec", "launcher"]:
                p = Path(preset.get(key, ""))
                add_item(items, "PASS" if p.exists() else "FAIL", f"Preset {name} references existing {key}: {p}")
            for file_name in preset.get("files", []):
                p = Path(file_name)
                level = "PASS" if p.exists() else "WARN"
                add_item(items, level, f"Preset {name} mod file reference: {p}")

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
                ]
            )
            add_item(items, "PASS" if controller_ok else "FAIL", f"{profile} UZDoom Steam Deck controller bindings: {autoexec_path}")
        else:
            add_item(items, "FAIL", f"{profile} UZDoom autoexec missing: {autoexec_path}")

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
            add_item(items, "PASS" if display_ok else "FAIL", f"{profile} UZDoom Steam Deck display settings: {ini_path}")
        else:
            add_item(items, "FAIL", f"{profile} UZDoom ini missing: {ini_path}")

    live_options_path = doomrunner_options_paths(dirs)[0]
    if live_options_path.exists():
        try:
            live_options = json.loads(live_options_path.read_text(encoding="utf-8"))
            add_item(items, "PASS", f"Doom Runner live options JSON is valid: {live_options_path}")
            engine_list = live_options.get("engines", {}).get("engine_list", [])
            engine_ok = any(
                engine.get("id") == DOOMRUNNER_ENGINE_ID
                and bool(engine.get("path"))
                and Path(engine.get("path", "")).exists()
                for engine in engine_list
            )
            add_item(items, "PASS" if engine_ok else "FAIL", f"Doom Runner live config has usable UZDoom engine: {live_options_path}")
            iwad_list = live_options.get("IWADs", {}).get("IWAD_list", [])
            iwad_ok = any(bool(iwad.get("path")) and Path(iwad.get("path", "")).exists() for iwad in iwad_list)
            add_item(items, "PASS" if iwad_ok else "FAIL", f"Doom Runner live config has IWAD entries: {live_options_path}")
            live_presets = live_options.get("presets", [])
            preset_ok = any(preset.get("selected_engine") == DOOMRUNNER_ENGINE_ID and preset.get("selected_IWAD") for preset in live_presets)
            add_item(items, "PASS" if preset_ok else "FAIL", f"Doom Runner live config has launchable presets: {live_options_path}")
            video_options = live_options.get("video_options", {})
            resolution_ok = (
                video_options.get("resolution_x") == STEAM_DECK_WIDTH
                and video_options.get("resolution_y") == STEAM_DECK_HEIGHT
            )
            add_item(items, "PASS" if resolution_ok else "FAIL", f"Doom Runner live config uses Steam Deck resolution: {live_options_path}")
        except json.JSONDecodeError as exc:
            add_item(items, "FAIL", f"Doom Runner live options JSON is invalid: {live_options_path}: {exc}")
    else:
        add_item(items, "FAIL", f"Doom Runner live options missing: {live_options_path}")

    shell_scripts = [uzdoom_wrapper, *sorted(dirs.launchers.glob("*.sh"))]
    seen_scripts: set[Path] = set()
    for script in shell_scripts:
        if script in seen_scripts:
            continue
        seen_scripts.add(script)
        if script.exists():
            shebang_ok = script_has_execve_shebang(script)
            add_item(
                items,
                "PASS" if shebang_ok else "FAIL",
                f"Shell script has execve-compatible shebang on first line: {script}",
            )
            result = run_command(["bash", "-n", str(script)], logger, dry_run=args.dry_run, timeout=10)
            add_item(items, "PASS" if result.returncode == 0 else "FAIL", f"Shell syntax valid for {script}")

    if steam.steam_root:
        add_item(items, "PASS", f"Steam root detected: {steam.steam_root}")
    else:
        add_item(items, "WARN", "Steam root not detected")
    if steam.app_install_dir:
        add_item(items, "PASS", f"Steam app {APPID_DOOM_PLUS_DOOM_II} install detected: {steam.app_install_dir}")
    else:
        add_item(items, "WARN", f"Steam app {APPID_DOOM_PLUS_DOOM_II} install not detected")

    if steam.shortcuts_vdf and steam.shortcuts_vdf.exists():
        try:
            root = load_shortcuts(steam.shortcuts_vdf)
            shortcuts_obj = root["shortcuts"].value
            found = False
            for value in shortcuts_obj.values():
                if value.type_code == BKV_OBJECT and get_bkv_str(value.value, "appname", "AppName") == "Doom Runner":
                    found = True
                    exe = get_bkv_str(value.value, "exe", "Exe")
                    if str(doomrunner_wrapper) in exe:
                        add_item(items, "PASS", "Steam shortcut exists for Doom Runner with expected wrapper path")
                    else:
                        add_item(items, "WARN", f"Steam shortcut named Doom Runner exists but exe differs: {exe}")
                    break
            if not found:
                add_item(items, "WARN", f"No Doom Runner shortcut found in {steam.shortcuts_vdf}")
        except DoomDeckError as exc:
            add_item(items, "FAIL", f"Could not parse shortcuts.vdf: {exc}")
    else:
        add_item(items, "WARN", "Steam shortcuts.vdf does not exist yet or Steam user was not detected")

    if not any(dirs.backups.glob("*")):
        add_item(items, "WARN", f"No backups found yet in {dirs.backups}; this is normal before the first replacement or Steam shortcut update")
    else:
        add_item(items, "PASS", f"Backups directory contains backup files: {dirs.backups}")

    if print_report:
        print("\nValidation report")
        print("=================")
        for item in items:
            print(f"[{item.level}] {item.message}")
        print()
    return items


def create_backup_archive(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    if not dirs.root.exists():
        raise DoomDeckError(f"Nothing to back up; root does not exist: {dirs.root}")
    archive = dirs.backups / f"doom-deck-backup-{now_stamp()}.tar.gz"
    print_plan("Planned backup actions", [f"Create archive {archive}", "Exclude nested backup archives to avoid recursion"])
    if args.dry_run:
        return 0
    dirs.backups.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for item in dirs.root.rglob("*"):
            if item == archive or dirs.backups in item.parents:
                continue
            tar.add(item, arcname=item.relative_to(dirs.root.parent), recursive=False)
    logger.info("Backup archive written: %s", archive)
    return 0


def clean(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    if not dirs.root.exists():
        logger.info("Nothing to clean; root does not exist: %s", dirs.root)
        return 0
    external_backups = dirs.root.parent / f"{dirs.root.name}.backups"
    archive = external_backups / f"doom-deck-clean-backup-{now_stamp()}.tar.gz"
    if args.yes_delete:
        actions = [f"Create external backup archive {archive}", f"Permanently delete {dirs.root}"]
    else:
        moved = dirs.root.parent / f"{dirs.root.name}.removed-{now_stamp()}"
        actions = [f"Move {dirs.root} to {moved} instead of deleting it"]
    print_plan("Planned clean actions", actions)
    if args.dry_run:
        return 0
    external_backups.mkdir(parents=True, exist_ok=True)
    if args.yes_delete:
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(dirs.root, arcname=dirs.root.name)
        shutil.rmtree(dirs.root)
        logger.info("Deleted %s after writing backup archive %s", dirs.root, archive)
    else:
        moved = dirs.root.parent / f"{dirs.root.name}.removed-{now_stamp()}"
        shutil.move(str(dirs.root), str(moved))
        logger.info("Moved %s -> %s", dirs.root, moved)
    return 0


def restore(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    archive = expand_path(args.backup_archive)
    if not archive.exists():
        raise DoomDeckError(f"Backup archive does not exist: {archive}")
    replaced = dirs.root.parent / f"{dirs.root.name}.pre-restore-{now_stamp()}"
    actions = [f"Extract {archive} under {dirs.root.parent}"]
    if dirs.root.exists():
        actions.insert(0, f"Move existing {dirs.root} to {replaced}")
    print_plan("Planned restore actions", actions)
    if args.dry_run:
        return 0
    if dirs.root.exists():
        shutil.move(str(dirs.root), str(replaced))
    with tarfile.open(archive, "r:gz") as tar:
        safe_extract_tar(tar, dirs.root.parent)
    logger.info("Restore completed from %s", archive)
    return 0


def safe_extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tar.getmembers():
        member_path = (dest / member.name).resolve()
        if not str(member_path).startswith(str(dest) + os.sep):
            raise DoomDeckError(f"Unsafe path in tar archive: {member.name}")
    tar.extractall(dest)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help=f"Managed Doom root directory (default: {DEFAULT_ROOT})")
    parser.add_argument("--steam-root", help="Steam root override, e.g. ~/.local/share/Steam")
    parser.add_argument("--steam-user-id", help="Steam userdata numeric ID override")
    parser.add_argument("--dry-run", action="store_true", help="Print and log intended changes without writing files")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging to console")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up Doom Runner, UZDoom, IWADs, launchers, and Steam integration on Steam Deck.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="Install/update the managed Doom setup")
    add_common_args(install_parser)
    install_parser.add_argument("--skip-downloads", action="store_true", help="Do not download AppImages or managed mod archives; reuse files already in place")
    install_parser.add_argument("--force-download", action="store_true", help="Redownload release assets and managed mod archives even if present in downloads/")
    install_parser.add_argument("--doomrunner-asset-url", help="Explicit Doom Runner AppImage URL override")
    install_parser.add_argument("--uzdoom-asset-url", help="Explicit UZDoom AppImage URL override")
    install_parser.add_argument("--brutal-doom-url", help="Explicit Brutal Doom .pk3/.zip download URL override")
    install_parser.add_argument("--project-brutality-url", help="Explicit Project Brutality .pk3/.zip download URL override")
    install_parser.add_argument("--prefer-legacy-appimage", action="store_true", help="Prefer Legacy AppImage assets when available")
    install_parser.add_argument(
        "--brutal-doom-channel",
        choices=["latest", "stable"],
        default="latest",
        help="Brutal Doom ModDB channel: latest can include beta/test builds; stable prefers non-beta candidates",
    )
    install_parser.add_argument("--brutal-doom-file", help="Path to a manually downloaded Brutal Doom .pk3/.wad/.zip")
    install_parser.add_argument("--project-brutality-file", help="Path to a manually downloaded Project Brutality .pk3/.wad/.zip")
    install_parser.add_argument("--skip-brutal-doom", action="store_true", help="Do not download, update, or install Brutal Doom")
    install_parser.add_argument("--skip-project-brutality", action="store_true", help="Do not download or install Project Brutality")
    install_parser.add_argument("--skip-steam-shortcut", action="store_true", help="Do not modify Steam shortcuts.vdf")
    install_parser.add_argument("--skip-doomrunner-live-config", action="store_true", help="Do not write Doom Runner's live options.json")
    install_parser.add_argument("--shutdown-steam", action="store_true", help="Attempt to shut down Steam before modifying shortcuts.vdf")
    install_parser.add_argument("--allow-steam-running", action="store_true", help="Modify shortcuts.vdf even if Steam appears to be running")
    install_parser.add_argument(
        "--experimental-doomrunner-config",
        action="store_true",
        help="Deprecated compatibility flag; live Doom Runner options.json is now written by default",
    )
    install_parser.set_defaults(func=install)

    validate_parser = subparsers.add_parser("validate", help="Validate the setup")
    add_common_args(validate_parser)
    validate_parser.set_defaults(func=validate)

    backup_parser = subparsers.add_parser("backup", help="Create a tar.gz backup of the managed Doom root")
    add_common_args(backup_parser)
    backup_parser.set_defaults(func=create_backup_archive)

    clean_parser = subparsers.add_parser("clean", help="Safely clean the managed Doom root")
    add_common_args(clean_parser)
    clean_parser.add_argument("--yes-delete", action="store_true", help="Actually delete the managed root after creating an external backup archive")
    clean_parser.set_defaults(func=clean)

    restore_parser = subparsers.add_parser("restore", help="Restore a backup archive")
    add_common_args(restore_parser)
    restore_parser.add_argument("backup_archive", help="Path to a backup tar.gz archive")
    restore_parser.set_defaults(func=restore)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except DoomDeckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Defensive: still surface unexpected stack details for automation logs.
        print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
        if getattr(args, "verbose", False):
            raise
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
