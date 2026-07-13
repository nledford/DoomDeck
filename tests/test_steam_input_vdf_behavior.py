from __future__ import annotations
import dataclasses

from doomdeck.application.control_mapping import build_default_control_scheme
from doomdeck.domain.control_mapping import ControlAction, KeyboardMouseOutput, PhysicalInput
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


def test_steam_input_vdf_uses_domain_bindings_as_source_of_truth() -> None:
    scheme = build_default_control_scheme()
    without_bindings = dataclasses.replace(scheme, bindings=())

    text = render_steam_input_layout(without_bindings)

    assert "key_press W" not in text
    assert "key_press F9" not in text
    assert "mouse_button LEFT" not in text
    assert "absolute_mouse" not in text
    assert "joystick_mouse" not in text
    assert '"right_trackpad"' not in text
    assert '"right_joystick"' not in text


def test_steam_input_vdf_uses_domain_quickload_key_and_timing() -> None:
    scheme = build_default_control_scheme()
    bindings = tuple(
        dataclasses.replace(
            binding,
            output=KeyboardMouseOutput("key", "F8", "Alternate quick load"),
            long_press_ms=900,
        )
        if binding.action == ControlAction.QUICK_LOAD
        else binding
        for binding in scheme.bindings
    )

    text = render_steam_input_layout(dataclasses.replace(scheme, bindings=bindings))

    assert "key_press F8" in text
    assert "key_press F9" not in text
    assert '"long_press_time"\t\t"900"' in text


def test_switch_group_remains_when_rear_grip_bindings_are_removed() -> None:
    scheme = build_default_control_scheme()
    grips = {PhysicalInput.L4, PhysicalInput.R4, PhysicalInput.L5, PhysicalInput.R5}
    without_grips = dataclasses.replace(
        scheme,
        bindings=tuple(binding for binding in scheme.bindings if binding.physical_input not in grips),
    )

    text = render_steam_input_layout(without_grips)

    for physical_input in (
        PhysicalInput.MENU,
        PhysicalInput.VIEW,
        PhysicalInput.LEFT_BUMPER,
        PhysicalInput.RIGHT_BUMPER,
    ):
        for binding in without_grips.bindings_for(physical_input):
            assert binding.output.steam_input_binding() in text
    assert '"id"\t\t"6"' in text
