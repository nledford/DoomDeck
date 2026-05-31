"""Managed Doom directory layout helpers."""
from __future__ import annotations

from pathlib import Path

from .models import Dirs


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def build_dirs(root: Path) -> Dirs:
    return Dirs(
        root=root,
        tools=root / "tools",
        doomrunner=root / "tools" / "doomrunner",
        ports=root / "source-ports",
        uzdoom=root / "source-ports" / "uzdoom",
        iwads=root / "iwads",
        pwads=root / "pwads",
        mods=root / "mods",
        brutal=root / "mods" / "brutal-doom",
        project_brutality=root / "mods" / "project-brutality",
        configs=root / "configs",
        xdg_config=root / "configs" / "xdg-config",
        xdg_data=root / "configs" / "xdg-data",
        doomrunner_config=root / "configs" / "doomrunner",
        uzdoom_config=root / "configs" / "uzdoom",
        launchers=root / "launchers",
        saves=root / "saves",
        screenshots=root / "screenshots",
        logs=root / "logs",
        backups=root / "backups",
        downloads=root / "downloads",
        docs=root / "docs",
    )


def all_managed_dirs(dirs: Dirs) -> list[Path]:
    return [
        dirs.root,
        dirs.tools,
        dirs.doomrunner,
        dirs.ports,
        dirs.uzdoom,
        dirs.iwads,
        dirs.pwads,
        dirs.mods,
        dirs.brutal,
        dirs.project_brutality,
        dirs.configs,
        dirs.xdg_config,
        dirs.xdg_data,
        dirs.doomrunner_config,
        dirs.uzdoom_config,
        dirs.launchers,
        dirs.saves,
        dirs.screenshots,
        dirs.logs,
        dirs.backups,
        dirs.downloads,
        dirs.docs,
    ]
