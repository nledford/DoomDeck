from __future__ import annotations

from doomdeck.application.control_mapping import build_default_control_scheme
from doomdeck.infrastructure.steam_input_vdf import dumps_vdf, render_steam_input_layout


def test_steam_input_vdf_serializes_neptune_keyboard_mouse_mapping() -> None:
    text = render_steam_input_layout(build_default_control_scheme())

    assert '"controller_mappings"' in text
    assert '"controller_type"\t\t"controller_neptune"' in text
    assert "DoomDeck Hybrid KB/M" in text
    assert "key_press W" in text
    assert "mouse_button LEFT" in text
    assert "mouse_button RIGHT" in text
    assert "button_back_left_upper" in text
    assert "button_back_right" in text
    assert "gyro active" not in text.lower()


def test_steam_input_vdf_keeps_repeated_binding_keys() -> None:
    text = dumps_vdf([("root", [("bindings", [("binding", "key_press LEFT_CONTROL"), ("binding", "key_press TAB")])])])

    assert text.count('"binding"') == 2


def test_steam_input_quickload_is_long_press_only() -> None:
    text = render_steam_input_layout(build_default_control_scheme())

    quickload_index = text.index("key_press F9")
    quickload_block = text[text.rfind('"button_back_right"', 0, quickload_index) : quickload_index + 240]

    assert '"Long_Press"' in quickload_block
    assert '"long_press_time"\t\t"1500"' in quickload_block
    assert '"Full_Press"' not in quickload_block
