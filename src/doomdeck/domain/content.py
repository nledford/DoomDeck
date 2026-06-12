"""Domain objects for grouped installable Doom content."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Mapping


@dataclasses.dataclass(frozen=True)
class ContentItem:
    id: str
    display_name: str
    kind: str
    path: Path | None = None
    metadata: Mapping[str, str] = dataclasses.field(default_factory=dict)
    selectable: bool = True

    def as_json_object(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "display_name": self.display_name,
            "kind": self.kind,
        }
        if self.path is not None:
            data["path"] = str(self.path)
        data["selectable"] = self.selectable
        if self.metadata:
            data["metadata"] = dict(sorted(self.metadata.items()))
        return data


@dataclasses.dataclass(frozen=True)
class ContentGroup:
    id: str
    display_name: str
    sort_order: int
    items: tuple[ContentItem, ...]

    def as_json_object(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "sort_order": self.sort_order,
            "items": [item.as_json_object() for item in self.items],
        }
