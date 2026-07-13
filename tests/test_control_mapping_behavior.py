from __future__ import annotations

from doomdeck.application.control_mapping import build_default_control_scheme, build_uzdoom_control_profile
from doomdeck.domain.control_mapping import ControlAction, ControlProfile, PhysicalInput


def test_default_control_scheme_uses_keyboard_mouse_layout_without_gyro() -> None:
    scheme = build_default_control_scheme()
    outputs = [binding.output.steam_input_binding() for binding in scheme.bindings]

    assert not scheme.gyro_enabled
    assert {"W", "A", "S", "D"} <= {
        binding.output.value
        for binding in scheme.bindings
        if binding.physical_input == PhysicalInput.LEFT_STICK and binding.action == ControlAction.MOVE
    }
    assert any("mouse_button LEFT" in output for output in outputs)
    assert any("mouse_button RIGHT" in output for output in outputs)
    assert any("mouse_wheel SCROLL_UP" in output for output in outputs)
    assert any("mouse_wheel SCROLL_DOWN" in output for output in outputs)
    assert scheme.sensitivity.right_trackpad == 50
    assert scheme.sensitivity.right_stick == 35


def test_back_grips_are_mapped_with_safe_quickload_long_press() -> None:
    scheme = build_default_control_scheme()

    grip_actions = {binding.physical_input: binding for binding in scheme.bindings if binding.physical_input in {PhysicalInput.L4, PhysicalInput.R4, PhysicalInput.L5, PhysicalInput.R5}}

    assert grip_actions[PhysicalInput.L4].action == ControlAction.JUMP
    assert grip_actions[PhysicalInput.R4].action == ControlAction.CROUCH
    assert grip_actions[PhysicalInput.L5].action == ControlAction.QUICK_SAVE
    assert grip_actions[PhysicalInput.R5].action == ControlAction.QUICK_LOAD
    assert grip_actions[PhysicalInput.R5].activation == "Long_Press"
    assert grip_actions[PhysicalInput.R5].long_press_ms == 1500


def test_left_trackpad_radial_maps_weapon_slots_and_mod_utilities() -> None:
    scheme = build_default_control_scheme()
    radial_bindings = scheme.bindings_for(PhysicalInput.LEFT_TRACKPAD)

    assert any(binding.action == ControlAction.DIRECT_WEAPON and binding.output.value == "1-9,0" for binding in radial_bindings)
    assert {binding.output.value for binding in radial_bindings if binding.layer == "radial"} >= {"Q", "F", "G", "U", "LEFT_ALT", "L"}


def test_profile_variants_preserve_mod_specific_keys() -> None:
    modern = build_uzdoom_control_profile(ControlProfile.MODERN)
    brutal = build_uzdoom_control_profile(ControlProfile.BRUTAL_DOOM)
    project_brutality = build_uzdoom_control_profile(ControlProfile.PROJECT_BRUTALITY)

    modern_bindings = {(binding.input_name, binding.command) for binding in modern.bindings}
    brutal_keys = {binding.input_name for binding in brutal.bindings}
    project_brutality_keys = {binding.input_name for binding in project_brutality.bindings}

    assert ("q", "weapprev") in modern_bindings
    assert ("capslock", '"toggle cl_run"') in modern_bindings
    assert ("tab", "togglemap") in modern_bindings
    assert ("0", "slot 0") in modern_bindings
    assert "q" not in brutal_keys
    assert not {"q", "f", "g", "u", "leftalt", "l"} & project_brutality_keys


def test_scheme_documents_three_alternatives_and_evidence() -> None:
    scheme = build_default_control_scheme()

    assert len(scheme.alternatives) == 3
    assert any("GZDoom" in source for source in scheme.evidence)
    assert any("Brutal Doom" in source for source in scheme.evidence)
    assert "no gyro" in scheme.description.lower()
