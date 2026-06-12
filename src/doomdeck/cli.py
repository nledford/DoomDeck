#!/usr/bin/env python3
"""
DoomDeck CLI

Steam Deck Doom modding setup automation for:
- Steam DOOM + DOOM II app 2280 IWAD discovery/copy
- Windows Doom Runner installation for Proton
- Windows UZDoom installation for Proton
- Brutal Doom manual-drop validation
- Steam non-Steam shortcut integration for Doom Runner and direct UZDoom presets
- UZDoom launch metadata for vanilla-style, UZDoom, Brutal Doom, and Project Brutality presets
- Doom Runner options.json generation with Proton-visible Windows paths

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
import datetime as _dt
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional

from doomdeck.application.content_groups import build_content_group_document
from doomdeck.application.doomrunner import (
    build_doomrunner_options,
    doomrunner_options_paths,
    launcher_slug,
)
from doomdeck.application.install import build_install_plan
from doomdeck.application.managed_mods import (
    install_brutal_doom_archive,
    install_project_brutality_archive,
    metadata_matches,
)
from doomdeck.application.moddb_wads import install_moddb_wad_urls
from doomdeck.application.presets import build_preset_manifest
from doomdeck.application.presets import choose_default_preset_iwad as _choose_default_preset_iwad
from doomdeck.application.proton import build_uzdoom_launch_options, proton_windows_path
from doomdeck.application.validation import InstallationValidator, format_validation_report, validation_has_failures
from doomdeck.application.wads import find_wads_in_install
from doomdeck.domain.deck import STEAM_DECK_HEIGHT, STEAM_DECK_TARGET_FPS, STEAM_DECK_WIDTH
from doomdeck.domain.downloads import DownloadPolicy
from doomdeck.domain.models import DoomDeckError, Dirs, GitHubAsset, SteamInfo, ValidationItem
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, ModSource
from doomdeck.domain.paths import all_managed_dirs, build_dirs, expand_path
from doomdeck.infrastructure.archives import (
    safe_extract_tar,
    safe_extract_zip,
    write_tree_tar_gz,
)
from doomdeck.infrastructure.binary_vdf import BinaryVDF
from doomdeck.infrastructure.downloads import download_url as _download_url
from doomdeck.infrastructure.files import (
    atomic_write_bytes,
    atomic_write_text,
    backup_path,
    files_equal,
)
from doomdeck.infrastructure.github_api import (
    validate_github_release_payload,
    validate_github_repository_payload,
)
from doomdeck.infrastructure.moddb import (
    BRUTAL_DOOM_MODDB_URL,
    safe_download_name,
    select_brutal_doom_download,
)
from doomdeck.infrastructure.steam_shortcuts import (
    load_shortcuts,
    upsert_shortcut,
)
from doomdeck.infrastructure.steam_compat import compat_mapping_key, dumps_text_vdf, load_text_vdf, set_compat_tool_mapping

APPID_DOOM_PLUS_DOOM_II = "2280"
DEFAULT_ROOT = Path.home() / "Games" / "Doom"
SCRIPT_VERSION = "2026.05.31"

BRUTAL_DOOM_ALIAS = BRUTAL_DOOM_MOD.alias
PROJECT_BRUTALITY_REPO = "pa1nki113r/Project_Brutality"
PROJECT_BRUTALITY_ALIAS = PROJECT_BRUTALITY_MOD.alias
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

STEAM_ROOT_CANDIDATES = [
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".steam" / "steam",
    Path.home() / ".steam" / "root",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
]

GITHUB_USER_AGENT = f"doomdeck/{SCRIPT_VERSION}"


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


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
    localconfig = shortcuts.parent / "localconfig.vdf" if shortcuts else None
    return SteamInfo(steam_root, user_id, shortcuts, libraries, app_install_dir, localconfig)


def copy_wads(
    wads: dict[str, Path],
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
    label: str,
    overwrite_existing: bool = True,
) -> None:
    for name, src in wads.items():
        dest = dest_dir / name.upper()
        if dest.exists() and files_equal(src, dest):
            logger.info("%s already copied: %s", label, dest)
            continue
        if dest.exists() and not overwrite_existing:
            logger.warning("Preserving existing %s with same name; skipping copy from %s: %s", label, src, dest)
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
    copy_wads(wads, dirs.pwads, dirs.backups, dry_run, logger, "add-on WAD", overwrite_existing=False)


def github_request_json(url: str) -> Any:
    DownloadPolicy.for_hosts({"api.github.com"}).validate_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": GITHUB_USER_AGENT, "Accept": "application/vnd.github+json"})
    # URL policy is validated before opening the request.
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def select_release_asset(repo: str, prefer_legacy_appimage: bool, logger: logging.Logger) -> GitHubAsset:
    release = validate_github_release_payload(
        github_request_json(f"https://api.github.com/repos/{repo}/releases/latest"),
        repo,
    )
    tag_name = release.label
    assets = release.assets
    if not assets:
        raise DoomDeckError(f"GitHub release {repo}@{tag_name} has no downloadable assets")

    repo_key = repo.split("/")[-1].lower().replace("_", "").replace("-", "")

    def score(asset: Any) -> int:
        name = asset.name
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
        names = ", ".join(a.name for a in assets)
        raise DoomDeckError(f"Could not identify a suitable Linux AppImage for {repo}@{tag_name}. Assets: {names}")
    logger.info("Selected GitHub asset for %s: %s", repo, chosen.name)
    return GitHubAsset(
        name=chosen.name,
        url=chosen.browser_download_url,
        size=chosen.size,
        tag_name=str(tag_name),
    )


def select_windows_release_asset(repo: str, logger: logging.Logger) -> GitHubAsset:
    release = validate_github_release_payload(
        github_request_json(f"https://api.github.com/repos/{repo}/releases/latest"),
        repo,
    )
    tag_name = release.label
    assets = release.assets
    if not assets:
        raise DoomDeckError(f"GitHub release {repo}@{tag_name} has no downloadable assets")

    repo_key = repo.split("/")[-1].lower().replace("_", "").replace("-", "")

    def score(asset: Any) -> int:
        name = asset.name
        lower = name.lower()
        compact = lower.replace("_", "").replace("-", "")
        value = 0
        if lower.endswith(".zip"):
            value += 100
        if "windows" in lower or "win64" in lower:
            value += 80
        if any(token in lower for token in ["x86_64", "x64", "amd64"]):
            value += 40
        if "recent" in lower:
            value += 15
        if repo_key in compact:
            value += 10
        if any(token in lower for token in ["legacy", "i386", "i686", "x86-32"]):
            value -= 80
        if any(token in lower for token in ["linux", "appimage", "mac", "dmg", "arm64", "aarch64"]):
            value -= 120
        return value

    ranked = sorted(assets, key=score, reverse=True)
    chosen = ranked[0]
    if score(chosen) < 120:
        names = ", ".join(a.name for a in assets)
        raise DoomDeckError(f"Could not identify a suitable Windows ZIP for {repo}@{tag_name}. Assets: {names}")
    logger.info("Selected Windows GitHub asset for %s: %s", repo, chosen.name)
    return GitHubAsset(
        name=chosen.name,
        url=chosen.browser_download_url,
        size=chosen.size,
        tag_name=str(tag_name),
    )


def download_url(
    url: str,
    dest: Path,
    dry_run: bool,
    logger: logging.Logger,
    force: bool = False,
    headers: Optional[dict[str, str]] = None,
    allowed_hosts: Optional[set[str]] = None,
    expected_size: Optional[int] = None,
    expected_sha256: Optional[str] = None,
    expected_md5: Optional[str] = None,
) -> Path:
    return _download_url(
        url,
        dest,
        dry_run,
        logger,
        force=force,
        headers=headers,
        allowed_hosts=allowed_hosts,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        expected_md5=expected_md5,
        user_agent=GITHUB_USER_AGENT,
    )


def install_windows_app_from_github(
    repo: str,
    target_dir: Path,
    expected_exe: str,
    dirs: Dirs,
    args: argparse.Namespace,
    logger: logging.Logger,
    explicit_url: Optional[str] = None,
) -> Optional[Path]:
    exe_path = target_dir / expected_exe
    if args.skip_downloads and not explicit_url:
        if exe_path.exists():
            logger.info("Skipping download; using existing Windows app %s", exe_path)
            return exe_path
        logger.warning("Skipping download and target does not exist: %s", exe_path)
        return None
    if explicit_url:
        asset_name = safe_download_name(explicit_url, f"{repo.split('/')[-1]}.zip")
        url = explicit_url
        expected_size = None
        allowed_hosts = None
    else:
        asset = select_windows_release_asset(repo, logger)
        asset_name = safe_download_name(asset.name, f"{repo.split('/')[-1]}.zip")
        url = asset.url
        expected_size = asset.size
        allowed_hosts = {"github.com"}
    downloaded = download_url(
        url,
        dirs.downloads / asset_name,
        args.dry_run,
        logger,
        force=args.force_download,
        allowed_hosts=allowed_hosts,
        expected_size=expected_size,
    )
    if args.dry_run:
        return exe_path
    install_windows_app_archive(downloaded, target_dir, expected_exe, dirs.backups, logger)
    return exe_path


def install_windows_app_archive(
    archive_path: Path,
    target_dir: Path,
    expected_exe: str,
    backups_dir: Path,
    logger: logging.Logger,
) -> None:
    temp_dir = target_dir.parent / f".{target_dir.name}.extract-{now_stamp()}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    logger.info("Extract Windows app archive: %s -> %s", archive_path, temp_dir)
    try:
        safe_extract_zip(archive_path, temp_dir)
        exe_path = temp_dir / expected_exe
        if not exe_path.exists():
            raise DoomDeckError(f"Windows archive did not contain expected executable {expected_exe}: {archive_path}")
        if target_dir.exists() or target_dir.is_symlink():
            backup_path(target_dir, backups_dir, dry_run=False, logger=logger, label=target_dir.name)
            if target_dir.is_dir() and not target_dir.is_symlink():
                shutil.rmtree(target_dir)
            else:
                target_dir.unlink()
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_dir), str(target_dir))
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise


def select_project_brutality_download(logger: logging.Logger) -> GitHubAsset:
    try:
        release_payload = github_request_json(f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise DoomDeckError(f"Could not read Project Brutality release metadata: {exc}") from exc
        release_payload = {}
    release = validate_github_release_payload(release_payload, PROJECT_BRUTALITY_REPO)
    tag_name = release.label
    assets = release.assets

    def score(asset: Any) -> int:
        name = asset.name
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
        logger.info("Selected Project Brutality release asset: %s", chosen.name)
        return GitHubAsset(
            name=chosen.name,
            url=chosen.browser_download_url,
            size=chosen.size,
            tag_name=tag_name,
        )

    zipball_url = release.zipball_url
    if not zipball_url:
        repo_meta = validate_github_repository_payload(
            github_request_json(f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}"),
            PROJECT_BRUTALITY_REPO,
        )
        default_branch = repo_meta.default_branch or "master"
        tag_name = default_branch
        zipball_url = f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/zipball/{default_branch}"
    fallback_name = f"Project_Brutality-{safe_download_name(tag_name, 'latest')}.zip"
    logger.info("Using Project Brutality source zipball: %s", tag_name)
    return GitHubAsset(name=fallback_name, url=str(zipball_url), size=None, tag_name=tag_name)


def resolve_project_brutality(args: argparse.Namespace, dirs: Dirs, dry_run: bool, logger: logging.Logger) -> Optional[Path]:
    canonical = PROJECT_BRUTALITY_MOD.alias_path(dirs.project_brutality)
    metadata_path = PROJECT_BRUTALITY_MOD.metadata_path(dirs.project_brutality)
    if args.project_brutality_file:
        src = expand_path(args.project_brutality_file)
        if not src.exists():
            raise DoomDeckError(f"--project-brutality-file does not exist: {src}")
        if src.suffix.lower() not in {".pk3", ".wad", ".zip"}:
            raise DoomDeckError(f"Project Brutality file should be a .pk3/.wad/.zip, got: {src}")
        return install_project_brutality_archive(
            src,
            canonical,
            dirs.backups,
            metadata_path,
            dry_run,
            logger,
            ModSource.local_file(src),
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
        expected_size = None
        allowed_hosts = None
    else:
        asset = select_project_brutality_download(logger)
        url = asset.url
        asset_name = safe_download_name(asset.name, "Project_Brutality.zip")
        tag_name = asset.tag_name
        expected_size = asset.size
        allowed_hosts = {"api.github.com", "github.com"}
    downloaded = download_url(
        url,
        dirs.downloads / asset_name,
        dry_run,
        logger,
        force=args.force_download,
        allowed_hosts=allowed_hosts,
        expected_size=expected_size,
    )
    return install_project_brutality_archive(
        downloaded,
        canonical,
        dirs.backups,
        metadata_path,
        dry_run,
        logger,
        ModSource.github(url=url, tag=tag_name),
        force=args.force_download,
    )


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
bind F6 quicksave
bind F9 quickload
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
// Modern dual-stick/FPS-style behavior for UZDoom, Brutal Doom, and Project Brutality.
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
bind F6 quicksave
bind F9 quickload
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
    canonical = BRUTAL_DOOM_MOD.alias_path(dirs.brutal)
    metadata_path = BRUTAL_DOOM_MOD.metadata_path(dirs.brutal)

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
            ModSource.local_existing(candidates[0]),
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
            ModSource.local_file(src),
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
        source = ModSource.explicit_url(url, asset_name)
        downloaded = download_url(url, dirs.downloads / asset_name, dry_run, logger, force=args.force_download)
        return install_brutal_doom_archive(downloaded, canonical, dirs.backups, metadata_path, dry_run, logger, source, force=args.force_download)

    try:
        selected = select_brutal_doom_download(args.brutal_doom_channel, logger, user_agent=GITHUB_USER_AGENT)
    except DoomDeckError as exc:
        if canonical.exists():
            logger.warning("Could not check Brutal Doom updates automatically; using existing alias: %s", exc)
            return canonical
        logger.warning("Could not install Brutal Doom automatically: %s", exc)
        return None

    source = ModSource.moddb(
        channel=args.brutal_doom_channel,
        title=selected.title,
        page_url=selected.page_url,
        filename=selected.filename,
        updated=selected.updated,
        md5=selected.md5,
    )
    compare_keys = ["source_type", "source_channel", "source_page_url", "source_filename", "source_updated", "source_md5"]
    already_current = canonical.exists() and metadata_matches(metadata_path, source.as_metadata(), compare_keys)
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
        allowed_hosts={"moddb.com"},
        expected_md5=selected.md5 or None,
    )
    return install_brutal_doom_archive(
        downloaded,
        canonical,
        dirs.backups,
        metadata_path,
        dry_run,
        logger,
        ModSource.moddb(
            channel=args.brutal_doom_channel,
            title=selected.title,
            page_url=selected.page_url,
            filename=selected.filename,
            updated=selected.updated,
            md5=selected.md5,
            download_url=selected.download_url,
        ),
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


def choose_default_preset_iwad(dirs: Dirs) -> Optional[Path]:
    return _choose_default_preset_iwad(dirs)


def generate_preset_manifest(dirs: Dirs, brutal_path: Optional[Path], project_brutality_path: Optional[Path]) -> dict[str, Any]:
    return build_preset_manifest(dirs, brutal_path, project_brutality_path)


def is_generated_preset_launcher(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return (
        (
            "UZDOOM=" in text
            and "IWAD=" in text
            and 'exec "$UZDOOM" -noautoload -iwad "$IWAD"' in text
        )
        or "DOOMDECK_WINDOWS_PROTON_PRESET=" in text
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
    written_launchers: set[Path] = set()
    for preset in manifest["presets"]:
        launcher = Path(preset["launcher"])
        written_launchers.add(launcher)
        files = [Path(p) for p in preset.get("files", [])]
        shortcut_name = f"DoomDeck - {preset['name']}"
        preset["steam_shortcut_name"] = shortcut_name
        preset["launch_options"] = build_uzdoom_launch_options(preset)
        missing_guard = ""
        if files:
            missing_hint = str(preset.get("missing_hint", "Install the required mod file, then rerun this launcher."))
            for file_path in files:
                missing_guard += f"if [[ ! -f {shell_quote(str(file_path))} ]]; then\n"
                missing_guard += f"  echo 'Missing required mod file: {file_path}' >&2\n"
                missing_guard += f"  echo {shell_quote(missing_hint)} >&2\n"
                missing_guard += "  exit 2\nfi\n"
        content = f"""#!/usr/bin/env bash
