from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def add_text_member(archive: tarfile.TarFile, name: str, content: str) -> None:
    data = content.encode("utf-8")
    member = tarfile.TarInfo(name)
    member.size = len(data)
    archive.addfile(member, fileobj=BytesIO(data))


def make_minimal_source_archive(path: Path, *, include_symlink: bool = False) -> None:
    with tarfile.open(path, "w:gz") as archive:
        add_text_member(archive, "DoomDeck-main/pyproject.toml", "[project]\nname = 'doomdeck'\n")
        add_text_member(archive, "DoomDeck-main/src/doomdeck/__init__.py", "")
        add_text_member(archive, "DoomDeck-main/src/doomdeck/__main__.py", "raise SystemExit(0)\n")
        if include_symlink:
            member = tarfile.TarInfo("DoomDeck-main/unsafe-link")
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/doomdeck-installer-unsafe-link-target"
            archive.addfile(member)


def make_repo_source_archive(path: Path) -> None:
    def source_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(member.name).parts
        if "__pycache__" in parts or member.name.endswith((".pyc", ".pyo")):
            return None
        return member

    with tarfile.open(path, "w:gz") as archive:
        archive.add(PROJECT_ROOT / "pyproject.toml", arcname="DoomDeck-main/pyproject.toml")
        archive.add(PROJECT_ROOT / "src" / "doomdeck", arcname="DoomDeck-main/src/doomdeck", filter=source_filter)


def run_installer(archive_path: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DOOMDECK_ARCHIVE_URL": archive_path.as_uri(),
        "DOOMDECK_INSTALL_DIR": str(tmp_path / "install" / "source"),
        "DOOMDECK_BIN_DIR": str(tmp_path / "bin"),
        "PYTHON": sys.executable,
        "TMPDIR": str(tmp_path),
    }
    return subprocess.run(
        ["sh", "install.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def test_install_script_rejects_source_archives_with_links(tmp_path: Path) -> None:
    archive_path = tmp_path / "doomdeck.tar.gz"
    make_minimal_source_archive(archive_path, include_symlink=True)

    result = run_installer(archive_path, tmp_path)

    assert result.returncode != 0
    assert "unsafe" in result.stderr.lower()
    assert not (tmp_path / "install" / "source").exists()


def test_install_script_installs_cli_with_self_update_command(tmp_path: Path) -> None:
    archive_path = tmp_path / "doomdeck.tar.gz"
    make_repo_source_archive(archive_path)

    result = run_installer(archive_path, tmp_path)

    assert result.returncode == 0, result.stderr
    installed_command = tmp_path / "bin" / "doomdeck"
    assert installed_command.exists()

    help_result = subprocess.run(
        [str(installed_command), "self-update", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert "usage:" in help_result.stdout
