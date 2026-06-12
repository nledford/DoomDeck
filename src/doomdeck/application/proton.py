"""Helpers for launching Windows Doom tools through Steam Proton."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def proton_windows_path(path: str | Path) -> str:
    """Map a Linux path to the Wine/Proton Z: drive namespace."""
    text = str(path)
    if len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}:
        return text.replace("/", "\\")
    if text.startswith("/"):
        return "Z:" + text.replace("/", "\\")
    return text.replace("/", "\\")


def proton_linux_path(path: str | Path) -> Path:
    text = str(path)
    if len(text) >= 3 and text[0].lower() == "z" and text[1] == ":" and text[2] in {"\\", "/"}:
        return Path("/" + text[3:].replace("\\", "/").lstrip("/"))
    return Path(text)


def proton_quote_arg(value: str | Path) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def build_uzdoom_launch_options(preset: dict[str, Any]) -> str:
    parts = [
        "-noautoload",
        "-iwad",
        proton_quote_arg(proton_windows_path(preset["iwad"])),
        "-config",
        proton_quote_arg(proton_windows_path(preset["config"])),
        "+exec",
        proton_quote_arg(proton_windows_path(preset["autoexec"])),
    ]
    files = [proton_windows_path(path) for path in preset.get("files", [])]
    if files:
        parts.append("-file")
        parts.extend(proton_quote_arg(path) for path in files)
    return " ".join(parts)
