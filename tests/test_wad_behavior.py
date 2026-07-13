from __future__ import annotations

import logging

from doomdeck.application.wads import copy_addon_wads
from doomdeck.application.wads import find_wads_in_install, score_iwad_candidate
from doomdeck.domain.paths import build_dirs
from doomdeck.domain.wads import iwad_dest_name


def test_iwad_destination_names_match_doom_file_conventions() -> None:
    assert iwad_dest_name("doom2.wad") == "DOOM2.WAD"


def test_iwad_candidate_scoring_prefers_rerelease_base_files(tmp_path) -> None:
    preferred = tmp_path / "rerelease" / "base" / "doom2.wad"
    lower_quality = tmp_path / "soundtrack" / "doom2.wad"
    preferred.parent.mkdir(parents=True)
    lower_quality.parent.mkdir(parents=True)
    preferred.write_bytes(b"x" * 1_000_001)
    lower_quality.write_bytes(b"x" * 1_000_001)

    assert score_iwad_candidate(preferred) > score_iwad_candidate(lower_quality)


def test_wad_discovery_separates_iwads_from_addon_wads_and_skips_support_archives(tmp_path) -> None:
    install_dir = tmp_path / "steam" / "DOOM + DOOM II"
    (install_dir / "rerelease" / "base").mkdir(parents=True)
    (install_dir / "mods").mkdir(parents=True)
    (install_dir / "support").mkdir(parents=True)
    (install_dir / "rerelease" / "base" / "doom2.wad").write_bytes(b"x" * 1_000_001)
    (install_dir / "mods" / "sigil.wad").write_bytes(b"addon")
    (install_dir / "support" / "dosbox.wad").write_bytes(b"support")

    iwads, pwads = find_wads_in_install(install_dir, logging.getLogger("test"))

    assert iwads == {"doom2.wad": (install_dir / "rerelease" / "base" / "doom2.wad").resolve()}
    assert pwads == {"sigil.wad": (install_dir / "mods" / "sigil.wad").resolve()}


def test_copy_addon_wads_preserves_existing_custom_wad_with_same_name(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.pwads.mkdir(parents=True)
    steam_addon = tmp_path / "steam" / "mods" / "sigil.wad"
    steam_addon.parent.mkdir(parents=True)
    steam_addon.write_bytes(b"steam addon bytes")
    existing_custom = dirs.pwads / "SIGIL.WAD"
    existing_custom.write_bytes(b"user custom bytes")

    copy_addon_wads({"sigil.wad": steam_addon}, dirs, dry_run=False, logger=logging.getLogger("test"))

    assert existing_custom.read_bytes() == b"user custom bytes"
    assert not any(dirs.backups.glob("SIGIL.WAD*"))