set -euo pipefail
DOOMDECK_WINDOWS_PROTON_PRESET={shell_quote(str(preset["name"]))}
STEAM_SHORTCUT={shell_quote(shortcut_name)}
if [[ ! -f {shell_quote(str(Path(preset["iwad"])))} ]]; then
  echo "Missing IWAD: {preset["iwad"]}" >&2
  exit 1
fi
{missing_guard}echo "Launch $DOOMDECK_WINDOWS_PROTON_PRESET from the Steam shortcut '$STEAM_SHORTCUT' so Windows UZDoom runs through Proton with Steam Input." >&2
exit 2
"""
        atomic_write_text(launcher, content, dry_run, logger, mode=0o755)

    remove_stale_generated_launchers(dirs, written_launchers, dry_run, logger)
    write_content_group_metadata(dirs, manifest, dry_run, logger)
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n", dry_run, logger)
    return manifest


def read_existing_preset_manifest(dirs: Dirs) -> dict[str, Any]:
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    if not manifest_path.exists():
        return {"presets": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"presets": []}
    return manifest if isinstance(manifest, dict) else {"presets": []}


def write_content_group_metadata(
    dirs: Dirs,
    manifest: dict[str, Any],
    dry_run: bool,
    logger: logging.Logger,
) -> dict[str, object]:
    document = build_content_group_document(dirs, manifest)
    groups = document["content_groups"]
    manifest["content_groups"] = groups
    atomic_write_text(dirs.doomrunner_config / "content-groups.json", json.dumps(document, indent=2) + "\n", dry_run, logger)
    return document


def refresh_existing_doomrunner_content_groups(
    dirs: Dirs,
    groups: object,
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    for options_path in doomrunner_options_paths(dirs):
        if not options_path.exists():
            continue
        try:
            options = json.loads(options_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not refresh Doom Runner content groups in invalid options JSON: %s", options_path)
            continue
        if not isinstance(options, dict):
            logger.warning("Could not refresh Doom Runner content groups in non-object options JSON: %s", options_path)
            continue
        if options.get("content_groups") == groups:
            logger.info("Doom Runner content groups already current: %s", options_path)
            continue
        backup_path(options_path, dirs.backups, dry_run, logger, label=f"doomrunner-content-groups-{options_path.parent.parent.name}.json")
        options["content_groups"] = groups
        atomic_write_text(options_path, json.dumps(options, indent=4) + "\n", dry_run, logger)


def write_doomrunner_live_config(dirs: Dirs, manifest: dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> None:
    if getattr(args, "skip_doomrunner_live_config", False):
        logger.info("Skipping Doom Runner generated options.json copies")
        return
    if is_process_running(["DoomRunner.exe", "DoomRunner "]):
        raise DoomDeckError("Doom Runner appears to be running. Close it before rewriting options.json.")

    options = build_doomrunner_options(dirs, manifest)
    content = json.dumps(options, indent=4) + "\n"
    for preset in manifest.get("presets", []):
        slug = launcher_slug(str(preset.get("name", ""))).lower()
        if slug:
            ensure_dir(dirs.saves / slug, args.dry_run, logger)
            ensure_dir(dirs.screenshots / slug, args.dry_run, logger)

    extra_options_paths = tuple(getattr(args, "extra_doomrunner_options_paths", ()))
    for options_path in [*doomrunner_options_paths(dirs), *extra_options_paths]:
        if options_path.exists():
            try:
                current = options_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                current = ""
            if current == content:
                logger.info("Doom Runner generated options already current: %s", options_path)
                continue
            label = f"doomrunner-options-{options_path.parent.parent.name}.json"
            backup_path(options_path, dirs.backups, args.dry_run, logger, label=label)
        atomic_write_text(options_path, content, args.dry_run, logger)


def doomrunner_proton_options_path(steam: SteamInfo, appid: int) -> Optional[Path]:
    if not steam.steam_root:
        return None
    return (
        steam.steam_root
        / "steamapps"
        / "compatdata"
        / compat_mapping_key(appid)
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "AppData"
        / "Roaming"
        / "DoomRunner"
        / "options.json"
    )


def render_content_group_guide(manifest: dict[str, Any]) -> str:
    content_groups = manifest.get("content_groups", {})
    if not isinstance(content_groups, dict):
        return ""
    section_titles = {
        "presets": "Preset Groups",
        "map_packs": "Map Pack Groups",
        "mods": "Mod Groups",
    }
    output = "\n## Automatic Content Groups\n\nDoomDeck writes group metadata separately from launchable items. Group headings are labels only; the entries listed under them remain the selectable presets, WADs, map packs, and mods.\n"
    wrote_any = False
    for section_key, title in section_titles.items():
        groups = content_groups.get(section_key, [])
        if not isinstance(groups, list) or not groups:
            continue
        wrote_any = True
        output += f"\n### {title}\n"
        for group in groups:
            if not isinstance(group, dict):
                continue
            output += f"\n#### {group.get('display_name', group.get('id', 'Group'))}\n"
            items = group.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = f" - `{item['path']}`" if item.get("path") else ""
                output += f"- `{item.get('display_name', item.get('id', 'item'))}`{path}\n"
    return output if wrote_any else ""


def write_docs(
    dirs: Dirs,
    manifest: dict[str, Any],
    brutal_path: Optional[Path],
    project_brutality_path: Optional[Path],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    # Generated Markdown, not a SQL expression.
    layout = (  # nosec B608
        f"""# Doom Deck Setup Layout

