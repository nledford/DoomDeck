from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from doomdeck.application.self_update import (
    DEFAULT_SELF_UPDATE_REF,
    DEFAULT_SELF_UPDATE_REPO_URL,
    build_self_update_archive_url,
    infer_source_install_dir,
    validate_self_update_source_dir,
)
from doomdeck.cli import main
from doomdeck.domain.models import DoomDeckError


def test_default_self_update_archive_url_points_at_github_branch_archive() -> None:
    assert (
        build_self_update_archive_url(DEFAULT_SELF_UPDATE_REPO_URL, DEFAULT_SELF_UPDATE_REF)
        == "https://github.com/nledford/DoomDeck/archive/refs/heads/master.tar.gz"
    )


def test_explicit_self_update_archive_url_wins() -> None:
    assert (
        build_self_update_archive_url(
            "https://github.com/example/project",
            "main",
            "https://downloads.example.test/doomdeck.tar.gz",
        )
        == "https://downloads.example.test/doomdeck.tar.gz"
    )


def test_infer_source_install_dir_from_loaded_cli_module_path() -> None:
    module_file = Path("/home/deck/.local/share/doomdeck/source/src/doomdeck/cli.py")

    assert infer_source_install_dir(module_file) == Path("/home/deck/.local/share/doomdeck/source")


def test_validate_self_update_source_dir_accepts_installer_layout(tmp_path: Path) -> None:
    install_dir = tmp_path / "source"
    (install_dir / "src" / "doomdeck").mkdir(parents=True)
    (install_dir / "pyproject.toml").write_text("[project]\nname = 'doomdeck'\n", encoding="utf-8")

    validate_self_update_source_dir(install_dir)


def test_validate_self_update_source_dir_rejects_git_checkout(tmp_path: Path) -> None:
    install_dir = tmp_path / "checkout"
    (install_dir / ".git").mkdir(parents=True)
    (install_dir / "src" / "doomdeck").mkdir(parents=True)
    (install_dir / "pyproject.toml").write_text("[project]\nname = 'doomdeck'\n", encoding="utf-8")

    with pytest.raises(DoomDeckError, match="git pull"):
        validate_self_update_source_dir(install_dir)


def test_self_update_replaces_managed_source_from_downloaded_archive(tmp_path: Path) -> None:
    install_dir = tmp_path / "source"
    (install_dir / "src" / "doomdeck").mkdir(parents=True)
    (install_dir / "pyproject.toml").write_text("[project]\nname = 'doomdeck'\n", encoding="utf-8")
    (install_dir / "old.txt").write_text("old\n", encoding="utf-8")

    archive_source = tmp_path / "archive-source" / "DoomDeck-main"
    (archive_source / "src" / "doomdeck").mkdir(parents=True)
    (archive_source / "pyproject.toml").write_text("[project]\nname = 'doomdeck'\n", encoding="utf-8")
    (archive_source / "src" / "doomdeck" / "__init__.py").write_text("", encoding="utf-8")
    (archive_source / "src" / "doomdeck" / "__main__.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (archive_source / "new.txt").write_text("new\n", encoding="utf-8")
    archive_path = tmp_path / "doomdeck.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(archive_source, arcname="DoomDeck-main")

    def fake_download(url, dest, dry_run, logger, **kwargs):
        shutil.copy2(archive_path, dest)
        return dest

    with patch("doomdeck.cli.download_url", side_effect=fake_download):
        result = main(
            [
                "self-update",
                "--install-dir",
                str(install_dir),
                "--archive-url",
                "https://example.test/doomdeck.tar.gz",
            ]
        )

    assert result == 0
    assert (install_dir / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert not (install_dir / "old.txt").exists()
    assert not Path(f"{install_dir}.previous").exists()
