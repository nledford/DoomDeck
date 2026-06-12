from __future__ import annotations

from doomdeck.application.docs import render_content_group_guide


def test_content_group_guide_renders_known_sections() -> None:
    guide = render_content_group_guide(
        {
            "content_groups": {
                "presets": [
                    {
                        "id": "brutal-doom-forks",
                        "display_name": "Brutal Doom forks",
                        "items": [
                            {
                                "id": "preset:brutal-doom",
                                "display_name": "Brutal Doom",
                                "path": "/doom/launchers/Brutal_Doom.sh",
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert "## Automatic Content Groups" in guide
    assert "### Preset Groups" in guide
    assert "#### Brutal Doom forks" in guide
    assert "`Brutal Doom` - `/doom/launchers/Brutal_Doom.sh`" in guide


def test_content_group_guide_ignores_invalid_content_group_shape() -> None:
    assert render_content_group_guide({"content_groups": []}) == ""
