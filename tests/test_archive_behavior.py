from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.archives import (
    choose_payload_member,
    common_zip_toplevel,
    normalized_zip_member_name,
    safe_extract_tar,
    zip_contains_markers,
)


def test_zip_member_names_drop_a_shared_archive_folder() -> None:
    names = [
        "Project_Brutality-master/gameinfo.txt",
        "Project_Brutality-master/zscript.zc",
    ]

    prefix = common_zip_toplevel(names)

    assert prefix == "Project_Brutality-master"
    assert normalized_zip_member_name(names[0], prefix) == "gameinfo.txt"
    assert normalized_zip_member_name(names[1], prefix) == "zscript.zc"


def test_zip_member_names_reject_path_traversal() -> None:
    assert normalized_zip_member_name("../outside.pk3", None) is None
    assert normalized_zip_member_name("folder/../../outside.pk3", "folder") is None


def test_zip_contains_markers_matches_case_insensitively_under_common_folder(tmp_path) -> None:
    archive_path = tmp_path / "project-brutality.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Project_Brutality-master/GameInfo.txt", "")
        archive.writestr("Project_Brutality-master/ZScript.zc", "")

    assert zip_contains_markers(archive_path, {"gameinfo.txt", "zscript.zc"})


def test_payload_selection_prefers_primary_brutal_doom_pk3() -> None:
    infos = [
        zipfile.ZipInfo("docs/readme.pk3"),
        zipfile.ZipInfo("extras/optional.wad"),
        zipfile.ZipInfo("BrutalDoom.pk3"),
    ]

    selected = choose_payload_member(infos)

    assert selected is not None
    assert selected.filename == "BrutalDoom.pk3"


def test_safe_tar_extraction_rejects_members_outside_destination(tmp_path) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"owned"
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(DoomDeckError, match="Unsafe path in tar archive"):
            safe_extract_tar(archive, tmp_path / "restore")
