"""Build grouped views of installed DoomDeck content."""
from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, cast

from doomdeck.domain.content import ContentGroup, ContentItem
from doomdeck.domain.models import Dirs
from doomdeck.domain.mods import BRUTAL_DOOM_MOD, PROJECT_BRUTALITY_MOD

CONTENT_GROUP_SCHEMA = "doom-deck-setup/content-groups/v1"
CONTENT_SUFFIXES = {".pk3", ".wad", ".zip"}


@dataclasses.dataclass(frozen=True)
class GroupDefinition:
    id: str
    display_name: str
    sort_order: int


@dataclasses.dataclass(frozen=True)
class GroupRule:
    group_id: str
    content_kinds: tuple[str, ...]
    terms: tuple[str, ...]


GROUP_DEFINITIONS: tuple[GroupDefinition, ...] = (
    GroupDefinition("brutal-doom-forks", "Brutal Doom forks", 10),
    GroupDefinition("weapon-mods", "weapon mods", 20),
    GroupDefinition("total-conversions", "total conversions", 30),
    GroupDefinition("master-levels", "Master Levels", 40),
    GroupDefinition("map-packs", "map packs", 50),
    GroupDefinition("mutators", "mutators", 60),
    GroupDefinition("textures", "textures", 70),
    GroupDefinition("visors", "visors", 80),
    GroupDefinition("music", "music", 90),
    GroupDefinition("other", "Other", 10_000),
)

GROUPS_BY_ID = {group.id: group for group in GROUP_DEFINITIONS}

# Ordered from most specific to broadest. The explicit metadata pass uses the
# same rules before the path/name passes so future metadata fields can override
# ambiguous filenames without changing rendering code.
GROUP_RULES: tuple[GroupRule, ...] = (
    GroupRule("brutal-doom-forks", ("mod", "preset"), ("brutal doom", "project brutality", "brutality")),
    GroupRule("weapon-mods", ("mod", "preset"), ("weapon", "weapons", "arsenal", "armory", "gun")),
    GroupRule("total-conversions", ("mod", "preset"), ("total conversion", "total-conversion", "tc", "aliens", "batman")),
    GroupRule("master-levels", ("map_pack",), ("master levels", "masterlevels", "master-levels", "master_levels")),
    GroupRule("map-packs", ("map_pack", "preset"), ("map pack", "mappack", "maps", "levels", "megawad", "episode", "dtwid", "sigil")),
    GroupRule("mutators", ("mod",), ("mutator", "mutators", "randomizer", "monsters only", "gameplay")),
    GroupRule("textures", ("mod",), ("texture", "textures", "brightmap", "brightmaps", "voxel", "voxels", "neural", "upscale")),
    GroupRule("visors", ("mod",), ("visor", "visors", "hud", "heads up", "crosshair")),
    GroupRule("music", ("mod",), ("music", "soundtrack", "midi", "ost")),
)


def serialize_content_groups(groups: Iterable[ContentGroup]) -> list[dict[str, object]]:
    return [group.as_json_object() for group in groups]


def serialize_content_group_sections(sections: Mapping[str, Iterable[ContentGroup]]) -> dict[str, list[dict[str, object]]]:
    return {section: serialize_content_groups(groups) for section, groups in sections.items()}


def content_group_document(dirs: Dirs, sections: Mapping[str, Iterable[ContentGroup]]) -> dict[str, object]:
    return {
        "schema": CONTENT_GROUP_SCHEMA,
        "root": str(dirs.root),
        "content_groups": serialize_content_group_sections(sections),
    }


def build_content_group_document(dirs: Dirs, manifest: Mapping[str, object]) -> dict[str, object]:
    return content_group_document(dirs, build_installed_content_groups(dirs, manifest))


def build_content_groups(items: Iterable[ContentItem]) -> list[ContentGroup]:
    grouped: dict[str, list[ContentItem]] = defaultdict(list)
    for item in items:
        grouped[infer_group_id(item)].append(item)

    groups: list[ContentGroup] = []
    for group_id, items_for_group in grouped.items():
        definition = GROUPS_BY_ID[group_id]
        groups.append(
            ContentGroup(
                id=definition.id,
                display_name=definition.display_name,
                sort_order=definition.sort_order,
                items=tuple(sorted(items_for_group, key=_item_sort_key)),
            )
        )
    return sorted(groups, key=lambda group: (group.sort_order, group.display_name.casefold(), group.id))


