from __future__ import annotations

from doomdeck.application.presets import build_preset_manifest
from doomdeck.domain.models import DoomDeckError
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD, InstalledModMetadata
from doomdeck.domain.paths import build_dirs
from doomdeck.domain.downloads import DownloadPolicy


def test_managed_mods_define_canonical_aliases_and_metadata_paths(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")

    assert BRUTAL_DOOM_MOD.alias_path(dirs.brutal) == dirs.brutal / "brutal-doom.pk3"
    assert BRUTAL_DOOM_MOD.metadata_path(dirs.brutal) == dirs.brutal / "brutal-doom.json"
    assert PROJECT_BRUTALITY_MOD.alias_path(dirs.project_brutality) == dirs.project_brutality / "project-brutality.pk3"
    assert PROJECT_BRUTALITY_MOD.metadata_path(dirs.project_brutality) == dirs.project_brutality / "project-brutality.json"


def test_installed_mod_metadata_keeps_source_provenance_explicit(tmp_path) -> None:
    installed = tmp_path / "brutal-doom.pk3"

    metadata = InstalledModMetadata(
        mod=BRUTAL_DOOM_MOD,
        installed=installed,
        source_sha256="source-sha",
        installed_sha256="installed-sha",
        payload_member="BrutalDoom.pk3",
        source={"source_type": "moddb", "source_page_url": "https://www.moddb.com/mods/brutal-doom"},
    ).as_json_object()

    assert metadata["name"] == "Brutal Doom"
    assert metadata["installed"] == str(installed)
    assert metadata["source_sha256"] == "source-sha"
    assert metadata["installed_sha256"] == "installed-sha"
    assert metadata["payload_member"] == "BrutalDoom.pk3"
    assert metadata["source_type"] == "moddb"
    assert "generated_at" in metadata


def test_download_policy_uses_https_and_host_allowlists() -> None:
    policy = DownloadPolicy.for_hosts({"moddb.com"})

    policy.validate_url("https://www.moddb.com/downloads/mirror/123")

    try:
        policy.validate_url("http://www.moddb.com/downloads/mirror/123")
    except DoomDeckError as exc:
        assert "must use https" in str(exc)
    else:
        raise AssertionError("expected non-https URL to be rejected")

    try:
        policy.validate_url("https://example.test/file.pk3")
    except DoomDeckError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("expected untrusted host to be rejected")


def test_preset_manifest_uses_managed_mod_identities(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")
    dirs.brutal.mkdir(parents=True)
    dirs.project_brutality.mkdir(parents=True)
    (dirs.brutal / "brutal-doom.pk3").write_bytes(b"brutal")
    (dirs.project_brutality / "project-brutality.pk3").write_bytes(b"project-brutality")

    manifest = build_preset_manifest(dirs, None, None)

    presets = {preset["name"]: preset for preset in manifest["presets"]}
    assert presets["Brutal Doom"]["files"] == [str(dirs.brutal / "brutal-doom.pk3")]
    assert presets["Project Brutality"]["files"] == [str(dirs.project_brutality / "project-brutality.pk3")]
    assert manifest["schema"] == "doom-deck-setup/preset-manifest/v1"
