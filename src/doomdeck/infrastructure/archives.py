"""Archive handling helpers used by DoomDeck installers and backups."""
from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, Optional

from doomdeck.domain.models import DoomDeckError


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


def path_is_or_is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def write_tree_tar_gz(
    archive_path: Path,
    root: Path,
    exclude_dirs: Iterable[Path] = (),
    include_root: bool = False,
) -> None:
    excluded = tuple(exclude_dirs)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        if include_root:
            archive.add(root, arcname=root.name, recursive=False)
        for item in root.rglob("*"):
            if item == archive_path or any(path_is_or_is_under(item, excluded_dir) for excluded_dir in excluded):
                continue
            archive.add(item, arcname=item.relative_to(root.parent), recursive=False)


def safe_extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    validated: list[tuple[tarfile.TarInfo, Path]] = []
    for member in tar.getmembers():
        parts = PurePosixPath(member.name).parts
        if PurePosixPath(member.name).is_absolute():
            raise DoomDeckError(f"Unsafe absolute path in tar archive: {member.name}")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise DoomDeckError(f"Unsafe path in tar archive: {member.name}")
        member_path = dest.joinpath(*parts).resolve()
        if not path_is_or_is_under(member_path, dest):
            raise DoomDeckError(f"Unsafe path in tar archive: {member.name}")
        if member.issym() or member.islnk():
            raise DoomDeckError(f"Unsafe link in tar archive: {member.name}")
        if not member.isfile() and not member.isdir():
            raise DoomDeckError(f"Unsafe special file in tar archive: {member.name}")
        validated.append((member, member_path))

    for member, member_path in validated:
        if member.isdir():
            member_path.mkdir(parents=True, exist_ok=True)
            continue
        source = tar.extractfile(member)
        if source is None:
            raise DoomDeckError(f"Could not read tar archive member: {member.name}")
        member_path.parent.mkdir(parents=True, exist_ok=True)
        with source, member_path.open("wb") as dest_handle:
            shutil.copyfileobj(source, dest_handle)
        os.chmod(member_path, member.mode & 0o755)
