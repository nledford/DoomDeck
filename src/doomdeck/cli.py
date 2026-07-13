#!/usr/bin/env python3
"""
DoomDeck CLI

Steam Deck Doom modding setup automation for:
- Steam DOOM + DOOM II app 2280 IWAD discovery/copy
- Windows Doom Runner installation for Proton
- Windows UZDoom installation for Proton
- Brutal Doom manual-drop validation
- Steam non-Steam shortcut integration for Doom Runner
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
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, Optional

from doomdeck import __version__
from doomdeck.application.doomrunner import (
    DoomRunnerLiveConfigSettings,
    doomrunner_options_paths,
    write_doomrunner_live_config,
)
from doomdeck.application.docs import write_docs
from doomdeck.application.install import build_install_plan
from doomdeck.application.launchers import (
    read_existing_preset_manifest,
    refresh_existing_doomrunner_content_groups,
    write_content_group_metadata,
    write_launchers_and_manifest,
)
from doomdeck.application.managed_mods import (
    install_brutal_doom_archive,
    install_project_brutality_archive,
    installed_payload_matches,
    metadata_matches,
)
from doomdeck.application.moddb_wads import install_moddb_wad_urls
from doomdeck.application.release_assets import fetch_windows_release_asset
from doomdeck.application.restore import restore_backup_archive
from doomdeck.application.self_update import (
    DEFAULT_SELF_UPDATE_REF,
    DEFAULT_SELF_UPDATE_REPO_URL,
    build_github_commit_api_url,
    build_self_update_archive_url,
    build_self_update_plan,
    find_extracted_self_update_source_dir,
    infer_source_install_dir,
    prepare_self_update_runtime,
    replace_self_update_install_dir,
    validate_self_update_source_dir,
)
from doomdeck.application.steam import (
    SteamShortcutSettings,
    add_or_update_doomrunner_shortcut,
    doomrunner_proton_options_path,
)
from doomdeck.application.steam_discovery import (
    DOOM_PLUS_DOOM_II_APP_ID as APPID_DOOM_PLUS_DOOM_II,
    SteamDiscoverySettings,
    detect_steamos,
    discover_steam,
)
from doomdeck.application.steam_input import deploy_steam_input_profile, write_managed_steam_input_profile
from doomdeck.application.uzdoom import write_uzdoom_configs
from doomdeck.application.validation import InstallationValidator, format_validation_report, validation_has_failures
from doomdeck.application.wads import copy_addon_wads, copy_iwads, find_wads_in_install
from doomdeck.domain.models import DoomDeckError, Dirs, GitHubAsset, SteamInfo, ValidationItem
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, ModSource
from doomdeck.domain.paths import all_managed_dirs, build_dirs, expand_path
from doomdeck.infrastructure.archives import (
    safe_extract_tar,
    safe_extract_zip,
    write_tree_tar_gz,
)
from doomdeck.infrastructure.downloads import download_url as _download_url
from doomdeck.infrastructure.files import (
    atomic_write_text,
    backup_path,
)
from doomdeck.infrastructure.github_api import (
    request_github_json,
    validate_github_commit_payload,
    validate_github_release_payload,
    validate_github_repository_payload,
)
from doomdeck.infrastructure.moddb import (
    BRUTAL_DOOM_MODDB_URL,
    safe_download_name,
    select_brutal_doom_download,
)

DEFAULT_ROOT = Path.home() / "Games" / "Doom"
SCRIPT_VERSION = "2026.05.31"

BRUTAL_DOOM_ALIAS = BRUTAL_DOOM_MOD.alias
PROJECT_BRUTALITY_REPO = "pa1nki113r/Project_Brutality"
GITHUB_USER_AGENT = f"doomdeck/{SCRIPT_VERSION}"


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


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


def configure_console_logging(verbose: bool) -> logging.Logger:
    logger = logging.getLogger("doom_deck_setup")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)
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
        expected_sha256 = None
        allowed_hosts = None
    else:
        asset = fetch_windows_release_asset(repo, logger, GITHUB_USER_AGENT)
        if not asset.sha256:
            raise DoomDeckError(f"GitHub release asset for {repo} did not include a SHA-256 digest: {asset.name}")
        asset_name = safe_download_name(asset.name, f"{repo.split('/')[-1]}.zip")
        url = asset.url
        expected_size = asset.size
        expected_sha256 = asset.sha256
        allowed_hosts = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
    downloaded = download_url(
        url,
        dirs.downloads / asset_name,
        args.dry_run,
        logger,
        force=args.force_download,
        allowed_hosts=allowed_hosts,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
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
        release_payload = request_github_json(
            f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/releases/latest",
            GITHUB_USER_AGENT,
        )
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
    if ranked and score(ranked[0]) > 0 and ranked[0].digest:
        chosen = ranked[0]
        logger.info("Selected Project Brutality release asset: %s", chosen.name)
        return GitHubAsset(
            name=chosen.name,
            url=chosen.browser_download_url,
            size=chosen.size,
            tag_name=tag_name,
            sha256=chosen.digest.removeprefix("sha256:") if chosen.digest else None,
        )

    ref = release.label if release_payload else ""
    if not ref:
        repo_meta = validate_github_repository_payload(
            request_github_json(
                f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}",
                GITHUB_USER_AGENT,
            ),
            PROJECT_BRUTALITY_REPO,
        )
        ref = repo_meta.default_branch or "master"
        tag_name = ref
    commit = validate_github_commit_payload(
        request_github_json(
            f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/commits/{urllib.parse.quote(ref, safe='')}",
            GITHUB_USER_AGENT,
        ),
        PROJECT_BRUTALITY_REPO,
    )
    zipball_url = f"https://api.github.com/repos/{PROJECT_BRUTALITY_REPO}/zipball/{commit.sha}"
    fallback_name = f"Project_Brutality-{safe_download_name(tag_name, 'latest')}-{commit.sha}.zip"
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
        expected_sha256 = None
        allowed_hosts = None
    else:
        asset = select_project_brutality_download(logger)
        url = asset.url
        asset_name = safe_download_name(asset.name, "Project_Brutality.zip")
        tag_name = asset.tag_name
        expected_size = asset.size
        expected_sha256 = asset.sha256
        allowed_hosts = {
            "api.github.com",
            "github.com",
            "objects.githubusercontent.com",
            "release-assets.githubusercontent.com",
        }
    downloaded = download_url(
        url,
        dirs.downloads / asset_name,
        dry_run,
        logger,
        force=args.force_download,
        allowed_hosts=allowed_hosts,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
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
    already_current = (
        canonical.exists()
        and metadata_matches(metadata_path, source.as_metadata(), compare_keys)
        and installed_payload_matches(canonical, metadata_path)
    )
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
    steam = discover_steam(SteamDiscoverySettings(args.steam_root, args.steam_user_id), logger)
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
    write_managed_steam_input_profile(dirs, args.dry_run, logger)

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
    write_docs(
        dirs,
        manifest,
        brutal_path,
        project_brutality_path,
        args.dry_run,
        logger,
        appid=APPID_DOOM_PLUS_DOOM_II,
        brutal_doom_source_url=BRUTAL_DOOM_MODDB_URL,
        project_brutality_repo=PROJECT_BRUTALITY_REPO,
    )
    write_experimental_doomrunner_note(dirs, args, args.dry_run, logger)

    extra_doomrunner_options_paths: list[Path] = []
    if not args.skip_steam_shortcut:
        if not steam.shortcuts_vdf:
            raise DoomDeckError("Could not locate Steam userdata/config/shortcuts.vdf path. Use --steam-root and/or --steam-user-id.")
        shortcut_settings = SteamShortcutSettings(
            dry_run=args.dry_run,
            allow_steam_running=args.allow_steam_running,
            shutdown_steam=args.shutdown_steam,
            proton_compat_tool=args.proton_compat_tool,
        )
        doomrunner_appid = add_or_update_doomrunner_shortcut(
            steam.shortcuts_vdf,
            dirs,
            shortcut_settings,
            logger,
        )
        proton_options = doomrunner_proton_options_path(steam, doomrunner_appid)
        if proton_options:
            extra_doomrunner_options_paths.append(proton_options)
        deploy_steam_input_profile(dirs, steam, doomrunner_appid, args.dry_run, logger)
        logger.info("Restart Steam before expecting the non-Steam shortcut to appear in Gaming Mode")

    write_doomrunner_live_config(
        dirs,
        manifest,
        DoomRunnerLiveConfigSettings(
            dry_run=args.dry_run,
            skip=args.skip_doomrunner_live_config,
            extra_options_paths=tuple(extra_doomrunner_options_paths),
        ),
        logger,
    )

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
    steam = discover_steam(SteamDiscoverySettings(args.steam_root, args.steam_user_id), logger)
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
    staging = dirs.root.parent / f".{dirs.root.name}.restore-{now_stamp()}"
    actions = [f"Extract and validate {archive} under staging path {staging}", f"Activate restored root at {dirs.root}"]
    if dirs.root.exists():
        actions.insert(0, f"Move existing {dirs.root} to {replaced}")
    print_plan("Planned restore actions", actions)
    if args.dry_run:
        return 0
    restore_backup_archive(archive, dirs.root, replaced, staging, logger)
    logger.info("Restore completed from %s", archive)
    return 0


def resolve_self_update_install_dir(explicit_install_dir: Optional[str]) -> Path:
    if explicit_install_dir:
        return expand_path(explicit_install_dir)
    env_install_dir = os.environ.get("DOOMDECK_INSTALL_DIR")
    if env_install_dir:
        return expand_path(env_install_dir)
    return infer_source_install_dir(Path(__file__))


def self_update_archive_allowed_hosts(archive_url: str, explicit_archive_url: Optional[str]) -> Optional[set[str]]:
    if explicit_archive_url:
        return None
    hostname = (urllib.parse.urlparse(archive_url).hostname or "").lower()
    return {hostname} if hostname else None


def smoke_test_self_update_source(
    source_dir: Path,
    logger: logging.Logger,
    python_executable: Path | None = None,
) -> None:
    env = os.environ.copy()
    src_path = str(source_dir / "src")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_path
    cmd = [str(python_executable or sys.executable), "-m", "doomdeck", "--help"]
    logger.debug("Run self-update smoke test: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=env,
    )
    if result.returncode != 0:
        raise DoomDeckError(
            "Downloaded DoomDeck source failed its import smoke test "
            f"({result.returncode}).\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def self_update(args: argparse.Namespace) -> int:
    logger = configure_console_logging(args.verbose)
    install_dir = resolve_self_update_install_dir(args.install_dir)
    archive_url = build_self_update_archive_url(args.repo_url, args.ref, args.archive_url)
    if not args.archive_url:
        commit = validate_github_commit_payload(
            request_github_json(
                build_github_commit_api_url(args.repo_url, args.ref),
                GITHUB_USER_AGENT,
            ),
            args.repo_url,
        )
        archive_url = build_self_update_archive_url(args.repo_url, commit.sha)
    plan = build_self_update_plan(install_dir, archive_url)
    validate_self_update_source_dir(install_dir)

    if args.check:
        print_plan(
            "DoomDeck self-update check",
            [
                f"Current version: {__version__}",
                f"Current source: {install_dir}",
                f"Update archive: {archive_url}",
                "Current source directory looks like a managed source-archive install",
            ],
        )
        return 0

    print_plan("Planned self-update actions", plan.render_actions())
    if args.dry_run:
        return 0

    with tempfile.TemporaryDirectory(prefix="doomdeck-self-update.") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "doomdeck.tar.gz"
        extract_dir = temp_root / "extract"
        staged_install_dir = temp_root / "source"
        extract_dir.mkdir(parents=True, exist_ok=True)

        download_url(
            archive_url,
            archive_path,
            False,
            logger,
            force=True,
            allowed_hosts=self_update_archive_allowed_hosts(archive_url, args.archive_url),
        )
        with tarfile.open(archive_path, "r:gz") as archive:
            safe_extract_tar(archive, extract_dir)
        source_dir = find_extracted_self_update_source_dir(extract_dir)
        shutil.copytree(source_dir, staged_install_dir)
        venv_python = prepare_self_update_runtime(staged_install_dir, Path(sys.executable), logger)
        smoke_test_self_update_source(staged_install_dir, logger, venv_python)
        replace_self_update_install_dir(staged_install_dir, install_dir)

    logger.info("Updated DoomDeck source install at %s", install_dir)
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
        help="Steam compatibility tool name to force for the generated Doom Runner shortcut",
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

    self_update_parser = subparsers.add_parser("self-update", help="Update the DoomDeck command installed by install.sh")
    self_update_parser.add_argument("--check", action="store_true", help="Show the current source path and update archive without downloading")
    self_update_parser.add_argument("--dry-run", action="store_true", help="Print intended update actions without downloading or writing files")
    self_update_parser.add_argument("--verbose", action="store_true", help="Enable debug logging to console")
    self_update_parser.add_argument(
        "--repo-url",
        default=DEFAULT_SELF_UPDATE_REPO_URL,
        help="GitHub repository URL used to build the default source archive URL",
    )
    self_update_parser.add_argument(
        "--ref",
        default=DEFAULT_SELF_UPDATE_REF,
        help="Branch name used to build the default source archive URL",
    )
    self_update_parser.add_argument("--archive-url", help="Explicit DoomDeck source archive URL override")
    self_update_parser.add_argument("--install-dir", help="DoomDeck source install directory override")
    self_update_parser.set_defaults(func=self_update)

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