Generated by `doomdeck`.

```text
{dirs.root}/
├── tools/doomrunner/              Windows Doom Runner executable for Proton
├── source-ports/uzdoom/           Windows UZDoom executable for Proton
├── iwads/                         Legal IWAD copies from Steam app {APPID_DOOM_PLUS_DOOM_II}
├── pwads/                         User PWADs and map packs
├── mods/brutal-doom/              Managed Brutal Doom .pk3 and update metadata
├── mods/project-brutality/         Downloaded Project Brutality .pk3
├── configs/doomrunner/            Generated manifest and Doom Runner setup guide
├── configs/uzdoom/                Classic and modern UZDoom config templates
├── launchers/                     Generated preset helper scripts and launch metadata
├── saves/                         Save-game location for future use
├── screenshots/                   Screenshot location for future use
├── downloads/                     Downloaded upstream release assets
├── backups/                       Backups made before replacement/modification
└── logs/                          Script logs
```
"""
    )
    steam_input = f"""# Steam Input Profiles for Doom Runner / UZDoom

DoomDeck installs the Windows builds of Doom Runner and UZDoom and forces generated Steam shortcuts to use the configured Steam compatibility tool. The default is `proton_10`. Steam Input should present Steam Deck, Xbox, PlayStation, and other supported controllers to Windows UZDoom as a gamepad.

