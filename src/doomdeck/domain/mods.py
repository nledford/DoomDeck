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
class ModSource:
    """Domain-facing provenance for a managed mod artifact."""

    source_type: str
    values: Mapping[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def local_file(cls, path: Path) -> "ModSource":
        return cls("local_file", {"source_path": str(path)})

    @classmethod
    def local_existing(cls, path: Path) -> "ModSource":
        return cls("local_existing", {"source_path": str(path)})

    @classmethod
    def explicit_url(cls, url: str, filename: str) -> "ModSource":
        return cls("explicit_url", {"source_url": url, "source_filename": filename})

    @classmethod
    def github(cls, url: str, tag: str) -> "ModSource":
        return cls("github", {"source_url": url, "source_tag": tag})

    @classmethod
    def moddb(
        cls,
        *,
        channel: str,
        title: str,
        page_url: str,
        filename: str,
        updated: str,
        md5: str,
        download_url: str = "",
    ) -> "ModSource":
        values = {
            "source_channel": channel,
            "source_title": title,
            "source_page_url": page_url,
            "source_filename": filename,
            "source_updated": updated,
            "source_md5": md5,
        }
        if download_url:
            values["source_download_url"] = download_url
        return cls("moddb", values)

    def as_metadata(self) -> dict[str, str]:
        return {"source_type": self.source_type, **{key: str(value) for key, value in self.values.items()}}


@dataclasses.dataclass(frozen=True)
class InstalledModMetadata:
    mod: ManagedMod
    installed: Path
    source_sha256: str
    source: Mapping[str, str] | ModSource
    installed_sha256: str | None = None
    payload_member: str = ""

    def as_json_object(self) -> dict[str, str]:
        source = self.source.as_metadata() if isinstance(self.source, ModSource) else dict(self.source)
        metadata = {
            "name": self.mod.name,
            "installed": str(self.installed),
            "source_sha256": self.source_sha256,
            **source,
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
