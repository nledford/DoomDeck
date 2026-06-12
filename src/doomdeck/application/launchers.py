"""Generate DoomDeck preset launchers and manifest metadata."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from doomdeck.application.content_groups import build_content_group_document
from doomdeck.application.doomrunner import doomrunner_options_paths
from doomdeck.application.presets import build_preset_manifest
from doomdeck.application.proton import build_uzdoom_launch_options
from doomdeck.domain.models import Dirs
from doomdeck.infrastructure.files import atomic_write_text, backup_path


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


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
