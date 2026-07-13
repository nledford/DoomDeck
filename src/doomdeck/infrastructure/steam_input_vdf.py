"""Steam Input VDF serialization for DoomDeck layouts."""
from __future__ import annotations

from typing import Sequence, TypeAlias

from doomdeck.domain.control_mapping import ControlAction, ControlScheme, PhysicalInput, SteamInputBinding

VDFValue: TypeAlias = str | Sequence[tuple[str, "VDFValue"]]
VDFEntries: TypeAlias = Sequence[tuple[str, VDFValue]]
SWITCH_PHYSICAL_INPUTS = {
    PhysicalInput.MENU,
    PhysicalInput.VIEW,
    PhysicalInput.LEFT_BUMPER,
    PhysicalInput.RIGHT_BUMPER,
    PhysicalInput.L4,
    PhysicalInput.R4,
    PhysicalInput.L5,
    PhysicalInput.R5,
}


def dumps_vdf(entries: VDFEntries) -> str:
    lines: list[str] = []
    _dump_entries(entries, lines, 0)
    return "\n".join(lines) + "\n"


def render_steam_input_layout(layout: ControlScheme, *, url: str = "template://doomdeck_hybrid_kbm.vdf") -> str:
    """Serialize a Steam Deck keyboard/mouse layout as Steam Input VDF."""

    groups: list[tuple[str, VDFValue]] = []
    source_bindings: list[tuple[str, VDFValue]] = []
    if _has_binding(layout, {PhysicalInput.A, PhysicalInput.B, PhysicalInput.X, PhysicalInput.Y}):
        groups.append(_four_button_group(layout))
        source_bindings.append(("0", "button_diamond active"))
    if _has_binding(layout, {PhysicalInput.LEFT_TRACKPAD}):
        groups.append(_left_trackpad_radial_group(layout))
        source_bindings.append(("1", "left_trackpad active"))
    if _has_binding(layout, {PhysicalInput.RIGHT_TRACKPAD}, ControlAction.AIM):
        groups.append(_right_trackpad_group(layout))
        source_bindings.append(("2", "right_trackpad active"))
    if _has_binding(layout, {PhysicalInput.LEFT_STICK}, ControlAction.MOVE):
        groups.append(_left_stick_group(layout))
        source_bindings.append(("3", "joystick active"))
    if _has_binding(layout, {PhysicalInput.LEFT_TRIGGER}):
        groups.append(_left_trigger_group(layout))
        source_bindings.append(("4", "left_trigger active"))
    if _has_binding(layout, {PhysicalInput.RIGHT_TRIGGER}):
        groups.append(_right_trigger_group(layout))
        source_bindings.append(("5", "right_trigger active"))
    if _has_binding(layout, SWITCH_PHYSICAL_INPUTS):
        groups.append(_switches_group(layout))
        source_bindings.append(("6", "switch active"))
    if _has_binding(layout, {PhysicalInput.DPAD}):
        groups.append(_dpad_group(layout))
        source_bindings.append(("7", "dpad active"))
    if _has_binding(layout, {PhysicalInput.RIGHT_STICK}, ControlAction.AIM):
        groups.append(_right_stick_group(layout))
        source_bindings.append(("8", "right_joystick active"))

    entries: VDFEntries = [
        (
            "controller_mappings",
            [
                ("version", "3"),
                ("revision", "1"),
                ("title", layout.name),
                ("description", layout.description),
                ("creator", "-1"),
                ("progenitor", "template://controller_neptune_wasd.vdf"),
                ("url", url),
                ("export_type", "personal_cloud" if url.startswith("autosave://") else "template"),
                ("controller_type", "controller_neptune"),
                ("controller_caps", "23117823"),
                ("major_revision", "0"),
                ("minor_revision", "0"),
                ("Timestamp", "0"),
                ("localization", [("english", [("title", layout.name), ("description", layout.description)])]),
                *groups,
                _default_preset(source_bindings),
                ("settings", [("left_trackpad_mode", "0"), ("right_trackpad_mode", "0")]),
            ],
        )
    ]
    return dumps_vdf(entries)


