"""Managed mod identities and metadata helpers."""
from __future__ import annotations

import dataclasses
import datetime as _dt
from pathlib import Path
from typing import Mapping


@dataclasses.dataclass(frozen=True)
class ManagedMod:
    name: str
    alias: str
    metadata_filename: str

    def alias_path(self, directory: Path) -> Path:
        return directory / self.alias

    def metadata_path(self, directory: Path) -> Path:
        return directory / self.metadata_filename


@dataclasses.dataclass(frozen=True)
class InstalledModMetadata:
    mod: ManagedMod
    installed: Path
    source_sha256: str
    source: Mapping[str, str]
    installed_sha256: str | None = None
    payload_member: str = ""

    def as_json_object(self) -> dict[str, str]:
        metadata = {
            "name": self.mod.name,
            "installed": str(self.installed),
            "source_sha256": self.source_sha256,
            **self.source,
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        if self.installed_sha256 is not None:
            metadata["installed_sha256"] = self.installed_sha256
        if self.payload_member:
            metadata["payload_member"] = self.payload_member
        return metadata


BRUTAL_DOOM_MOD = ManagedMod(
    name="Brutal Doom",
    alias="brutal-doom.pk3",
    metadata_filename="brutal-doom.json",
)

PROJECT_BRUTALITY_MOD = ManagedMod(
    name="Project Brutality",
    alias="project-brutality.pk3",
    metadata_filename="project-brutality.json",
)