The generated UZDoom configs enable joystick input and bind common Steam Deck gamepad buttons directly. Steam's standard Gamepad layout should work for the generated presets; use Steam's controller configurator only if you want a custom layout.

The generated UZDoom configs also default to fullscreen {STEAM_DECK_WIDTH}x{STEAM_DECK_HEIGHT}, vsync on, and a {STEAM_DECK_TARGET_FPS} FPS cap.

For Steam Deck rear buttons, set Steam Input so L4 sends `F6` and R4 sends `F9`. DoomDeck binds `F6` to UZDoom quick save and `F9` to UZDoom quick load in both generated profiles.

## Classic Doom controls

Recommended Steam Deck layout for the `Vanilla Doom` preset:

- Left stick: movement.
- Right stick or right trackpad: horizontal turn only, low-to-moderate sensitivity.
- Right trigger: attack.
- A: use in-game and select in menus.
- B: back in menus.
- Left/right bumpers: weapon cycling.
- Menu/Start: open menu.
- L4: quick save, through a Steam Input `F6` mapping.
- R4: quick load, through a Steam Input `F9` mapping.
- Disable gyro and vertical mouse if you want a stricter classic feel.

The generated `configs/uzdoom/classic/autoexec.cfg` sets `freelook false`, `sv_allowjump false`, and `sv_allowcrouch false`.