def infer_group_id(item: ContentItem) -> str:
    if (explicit_id := item.metadata.get("group_id")) in GROUPS_BY_ID:
        return str(explicit_id)

    explicit_values = [
        item.metadata.get("group", ""),
        item.metadata.get("category", ""),
        item.metadata.get("name", ""),
        item.metadata.get("source_title", ""),
    ]
    if group_id := _match_rules(item.kind, explicit_values):
        return group_id

    path_values = _path_group_values(item.path)
    if group_id := _match_rules(item.kind, path_values):
        return group_id

    name_values = [item.display_name, item.path.name if item.path else ""]
    return _match_rules(item.kind, name_values) or "other"


def build_installed_content_groups(dirs: Dirs, manifest: Mapping[str, object]) -> dict[str, list[ContentGroup]]:
    return {
        "presets": build_content_groups(_preset_items(manifest)),
        "map_packs": build_content_groups(_file_items(dirs.pwads, "map_pack", dirs.root)),
        "mods": build_content_groups(_mod_items(dirs)),
    }


def content_groups_from_manifest(dirs: Dirs, manifest: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    return serialize_content_group_sections(build_installed_content_groups(dirs, manifest))


def _preset_items(manifest: Mapping[str, object]) -> list[ContentItem]:
    presets = manifest.get("presets", [])
    if not isinstance(presets, list):
        return []
    items: list[ContentItem] = []
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        preset_data = cast(Mapping[str, object], preset)
        name = str(preset_data.get("name", "")).strip()
        if not name:
            continue
        launcher_raw = preset_data.get("launcher")
        launcher = Path(str(launcher_raw)) if launcher_raw else None
        metadata = {
            "category": str(preset_data.get("category", "")),
            "engine": str(preset_data.get("engine", "")),
        }
        items.append(
            ContentItem(
                id=f"preset:{_slug_id(name)}",
                display_name=name,
                kind="preset",
                path=launcher,
                metadata={key: value for key, value in metadata.items() if value},
            )
        )
    return items


def _file_items(directory: Path, kind: str, root: Path) -> list[ContentItem]:
    if not directory.exists():
        return []
    items: list[ContentItem] = []
    for path in sorted((p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in CONTENT_SUFFIXES), key=_path_sort_key):
        items.append(
            ContentItem(
                id=f"{kind}:{_stable_path_id(path, root)}",
                display_name=_display_name(path),
                kind=kind,
                path=path,
            )
        )
    return items


def _mod_items(dirs: Dirs) -> list[ContentItem]:
    items = _file_items(dirs.mods, "mod", dirs.root)
    metadata_by_path = _managed_mod_metadata_by_path(dirs)
    enriched: list[ContentItem] = []
    for item in items:
        metadata = dict(item.metadata)
        if item.path and item.path in metadata_by_path:
            metadata.update(metadata_by_path[item.path])
        enriched.append(
            ContentItem(
                id=item.id,
                display_name=item.display_name,
                kind=item.kind,
                path=item.path,
                metadata=metadata,
                selectable=item.selectable,
            )
        )
    return enriched


def _managed_mod_metadata_by_path(dirs: Dirs) -> dict[Path, dict[str, str]]:
    metadata: dict[Path, dict[str, str]] = {}
    for mod, directory in [(BRUTAL_DOOM_MOD, dirs.brutal), (PROJECT_BRUTALITY_MOD, dirs.project_brutality)]:
        metadata_path = mod.metadata_path(directory)
        if not metadata_path.exists():
            continue
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        installed = Path(str(raw.get("installed", mod.alias_path(directory))))
        metadata[installed] = {str(key): str(value) for key, value in raw.items() if isinstance(value, str)}
    return metadata


def _match_rules(kind: str, values: Iterable[str]) -> str:
    texts = [value for value in values if value]
    for rule in GROUP_RULES:
        if kind not in rule.content_kinds:
            continue
        if any(_contains_term(text, term) for text in texts for term in rule.terms):
            return rule.group_id
    return ""


def _path_group_values(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [str(part) for part in path.parts[:-1]]


def _contains_term(text: str, term: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_term = _normalize_text(term)
    compact_text = normalized_text.replace(" ", "")
    compact_term = normalized_term.replace(" ", "")
    return normalized_term in normalized_text or bool(compact_term and compact_term in compact_text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def _slug_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "item"


def _stable_path_id(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return _slug_id(relative.as_posix())


def _display_name(path: Path) -> str:
    return path.stem.strip() or path.name


def _item_sort_key(item: ContentItem) -> tuple[str, str, str]:
    return (item.display_name.casefold(), str(item.path or "").casefold(), item.id)


def _path_sort_key(path: Path) -> str:
    return path.as_posix().casefold()