def _four_button_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "0"),
            ("mode", "four_buttons"),
            ("name", "Face buttons"),
            ("description", "Console-style use/crouch/reload/jump mapped to keyboard keys"),
            (
                "inputs",
                [_binding_input(binding, repeat=True) for binding in _slot_bindings(layout, {PhysicalInput.A, PhysicalInput.B, PhysicalInput.X, PhysicalInput.Y})],
            ),
            ("settings", [("button_size", "17994"), ("button_dist", "19994")]),
        ],
    )


def _left_trackpad_radial_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    bindings = [
        binding
        for binding in layout.bindings_for(PhysicalInput.LEFT_TRACKPAD)
        if binding.layer == "radial" and binding.input_slot
    ]
    return (
        "group",
        [
            ("id", "1"),
            ("mode", "radial_menu"),
            ("name", "Weapons and mod utilities"),
            ("description", "Direct slots plus Brutal Doom / Project Brutality utility keys"),
            ("inputs", [_binding_input(binding) for binding in bindings]),
            ("settings", [("requires_click", "0"), ("touch_menu_button_count", str(len(bindings)))]),
        ],
    )


def _right_trackpad_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    click_bindings = [
        binding
        for binding in layout.bindings_for(PhysicalInput.RIGHT_TRACKPAD)
        if binding.input_slot
    ]
    return (
        "group",
        [
            ("id", "2"),
            ("mode", _aim_mode(layout, PhysicalInput.RIGHT_TRACKPAD)),
            ("name", "Right trackpad aim"),
            ("description", "Primary mouse aim without gyro"),
            ("inputs", [_binding_input(binding) for binding in click_bindings]),
            ("settings", [("sensitivity", str(layout.sensitivity.right_trackpad)), ("doubetap_max_duration", "320")]),
        ],
    )


def _left_stick_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "3"),
            ("mode", "dpad"),
            ("name", "Left stick WASD"),
            ("description", "Keyboard WASD movement"),
            (
                "inputs",
                [_binding_input(binding, repeat=True) for binding in _slot_bindings(layout, {PhysicalInput.LEFT_STICK})],
            ),
            ("settings", [("requires_click", "0"), ("deadzone_inner_radius", str(layout.sensitivity.left_stick_deadzone))]),
        ],
    )


def _left_trigger_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "4"),
            ("mode", "trigger"),
            ("name", "Left trigger alt fire"),
            ("inputs", [_binding_input(binding, haptic="2") for binding in _slot_bindings(layout, {PhysicalInput.LEFT_TRIGGER})]),
        ],
    )


def _right_trigger_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "5"),
            ("mode", "trigger"),
            ("name", "Right trigger fire"),
            ("inputs", [_binding_input(binding, haptic="2") for binding in _slot_bindings(layout, {PhysicalInput.RIGHT_TRIGGER})]),
        ],
    )


def _switches_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    bindings = _slot_bindings(layout, SWITCH_PHYSICAL_INPUTS)
    return (
        "group",
        [
            ("id", "6"),
            ("mode", "switches"),
            ("name", "Buttons and grips"),
            (
                "inputs",
                [
                    _binding_input(
                        binding,
                        repeat=binding.physical_input in {PhysicalInput.L4, PhysicalInput.R4},
                        haptic="2" if binding.physical_input == PhysicalInput.L5 else "1",
                    )
                    for binding in bindings
                ],
            ),
        ],
    )


def _dpad_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "7"),
            ("mode", "dpad"),
            ("name", "Menu navigation"),
            (
                "inputs",
                [_binding_input(binding, repeat=True) for binding in _slot_bindings(layout, {PhysicalInput.DPAD})],
            ),
            ("settings", [("requires_click", "0"), ("haptic_intensity_override", "0")]),
        ],
    )