## Modern Doom / Brutal Doom / Project Brutality controls

Recommended Steam Deck layout for the `UZDoom`, `Brutal Doom`, and `Project Brutality` presets:

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
- L4: quick save, through a Steam Input `F6` mapping.
- R4: quick load, through a Steam Input `F9` mapping.
- Optional gyro: mouse as gyro, active on right-stick touch or left trigger.

The generated `configs/uzdoom/modern/autoexec.cfg` enables freelook, jump, crouch, reload, alt-fire, quick save, and quick load bindings.
"""
    live_options_primary = doomrunner_options_paths(dirs)[0]
    doomrunner_guide = f"""# Doom Runner Setup Guide

DoomDeck installs the Windows builds of Doom Runner and UZDoom, copies Steam IWADs, creates Steam shortcuts that run through Proton, writes Doom Runner's generated options file, and writes a stable preset manifest:

`{live_options_primary}`

`{dirs.doomrunner_config / 'preset-manifest.json'}`

DoomDeck also writes a Doom Runner options copy into the generated Steam shortcut's Proton prefix when Steam shortcut creation is enabled.

Doom Runner should open through Steam/Proton with the generated UZDoom engine, IWADs, and presets already listed. Existing generated Doom Runner options are backed up under:

`{dirs.backups}`

