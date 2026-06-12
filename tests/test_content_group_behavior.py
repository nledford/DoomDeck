from __future__ import annotations

from doomdeck.application.content_groups import (
    build_content_groups,
    build_installed_content_groups,
    serialize_content_groups,
)
from doomdeck.application.presets import build_preset_manifest
from doomdeck.domain.content import ContentItem
from doomdeck.domain.paths import build_dirs


def group_names(groups):
    return {group.id: [item.display_name for item in group.items] for group in groups}


def test_grouping_known_related_content_by_metadata_and_paths(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    master = dirs.pwads / "MasterLevels" / "ATTACK.WAD"
    dtwid = dirs.pwads / "DTWID.WAD"
    brutal = dirs.mods / "brutal-doom" / "brutal-doom.pk3"
    weapon = dirs.mods / "arsenal" / "Combined_Arms.pk3"
    texture = dirs.mods / "textures" / "NeuralUpscale.pk3"
    visor = dirs.mods / "hud" / "visor-hud.pk3"
    music = dirs.mods / "music" / "Roland_MIDI_music.pk3"
    for path in [master, dtwid, brutal, weapon, texture, visor, music]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"content")

    grouped = build_installed_content_groups(
        dirs,
        {
            "presets": [
                {
                    "name": "Project Brutality",
                    "category": "Brutal Doom",
                    "launcher": str(dirs.launchers / "Project_Brutality.sh"),
                }
            ]
        },
    )

    assert group_names(grouped["presets"]) == {"brutal-doom-forks": ["Project Brutality"]}
    assert group_names(grouped["map_packs"]) == {
        "master-levels": ["ATTACK"],
        "map-packs": ["DTWID"],
    }
    assert group_names(grouped["mods"]) == {
        "brutal-doom-forks": ["brutal-doom"],
        "weapon-mods": ["Combined_Arms"],
        "textures": ["NeuralUpscale"],
        "visors": ["visor-hud"],
        "music": ["Roland_MIDI_music"],
    }


def test_unknown_items_are_kept_in_other_group(tmp_path) -> None:
    unknown = ContentItem(
        id="mod:unknown",
        display_name="mystery-addon",
        kind="mod",
        path=tmp_path / "mystery-addon.pk3",
    )

    groups = build_content_groups([unknown])

    assert group_names(groups) == {"other": ["mystery-addon"]}


def test_newly_added_wad_and_mod_appear_in_groups_on_refresh(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.pwads.mkdir(parents=True)
    dirs.mods.mkdir(parents=True)

    first_refresh = build_installed_content_groups(dirs, {"presets": []})
    assert first_refresh["map_packs"] == []
    assert first_refresh["mods"] == []

    (dirs.pwads / "MasterLevels.wad").write_bytes(b"wad")
    (dirs.mods / "textures" / "NeuralUpscale.pk3").parent.mkdir(parents=True)
    (dirs.mods / "textures" / "NeuralUpscale.pk3").write_bytes(b"mod")

    refreshed = build_installed_content_groups(dirs, {"presets": []})

    assert group_names(refreshed["map_packs"]) == {"master-levels": ["MasterLevels"]}
    assert group_names(refreshed["mods"]) == {"textures": ["NeuralUpscale"]}


def test_group_headers_are_not_serialized_as_selectable_items(tmp_path) -> None:
    item = ContentItem(
        id="map:dtwid",
        display_name="DTWID",
        kind="map_pack",
        path=tmp_path / "DTWID.WAD",
    )

    serialized = serialize_content_groups(build_content_groups([item]))

    assert "path" not in serialized[0]
    assert "selectable" not in serialized[0]
    assert serialized[0]["items"] == [
        {
            "id": "map:dtwid",
            "display_name": "DTWID",
            "kind": "map_pack",
            "path": str(tmp_path / "DTWID.WAD"),
            "selectable": True,
        }
    ]


def test_group_and_item_ordering_is_deterministic(tmp_path) -> None:
    items = [
        ContentItem("mod:z", "zeta weapon", "mod", tmp_path / "zeta-weapon.pk3"),
        ContentItem("mod:a", "alpha weapon", "mod", tmp_path / "alpha-weapon.pk3"),
        ContentItem("mod:t", "texture pack", "mod", tmp_path / "texture-pack.pk3"),
        ContentItem("mod:o", "unknown", "mod", tmp_path / "unknown.pk3"),
    ]

    groups = build_content_groups(items)

    assert [(group.id, [item.display_name for item in group.items]) for group in groups] == [
        ("weapon-mods", ["alpha weapon", "zeta weapon"]),
        ("textures", ["texture pack"]),
        ("other", ["unknown"]),
    ]


def test_preset_manifest_keeps_existing_presets_and_adds_separate_groups(tmp_path) -> None:
    dirs = build_dirs(tmp_path / "Doom")
    dirs.iwads.mkdir(parents=True)
    (dirs.iwads / "DOOM2.WAD").write_bytes(b"iwad")

    manifest = build_preset_manifest(dirs, None, None)

    presets = {preset["name"]: preset for preset in manifest["presets"]}
    assert presets["Brutal Doom"]["files"] == [str(dirs.brutal / "brutal-doom.pk3")]
    assert manifest["content_groups"]["presets"][0]["id"] == "brutal-doom-forks"
    assert all("content_groups" not in preset for preset in manifest["presets"])
