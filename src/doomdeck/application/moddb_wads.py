"""Application services for installing WAD payloads downloaded from ModDB."""
from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from typing import BinaryIO, Callable, Optional

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.archives import common_zip_toplevel, normalized_zip_member_name
from doomdeck.infrastructure.downloads import DEFAULT_USER_AGENT, download_url
from doomdeck.infrastructure.files import backup_path, files_equal
from doomdeck.infrastructure.moddb import select_moddb_wad_download

MODDB_WAD_PAYLOAD_SUFFIXES = {".wad", ".pk3"}


def _install_moddb_wad_payload(
    payload_name: str,
    write_payload: Callable[[BinaryIO], None],
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
) -> Optional[Path]:
    dest = dest_dir / Path(payload_name).name.upper()
    logger.info("Install ModDB WAD payload: %s -> %s", payload_name, dest)
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with tmp.open("wb") as handle:
            write_payload(handle)
        if dest.exists() and files_equal(tmp, dest):
            tmp.unlink()
            logger.info("ModDB WAD payload already installed: %s", dest)
            return dest
        if dest.exists():
            backup_path(dest, backups_dir, dry_run, logger, label=dest.name)
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return dest


def _install_direct_moddb_wad_payload(
    src: Path,
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
) -> list[Path]:
    def copy_direct_payload(handle: BinaryIO) -> None:
        with src.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, handle)

    installed = _install_moddb_wad_payload(src.name, copy_direct_payload, dest_dir, backups_dir, dry_run, logger)
    return [installed] if installed else []


def _moddb_wad_zip_payload_infos(src: Path, source_zip: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    infos = [info for info in source_zip.infolist() if not info.is_dir()]
    prefix = common_zip_toplevel(info.filename for info in infos)
    payload_infos: list[tuple[zipfile.ZipInfo, str]] = []
    for info in infos:
        raw_suffix = Path(info.filename).suffix.lower()
        if raw_suffix not in MODDB_WAD_PAYLOAD_SUFFIXES:
            continue
        normalized = normalized_zip_member_name(info.filename, prefix)
        if normalized is None:
            raise DoomDeckError(f"Unsafe path in ModDB WAD archive: {info.filename}")
        payload_infos.append((info, normalized))
    if not payload_infos:
        raise DoomDeckError(f"ModDB WAD archive has no .wad/.pk3 payload: {src}")
    return payload_infos


def _install_moddb_wad_zip(
    src: Path,
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
) -> list[Path]:
    installed: list[Path] = []
    with zipfile.ZipFile(src) as source_zip:
        for info, normalized in _moddb_wad_zip_payload_infos(src, source_zip):

            def copy_zip_payload(handle: BinaryIO, member: zipfile.ZipInfo = info) -> None:
                with source_zip.open(member) as source_handle:
                    shutil.copyfileobj(source_handle, handle)

            installed_path = _install_moddb_wad_payload(
                normalized,
                copy_zip_payload,
                dest_dir,
                backups_dir,
                dry_run,
                logger,
            )
            if installed_path:
                installed.append(installed_path)
    return installed


def install_moddb_wad_archive(
    src: Path,
    dest_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
) -> list[Path]:
    if not src.exists() and not dry_run:
        raise DoomDeckError(f"ModDB WAD download is missing: {src}")

    if src.suffix.lower() in MODDB_WAD_PAYLOAD_SUFFIXES:
        return _install_direct_moddb_wad_payload(src, dest_dir, backups_dir, dry_run, logger)

    if not zipfile.is_zipfile(src):
        raise DoomDeckError(f"ModDB WAD file should be a .wad/.pk3/.zip, got: {src}")

    return _install_moddb_wad_zip(src, dest_dir, backups_dir, dry_run, logger)


def install_moddb_wad_urls(
    page_urls: list[str],
    downloads_dir: Path,
    pwads_dir: Path,
    backups_dir: Path,
    dry_run: bool,
    logger: logging.Logger,
    force_download: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[Path]:
    installed: list[Path] = []
    for page_url in page_urls:
        selected = select_moddb_wad_download(page_url, logger, user_agent=user_agent)
        download_dest = downloads_dir / selected.filename
        downloaded = download_url(
            selected.download_url,
            download_dest,
            dry_run,
            logger,
            force=force_download,
            headers={"Referer": selected.page_url},
            allowed_hosts={"moddb.com"},
            expected_md5=selected.md5 or None,
            user_agent=user_agent,
        )
        installed.extend(install_moddb_wad_archive(downloaded, pwads_dir, backups_dir, dry_run, logger))
    return installed
