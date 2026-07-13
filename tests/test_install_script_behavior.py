from __future__ import annotations

import os
import hashlib
import subprocess
import sys
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DEP_NAME = "doomdecktestdep"


def test_install_script_resolves_default_branch_to_commit_archive() -> None:
    script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "api.github.com/repos" in script
    assert "/commits/" in script
    assert 'archive/${resolved_ref}.tar.gz' in script
    assert "class ValidatingRedirectHandler" in script
    assert "validate_url(response.geturl())" in script


def add_text_member(archive: tarfile.TarFile, name: str, content: str) -> None:
    data = content.encode("utf-8")
    member = tarfile.TarInfo(name)
    member.size = len(data)
    archive.addfile(member, fileobj=BytesIO(data))


def make_test_dependency_wheel(path: Path) -> None:
    metadata_dir = f"{TEST_DEP_NAME}-0.1.dist-info"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(f"{TEST_DEP_NAME}/__init__.py", "VALUE = 'installed dependency'\n")
        wheel.writestr(
            f"{metadata_dir}/METADATA",
            f"Metadata-Version: 2.1\nName: {TEST_DEP_NAME}\nVersion: 0.1\n",
        )
        wheel.writestr(
            f"{metadata_dir}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: DoomDeck tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(f"{metadata_dir}/RECORD", "")


def make_minimal_source_archive(path: Path, *, include_symlink: bool = False, dependency_wheel: Path | None = None) -> None:
    requirements = "# No dependencies in test fixture.\n"
    if dependency_wheel:
        digest = hashlib.sha256(dependency_wheel.read_bytes()).hexdigest()
        requirements = f"{TEST_DEP_NAME} @ {dependency_wheel.as_uri()} --hash=sha256:{digest}\n"
    main_module = (
        f"import {TEST_DEP_NAME}\nprint('usage: doomdeck')\nraise SystemExit(0)\n"
        if dependency_wheel
        else "print('usage: doomdeck')\nraise SystemExit(0)\n"
    )
    with tarfile.open(path, "w:gz") as archive:
        add_text_member(archive, "DoomDeck-main/pyproject.toml", "[project]\nname = 'doomdeck'\n")
        add_text_member(archive, "DoomDeck-main/requirements-runtime.lock", requirements)
        add_text_member(archive, "DoomDeck-main/src/doomdeck/__init__.py", "")
        add_text_member(archive, "DoomDeck-main/src/doomdeck/__main__.py", main_module)
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
        archive.add(PROJECT_ROOT / "requirements-runtime.lock", arcname="DoomDeck-main/requirements-runtime.lock")
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
    dependency_wheel = tmp_path / f"{TEST_DEP_NAME}-0.1-py3-none-any.whl"
    make_test_dependency_wheel(dependency_wheel)
    archive_path = tmp_path / "doomdeck.tar.gz"
    make_minimal_source_archive(archive_path, dependency_wheel=dependency_wheel)

    result = run_installer(archive_path, tmp_path)

    assert result.returncode == 0, result.stderr
    installed_command = tmp_path / "bin" / "doomdeck"
    assert installed_command.exists()
    installed_source = tmp_path / "install" / "source"
    assert (installed_source / ".venv" / "bin" / "python").exists()
    assert ".venv/bin/python" in installed_command.read_text(encoding="utf-8")

    help_result = subprocess.run(
        [str(installed_command), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert "usage:" in help_result.stdout
