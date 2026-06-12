from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import call, patch

import pytest

from doomdeck.application.self_update import (
    DEFAULT_SELF_UPDATE_REF,
    DEFAULT_SELF_UPDATE_REPO_URL,
    build_self_update_archive_url,
    infer_source_install_dir,
    prepare_self_update_runtime,
    read_project_dependencies,
    runtime_venv_python,
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


def test_read_project_dependencies_from_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "doomdeck"\ndependencies = [\n    "pydantic>=2.13.0,<3.0.0",\n]\n',
        encoding="utf-8",
    )

    assert read_project_dependencies(pyproject) == ["pydantic>=2.13.0,<3.0.0"]


def test_prepare_self_update_runtime_installs_project_dependencies(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "pyproject.toml").write_text(
        '[project]\nname = "doomdeck"\ndependencies = ["pydantic>=2.13.0,<3.0.0"]\n',
        encoding="utf-8",
    )
    venv_python = runtime_venv_python(source_dir)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    logger = logging.getLogger("test")

    with patch("doomdeck.application.self_update.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")

        prepared_python = prepare_self_update_runtime(source_dir, Path(sys.executable), logger)

    assert prepared_python == venv_python
    assert run.call_args_list == [
        call(
            [sys.executable, "-m", "venv", str(source_dir / ".venv")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        ),
        call(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "pydantic>=2.13.0,<3.0.0",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        ),
    ]


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
