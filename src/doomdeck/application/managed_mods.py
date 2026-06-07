"""Managed mod installation use cases."""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Iterable, Mapping

from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, InstalledModMetadata, ModSource
from doomdeck.infrastructure.archives import (
    choose_payload_member,
    common_zip_toplevel,
    normalized_zip_member_name,
    zip_contains_markers,
)
from doomdeck.infrastructure.downloads import sha256_file
from doomdeck.infrastructure.files import atomic_write_text, backup_path

SourceMetadata = Mapping[str, str] | ModSource


def metadata_matches(metadata_path: Path, expected: dict[str, str], keys: Iterable[str]) -> bool:
    if not metadata_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return all(str(metadata.get(key, "")) == str(expected.get(key, "")) for key in keys)


def install_project_brutality_archive(
    src: Path,
    dest: Path,
    backups_dir: Path,
    metadata_path: Path,
    dry_run: bool,
    logger: logging.Logger,
    source: SourceMetadata,
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
        _repack_project_brutality_zip(src, dest)

    metadata = InstalledModMetadata(
        mod=PROJECT_BRUTALITY_MOD,
        installed=dest,
        source_sha256=source_sha,
        source=source,
    ).as_json_object()
    atomic_write_text(metadata_path, json.dumps(metadata, indent=2) + "\n", dry_run, logger)
    return dest


def _repack_project_brutality_zip(src: Path, dest: Path) -> None:
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


def install_brutal_doom_archive(
    src: Path,
    dest: Path,
    backups_dir: Path,
    metadata_path: Path,
    dry_run: bool,
    logger: logging.Logger,
    source: SourceMetadata,
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

    payload_member = _install_brutal_doom_payload(src, dest)

    metadata = InstalledModMetadata(
        mod=BRUTAL_DOOM_MOD,
        installed=dest,
        installed_sha256=sha256_file(dest),
        payload_member=payload_member,
        source_sha256=source_sha,
        source=source,
    ).as_json_object()
    atomic_write_text(metadata_path, json.dumps(metadata, indent=2) + "\n", dry_run, logger)
    return dest


def _install_brutal_doom_payload(src: Path, dest: Path) -> str:
    payload_member = ""
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        if src.suffix.lower() in {".pk3", ".wad"}:
            shutil.copy2(src, tmp)
        elif zipfile.is_zipfile(src):
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
        else:
            raise DoomDeckError(f"Brutal Doom file should be a .pk3/.wad/.zip, got: {src}")
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return payload_member