## Initial Doom Runner check

1. Launch `Doom Runner` from Steam Gaming Mode.

2. Confirm this engine exists:

   - Engine name: `UZDoom`
   - Executable path: `{proton_windows_path(dirs.uzdoom / 'uzdoom.exe')}`
   - Engine family: `UZDoom` if shown, otherwise `ZDoom` / `GZDoom-family`
   - Config directory: `{proton_windows_path(dirs.uzdoom_config)}`
   - Data directory: `{proton_windows_path(dirs.root)}`

3. Confirm IWADs are listed from:

   `{dirs.iwads}`

4. Confirm the map directory is:

   `{dirs.pwads}`

   ModDB WAD archives installed with `doomdeck install-wads` are extracted here so they can be selected inside a preset.

5. Confirm these presets are listed:

"""
    for preset in manifest.get("presets", []):
        files = ", ".join(preset.get("files") or []) or "none"
        doomrunner_guide += f"- `{preset['name']}`\n  - IWAD: `{preset['iwad']}`\n  - Config: `{preset['config']}`\n  - Autoexec: `{preset['autoexec']}`\n  - Files/mods: `{files}`\n"
    doomrunner_guide += render_content_group_guide(manifest)
    doomrunner_guide += """
## Direct launchers

DoomDeck creates Steam shortcuts named `DoomDeck - <preset>` for one-click preset launches. The scripts in `launchers/` are helper placeholders that point you back to those Steam shortcuts so Windows UZDoom runs through Proton with Steam Input.
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
    logger.warning("Steam command not found; close Steam manually before modifying Steam shortcut and compatibility files")


def add_or_update_steam_shortcut(
    shortcuts_path: Path,
    appname: str,
    exe: Path,
    start_dir: Path,
    dirs: Dirs,
    args: argparse.Namespace,
    logger: logging.Logger,
    launch_options: str = "",
    match_exe: bool = True,
) -> int:
    if is_process_running(["steamwebhelper", "steam -", "/steam"]):
        if args.shutdown_steam:
            shutdown_steam(logger, args.dry_run)
        elif not args.allow_steam_running:
            raise DoomDeckError(
                "Steam appears to be running. Close Steam first, rerun with --shutdown-steam, "
                "or use --skip-steam-shortcut."
            )
        else:
            logger.warning("Steam appears to be running; modifying Steam shortcut and compatibility files anyway because --allow-steam-running was set")

    shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
    if shortcuts_path.exists():
        backup_path(shortcuts_path, dirs.backups, args.dry_run, logger, label="shortcuts.vdf")
    root = load_shortcuts(shortcuts_path)
    result = upsert_shortcut(root, appname, exe, start_dir, tags=["Doom", "Tools"], launch_options=launch_options, match_exe=match_exe)
    if result.created:
        logger.info("Add Steam shortcut %s at index %s in %s", appname, result.key, shortcuts_path)
    else:
        logger.info("Update existing Steam shortcut %s in %s", appname, shortcuts_path)
    atomic_write_bytes(shortcuts_path, BinaryVDF.dumps(root), args.dry_run, logger)
    compat_tool = getattr(args, "proton_compat_tool", "")
    if compat_tool:
        add_or_update_steam_compat_mapping(shortcuts_path.parent / "localconfig.vdf", result.appid, compat_tool, dirs, args, logger)
    return result.appid


