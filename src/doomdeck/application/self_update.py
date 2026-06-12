"""Self-update helpers for source-archive DoomDeck installs."""
from __future__ import annotations

import ast
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from doomdeck.domain.models import DoomDeckError

DEFAULT_SELF_UPDATE_REPO_URL = "https://github.com/nledford/DoomDeck"
DEFAULT_SELF_UPDATE_REF = "master"


@dataclass(frozen=True)
class SelfUpdatePlan:
    install_dir: Path
    archive_url: str
    previous_install_dir: Path

    def render_actions(self) -> list[str]:
        return [
            f"Validate managed DoomDeck source at {self.install_dir}",
            f"Download DoomDeck source archive from {self.archive_url}",
            "Extract and smoke-test the downloaded DoomDeck source",
            f"Replace {self.install_dir} using rollback path {self.previous_install_dir}",
        ]


def build_self_update_archive_url(
    repo_url: str = DEFAULT_SELF_UPDATE_REPO_URL,
    ref: str = DEFAULT_SELF_UPDATE_REF,
    explicit_archive_url: str | None = None,
) -> str:
    if explicit_archive_url:
        return explicit_archive_url
    normalized_repo_url = repo_url.rstrip("/")
    if normalized_repo_url.endswith(".git"):
        normalized_repo_url = normalized_repo_url[:-4]
    if not normalized_repo_url:
        raise DoomDeckError("Self-update repository URL must not be empty")
    if not ref.strip():
        raise DoomDeckError("Self-update ref must not be empty")
    return f"{normalized_repo_url}/archive/refs/heads/{ref}.tar.gz"


def infer_source_install_dir(module_file: Path) -> Path:
    resolved = module_file.expanduser()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    try:
        return resolved.parents[2]
    except IndexError as exc:
        raise DoomDeckError(f"Could not infer DoomDeck source install directory from {module_file}") from exc


def previous_self_update_install_dir(install_dir: Path) -> Path:
    return Path(f"{install_dir}.previous")


def build_self_update_plan(install_dir: Path, archive_url: str) -> SelfUpdatePlan:
    return SelfUpdatePlan(
        install_dir=install_dir,
        archive_url=archive_url,
        previous_install_dir=previous_self_update_install_dir(install_dir),
    )


def validate_self_update_source_dir(install_dir: Path) -> None:
    if not install_dir.exists():
        raise DoomDeckError(f"DoomDeck source install directory does not exist: {install_dir}")
    if (install_dir / ".git").exists():
        raise DoomDeckError(
            f"{install_dir} looks like a Git checkout. Use git pull for checkout updates instead of doomdeck self-update."
        )
    if not (install_dir / "pyproject.toml").is_file():
        raise DoomDeckError(f"DoomDeck source install is missing pyproject.toml: {install_dir}")
    if not (install_dir / "src" / "doomdeck").is_dir():
        raise DoomDeckError(f"DoomDeck source install is missing src/doomdeck: {install_dir}")


def read_project_dependencies(pyproject_path: Path) -> list[str]:
    in_project = False
    collecting_dependencies = False
    dependency_lines: list[str] = []
    bracket_depth = 0

    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if collecting_dependencies:
                break
            in_project = line == "[project]"
            continue
        if not in_project:
            continue
        if collecting_dependencies:
            dependency_lines.append(line)
            bracket_depth += line.count("[") - line.count("]")
            if bracket_depth <= 0:
                break
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip() == "dependencies":
            dependency_lines.append(value.strip())
            bracket_depth += value.count("[") - value.count("]")
            if bracket_depth <= 0:
                break
            collecting_dependencies = True

    if not dependency_lines:
        return []
    try:
        dependencies = ast.literal_eval("\n".join(dependency_lines))
    except (SyntaxError, ValueError) as exc:
        raise DoomDeckError(f"Could not read project dependencies from {pyproject_path}") from exc
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise DoomDeckError(f"Project dependencies must be a list of strings in {pyproject_path}")
    return dependencies


def runtime_venv_python(source_dir: Path) -> Path:
    if os.name == "nt":
        return source_dir / ".venv" / "Scripts" / "python.exe"
    return source_dir / ".venv" / "bin" / "python"


def _run_runtime_command(cmd: list[str], error_message: str) -> None:
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    if result.returncode != 0:
        raise DoomDeckError(f"{error_message} ({result.returncode}).\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def prepare_self_update_runtime(source_dir: Path, python_executable: Path, logger: logging.Logger) -> Path:
    venv_dir = source_dir / ".venv"
    logger.debug("Create DoomDeck runtime venv: %s", venv_dir)
    _run_runtime_command(
        [str(python_executable), "-m", "venv", str(venv_dir)],
        "Failed to create DoomDeck Python environment",
    )
    venv_python = runtime_venv_python(source_dir)
    if not venv_python.is_file():
        raise DoomDeckError(f"DoomDeck Python environment is missing its interpreter: {venv_python}")

    dependencies = read_project_dependencies(source_dir / "pyproject.toml")
    if dependencies:
        logger.debug("Install DoomDeck runtime dependencies into %s: %s", venv_dir, ", ".join(dependencies))
        _run_runtime_command(
            [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", *dependencies],
            "Failed to install DoomDeck Python dependencies",
        )
    return venv_python


def find_extracted_self_update_source_dir(extract_dir: Path) -> Path:
    candidates = [child for child in extract_dir.iterdir() if child.is_dir()]
    if len(candidates) != 1:
        raise DoomDeckError(f"DoomDeck source archive should contain exactly one top-level directory: {extract_dir}")
    source_dir = candidates[0]
    validate_self_update_source_dir(source_dir)
    return source_dir


def remove_existing_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def replace_self_update_install_dir(staged_install_dir: Path, install_dir: Path) -> None:
    previous_install_dir = previous_self_update_install_dir(install_dir)
    remove_existing_path(previous_install_dir)
    install_dir.parent.mkdir(parents=True, exist_ok=True)

    moved_existing = False
    if install_dir.exists() or install_dir.is_symlink():
        shutil.move(str(install_dir), str(previous_install_dir))
        moved_existing = True

    try:
        shutil.move(str(staged_install_dir), str(install_dir))
    except Exception as exc:
        if install_dir.exists() or install_dir.is_symlink():
            remove_existing_path(install_dir)
        if moved_existing and previous_install_dir.exists():
            shutil.move(str(previous_install_dir), str(install_dir))
        raise DoomDeckError(f"Failed to replace DoomDeck source install at {install_dir}") from exc

    remove_existing_path(previous_install_dir)