def _right_stick_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    click_bindings = [
        binding
        for binding in layout.bindings_for(PhysicalInput.RIGHT_STICK)
        if binding.input_slot
    ]
    return (
        "group",
        [
            ("id", "8"),
            ("mode", _aim_mode(layout, PhysicalInput.RIGHT_STICK)),
            ("name", "Right stick mouse"),
            ("description", "Conservative coarse mouse aim; right trackpad remains primary aim"),
            ("inputs", [_binding_input(binding) for binding in click_bindings]),
            (
                "settings",
                [
                    ("output_joystick", "2"),
                    ("sensitivity", str(layout.sensitivity.right_stick)),
                    ("deadzone_inner_radius", str(layout.sensitivity.right_stick_deadzone)),
                ],
            ),
        ],
    )


def _default_preset(source_bindings: list[tuple[str, VDFValue]]) -> tuple[str, VDFValue]:
    return (
        "preset",
        [
            ("id", "0"),
            ("name", "Default"),
            ("group_source_bindings", source_bindings),
        ],
    )


def _slot_bindings(layout: ControlScheme, physical_inputs: set[PhysicalInput]) -> list[SteamInputBinding]:
    return [
        binding
        for binding in layout.bindings
        if binding.physical_input in physical_inputs and binding.input_slot
    ]


def _has_binding(
    layout: ControlScheme,
    physical_inputs: set[PhysicalInput],
    action: ControlAction | None = None,
) -> bool:
    return any(
        binding.physical_input in physical_inputs and (action is None or binding.action == action)
        for binding in layout.bindings
    )


def _aim_mode(layout: ControlScheme, physical_input: PhysicalInput) -> str:
    for binding in layout.bindings_for(physical_input):
        if binding.action == ControlAction.AIM:
            return binding.output.value
    raise ValueError(f"Steam Input aim binding is missing: {physical_input.value}")


def _binding_input(
    binding: SteamInputBinding,
    *,
    repeat: bool = False,
    haptic: str = "1",
) -> tuple[str, VDFValue]:
    if not binding.input_slot:
        raise ValueError(f"Steam Input binding is missing an input slot: {binding.physical_input.value}")
    serialized = binding.output.steam_input_binding()
    if binding.activation == "Long_Press":
        if binding.long_press_ms is None:
            raise ValueError(f"Long-press binding is missing its duration: {binding.physical_input.value}")
        return _long_press_input(binding.input_slot, serialized, long_press_ms=binding.long_press_ms)
    return _button_input(
        binding.input_slot,
        serialized,
        activator=binding.activation,
        repeat=repeat,
        haptic=haptic,
    )


def _button_input(
    input_name: str,
    binding: str,
    *,
    activator: str = "Full_Press",
    repeat: bool = False,
    haptic: str = "1",
) -> tuple[str, VDFValue]:
    settings = [("haptic_intensity", haptic)]
    if repeat:
        settings.insert(0, ("repeat_rate", "99"))
    return (input_name, _activator(binding, activator=activator, settings=settings))


def _long_press_input(input_name: str, binding: str, *, long_press_ms: int) -> tuple[str, VDFValue]:
    return (
        input_name,
        [
            (
                "activators",
                [
                    (
                        "Long_Press",
                        [
                            ("bindings", [("binding", binding)]),
                            ("settings", [("long_press_time", str(long_press_ms)), ("haptic_intensity", "3")]),
                        ],
                    )
                ],
            ),
            ("disabled_activators", []),
        ],
    )


def _activator(
    binding: str,
    *,
    activator: str = "Full_Press",
    settings: VDFEntries | None = None,
) -> VDFEntries:
    body: list[tuple[str, VDFValue]] = [("bindings", [("binding", binding)])]
    if settings:
        body.append(("settings", settings))
    return [("activators", [(activator, body)]), ("disabled_activators", [])]


def _dump_entries(entries: VDFEntries, lines: list[str], indent: int) -> None:
    prefix = "\t" * indent
    for key, value in entries:
        escaped_key = _escape_vdf(key)
        if isinstance(value, str):
            lines.append(f'{prefix}"{escaped_key}"\t\t"{_escape_vdf(value)}"')
        else:
            lines.append(f'{prefix}"{escaped_key}"')
            lines.append(f"{prefix}{{")
            _dump_entries(value, lines, indent + 1)
            lines.append(f"{prefix}}}")


def _escape_vdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