def add_or_update_steam_compat_mapping(
    localconfig_path: Path,
    appid: int,
    compat_tool: str,
    dirs: Dirs,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    if localconfig_path.exists():
        backup_path(localconfig_path, dirs.backups, args.dry_run, logger, label="localconfig.vdf")
    logger.info("Set Steam compatibility tool for appid %s to %s in %s", appid, compat_tool, localconfig_path)
    root = load_text_vdf(localconfig_path)
    set_compat_tool_mapping(root, appid, compat_tool)
    atomic_write_text(localconfig_path, dumps_text_vdf(root), args.dry_run, logger)


def write_experimental_doomrunner_note(dirs: Dirs, args: argparse.Namespace, dry_run: bool, logger: logging.Logger) -> None:
    note: dict[str, object] = {
        "note": "Generated Doom Runner options.json copies are enabled by default.",
        "managed_options_json": str(doomrunner_options_paths(dirs)[0]),
        "managed_compatibility_options_json": str(doomrunner_options_paths(dirs)[1]),
        "backup_directory": str(dirs.backups),
        "generated_from": [
            str(dirs.doomrunner_config / "preset-manifest.json"),
            str(dirs.docs / "DOOM_RUNNER_SETUP.md"),
        ],
    }
    if args.experimental_doomrunner_config:
        note["experimental_requested"] = True
        note["result"] = "This flag is kept for compatibility; generated options.json copies are now written by default."
    atomic_write_text(dirs.doomrunner_config / "options-json-policy.json", json.dumps(note, indent=2) + "\n", dry_run, logger)


def install(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    steamos_ok, steamos_msg = detect_steamos()
    steam = discover_steam(args, logger)
    plan = build_install_plan(
        dirs=dirs,
        steam=steam,
        appid=APPID_DOOM_PLUS_DOOM_II,
        steamos_msg=steamos_msg,
        skip_steam_shortcut=args.skip_steam_shortcut,
    )
    print_plan("Planned install actions", plan.render_actions())

    if not steamos_ok:
        logger.warning("Environment warning: %s", steamos_msg)
    for directory in all_managed_dirs(dirs):
        ensure_dir(directory, args.dry_run, logger)

    install_windows_app_from_github(
        "Youda008/DoomRunner",
        dirs.doomrunner,
        "DoomRunner.exe",
        dirs,
        args,
        logger,
        explicit_url=args.doomrunner_asset_url,
    )
    install_windows_app_from_github(
        "UZDoom/UZDoom",
        dirs.uzdoom,
        "uzdoom.exe",
        dirs,
        args,
        logger,
        explicit_url=args.uzdoom_asset_url,
    )
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
    write_docs(dirs, manifest, brutal_path, project_brutality_path, args.dry_run, logger)
    write_experimental_doomrunner_note(dirs, args, args.dry_run, logger)

    extra_doomrunner_options_paths: list[Path] = []
    if not args.skip_steam_shortcut:
        if not steam.shortcuts_vdf:
            raise DoomDeckError("Could not locate Steam userdata/config/shortcuts.vdf path. Use --steam-root and/or --steam-user-id.")
        doomrunner_appid = add_or_update_steam_shortcut(
            steam.shortcuts_vdf,
            "Doom Runner",
            dirs.doomrunner / "DoomRunner.exe",
            dirs.doomrunner,
            dirs,
            args,
            logger,
        )
        proton_options = doomrunner_proton_options_path(steam, doomrunner_appid)
        if proton_options:
            extra_doomrunner_options_paths.append(proton_options)
        for preset in manifest.get("presets", []):
            add_or_update_steam_shortcut(
                steam.shortcuts_vdf,
                str(preset["steam_shortcut_name"]),
                dirs.uzdoom / "uzdoom.exe",
                dirs.uzdoom,
                dirs,
                args,
                logger,
                launch_options=str(preset["launch_options"]),
                match_exe=False,
            )
        logger.info("Restart Steam before expecting the non-Steam shortcut to appear in Gaming Mode")

    args.extra_doomrunner_options_paths = tuple(extra_doomrunner_options_paths)
    write_doomrunner_live_config(dirs, manifest, args, logger)

    report = validate_internal(args, dirs, steam, logger, print_report=True)
    return 1 if validation_has_failures(report) else 0


def install_wads(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    print_plan(
        "Planned WAD install actions",
        [
            f"Create/update WAD directories under {dirs.root}",
            "Download requested ModDB WAD archives into the PWAD map directory",
        ],
    )
    for directory in [dirs.root, dirs.configs, dirs.doomrunner_config, dirs.downloads, dirs.pwads, dirs.backups, dirs.logs]:
        ensure_dir(directory, args.dry_run, logger)

    moddb_wads = install_moddb_wad_urls(
        args.moddb_wad_urls,
        dirs.downloads,
        dirs.pwads,
        dirs.backups,
        args.dry_run,
        logger,
        force_download=args.force_download,
        user_agent=GITHUB_USER_AGENT,
    )
    if moddb_wads:
        logger.info("Installed ModDB WAD payloads: %s", ", ".join(str(path) for path in moddb_wads))
    else:
        logger.info("No ModDB WAD payloads installed")
    manifest = read_existing_preset_manifest(dirs)
    document = write_content_group_metadata(dirs, manifest, args.dry_run, logger)
    manifest_path = dirs.doomrunner_config / "preset-manifest.json"
    if manifest_path.exists():
        atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n", args.dry_run, logger)
    refresh_existing_doomrunner_content_groups(dirs, document["content_groups"], args.dry_run, logger)
    return 0


def validate(args: argparse.Namespace) -> int:
    dirs = build_dirs(expand_path(args.root))
    logger = configure_logging(dirs, args.verbose, args.dry_run)
    steam = discover_steam(args, logger)
    report = validate_internal(args, dirs, steam, logger, print_report=True)
    return 1 if validation_has_failures(report) else 0


def print_validation_report(items: Iterable[ValidationItem]) -> None:
    sys.stdout.write(format_validation_report(items))


def validate_internal(
    args: argparse.Namespace,
    dirs: Dirs,
    steam: SteamInfo,
    logger: logging.Logger,
    print_report: bool = False,
) -> list[ValidationItem]:
    def shell_syntax_checker(script: Path) -> bool:
        return run_command(["bash", "-n", str(script)], logger, dry_run=args.dry_run, timeout=10).returncode == 0

    validator = InstallationValidator(
        steamos_detector=detect_steamos,
        shell_syntax_checker=shell_syntax_checker,
        steam_appid=APPID_DOOM_PLUS_DOOM_II,
    )
    items = validator.validate(dirs, steam)

    if print_report:
        print_validation_report(items)
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
    write_tree_tar_gz(archive, dirs.root, exclude_dirs=[dirs.backups])
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
        write_tree_tar_gz(archive, dirs.root, include_root=True)
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


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help=f"Managed Doom root directory (default: {DEFAULT_ROOT})")
    parser.add_argument("--steam-root", help="Steam root override, e.g. ~/.local/share/Steam")
    parser.add_argument("--steam-user-id", help="Steam userdata numeric ID override")
    parser.add_argument("--dry-run", action="store_true", help="Print and log intended changes without writing files")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging to console")


def add_moddb_wad_url_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        dest="moddb_wad_urls",
        metavar="moddb_url",
        nargs="+",
        help="ModDB add-on/file page URL to download and extract .wad/.pk3 map payloads into pwads/",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up Doom Runner, UZDoom, IWADs, launchers, and Steam integration on Steam Deck.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="Install/update the managed Doom setup")
    add_common_args(install_parser)
    install_parser.add_argument("--skip-downloads", action="store_true", help="Do not download Windows tools or managed mod archives; reuse files already in place")
    install_parser.add_argument("--force-download", action="store_true", help="Redownload release assets and managed mod archives even if present in downloads/")
    install_parser.add_argument("--doomrunner-asset-url", help="Explicit Doom Runner Windows ZIP URL override")
    install_parser.add_argument("--uzdoom-asset-url", help="Explicit UZDoom Windows ZIP URL override")
    install_parser.add_argument("--brutal-doom-url", help="Explicit Brutal Doom .pk3/.zip download URL override")
    install_parser.add_argument("--project-brutality-url", help="Explicit Project Brutality .pk3/.zip download URL override")
    install_parser.add_argument("--prefer-legacy-appimage", action="store_true", help="Deprecated compatibility flag; Windows ZIP assets are now used")
    install_parser.add_argument(
        "--proton-compat-tool",
        default="proton_10",
        help="Steam compatibility tool name to force for generated Windows shortcuts",
    )
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
    install_parser.add_argument("--skip-steam-shortcut", action="store_true", help="Do not modify Steam shortcuts.vdf or Proton compatibility mapping")
    install_parser.add_argument("--skip-doomrunner-live-config", action="store_true", help="Do not write Doom Runner generated options.json copies")
    install_parser.add_argument("--shutdown-steam", action="store_true", help="Attempt to shut down Steam before modifying shortcut and compatibility files")
    install_parser.add_argument("--allow-steam-running", action="store_true", help="Modify Steam shortcut and compatibility files even if Steam appears to be running")
    install_parser.add_argument(
        "--experimental-doomrunner-config",
        action="store_true",
        help="Deprecated compatibility flag; generated Doom Runner options.json copies are now written by default",
    )
    install_parser.set_defaults(func=install)

    install_wads_parser = subparsers.add_parser("install-wads", help="Install/update ModDB WAD archives only")
    add_common_args(install_wads_parser)
    install_wads_parser.add_argument("--force-download", action="store_true", help="Redownload WAD archives even if present in downloads/")
    add_moddb_wad_url_args(install_wads_parser)
    install_wads_parser.set_defaults(func=install_wads)

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
