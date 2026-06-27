"""Steam Input VDF serialization for DoomDeck layouts."""
from __future__ import annotations

from typing import Sequence, TypeAlias

from doomdeck.domain.control_mapping import ControlScheme

VDFValue: TypeAlias = str | Sequence[tuple[str, "VDFValue"]]
VDFEntries: TypeAlias = Sequence[tuple[str, VDFValue]]


def dumps_vdf(entries: VDFEntries) -> str:
    lines: list[str] = []
    _dump_entries(entries, lines, 0)
    return "\n".join(lines) + "\n"


def render_steam_input_layout(layout: ControlScheme, *, url: str = "template://doomdeck_hybrid_kbm.vdf") -> str:
    """Serialize a Steam Deck keyboard/mouse layout as Steam Input VDF."""

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
                _four_button_group(),
                _left_trackpad_radial_group(),
                _right_trackpad_group(layout),
                _left_stick_group(layout),
                _left_trigger_group(),
                _right_trigger_group(),
                _switches_group(),
                _dpad_group(),
                _right_stick_group(layout),
                _default_preset(),
                ("settings", [("left_trackpad_mode", "0"), ("right_trackpad_mode", "0")]),
            ],
        )
    ]
    return dumps_vdf(entries)


def _four_button_group() -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "0"),
            ("mode", "four_buttons"),
            ("name", "Face buttons"),
            ("description", "Console-style use/crouch/reload/jump mapped to keyboard keys"),
            (
                "inputs",
                [
                    _button_input("button_a", "key_press E, Use / confirm, , ", repeat=True),
                    _button_input("button_b", "key_press LEFT_CONTROL, Crouch / menu back, , ", repeat=True),
                    _button_input("button_x", "key_press R, Reload, , ", repeat=True),
                    _button_input("button_y", "key_press SPACE, Jump / use, , ", repeat=True),
                ],
            ),
            ("settings", [("button_size", "17994"), ("button_dist", "19994")]),
        ],
    )


def _left_trackpad_radial_group() -> tuple[str, VDFValue]:
    buttons = [
        ("1", "Weapon slot 1"),
        ("2", "Weapon slot 2"),
        ("3", "Weapon slot 3"),
        ("4", "Weapon slot 4"),
        ("5", "Weapon slot 5"),
        ("6", "Weapon slot 6"),
        ("7", "Weapon slot 7"),
        ("8", "Weapon slot 8"),
        ("9", "Weapon slot 9"),
        ("0", "Weapon slot 10"),
        ("Q", "Brutal/PB kick"),
        ("F", "Flashlight / zoom / mod utility"),
        ("G", "PB equipment"),
        ("U", "PB unload"),
        ("LEFT_ALT", "PB dash"),
        ("L", "PB clear debris"),
    ]
    return (
        "group",
        [
            ("id", "1"),
            ("mode", "radial_menu"),
            ("name", "Weapons and mod utilities"),
            ("description", "Direct slots plus Brutal Doom / Project Brutality utility keys"),
            ("inputs", [(f"touch_menu_button_{index}", _activator(f"key_press {key}, {label}, , ")) for index, (key, label) in enumerate(buttons, start=1)]),
            ("settings", [("requires_click", "0"), ("touch_menu_button_count", str(len(buttons)))]),
        ],
    )


def _right_trackpad_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "2"),
            ("mode", "absolute_mouse"),
            ("name", "Right trackpad aim"),
            ("description", "Primary mouse aim without gyro"),
            ("inputs", [_button_input("click", "mouse_button MIDDLE, Zoom / center view, , ", activator="Soft_Press")]),
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
                [
                    _button_input("dpad_north", "key_press W, Move forward, , ", repeat=True),
                    _button_input("dpad_south", "key_press S, Move back, , ", repeat=True),
                    _button_input("dpad_east", "key_press D, Strafe right, , ", repeat=True),
                    _button_input("dpad_west", "key_press A, Strafe left, , ", repeat=True),
                    _button_input("click", "key_press CAPSLOCK, Toggle run mode, , ", repeat=True),
                ],
            ),
            ("settings", [("requires_click", "0"), ("deadzone_inner_radius", str(layout.sensitivity.left_stick_deadzone))]),
        ],
    )


def _left_trigger_group() -> tuple[str, VDFValue]:
    return ("group", [("id", "4"), ("mode", "trigger"), ("name", "Left trigger alt fire"), ("inputs", [_button_input("edge", "mouse_button RIGHT, Alt fire / ADS, , ", haptic="2")])])


def _right_trigger_group() -> tuple[str, VDFValue]:
    return ("group", [("id", "5"), ("mode", "trigger"), ("name", "Right trigger fire"), ("inputs", [_button_input("edge", "mouse_button LEFT, Fire, , ", haptic="2")])])


def _switches_group() -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "6"),
            ("mode", "switches"),
            ("name", "Buttons and grips"),
            (
                "inputs",
                [
                    _button_input("button_escape", "key_press ESCAPE, Menu / pause, , "),
                    _button_input("button_menu", "key_press TAB, Automap, , "),
                    _button_input("left_bumper", "mouse_wheel SCROLL_DOWN, Previous weapon, , "),
                    _button_input("right_bumper", "mouse_wheel SCROLL_UP, Next weapon, , "),
                    _button_input("button_back_left_upper", "key_press SPACE, L4 jump, , ", repeat=True),
                    _button_input("button_back_right_upper", "key_press LEFT_CONTROL, R4 crouch, , ", repeat=True),
                    _button_input("button_back_left", "key_press F6, L5 quick save, , ", haptic="2"),
                    _long_press_input("button_back_right", "key_press F9, R5 long-press quick load, , ", long_press_ms=1500),
                ],
            ),
        ],
    )


def _dpad_group() -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "7"),
            ("mode", "dpad"),
            ("name", "Menu navigation"),
            (
                "inputs",
                [
                    _button_input("dpad_north", "key_press UP_ARROW, Menu up, , ", repeat=True),
                    _button_input("dpad_south", "key_press DOWN_ARROW, Menu down, , ", repeat=True),
                    _button_input("dpad_east", "key_press RIGHT_ARROW, Menu right, , ", repeat=True),
                    _button_input("dpad_west", "key_press LEFT_ARROW, Menu left, , ", repeat=True),
                ],
            ),
            ("settings", [("requires_click", "0"), ("haptic_intensity_override", "0")]),
        ],
    )


def _right_stick_group(layout: ControlScheme) -> tuple[str, VDFValue]:
    return (
        "group",
        [
            ("id", "8"),
            ("mode", "joystick_mouse"),
            ("name", "Right stick mouse"),
            ("description", "Conservative coarse mouse aim; right trackpad remains primary aim"),
            ("inputs", [_button_input("click", "mouse_button MIDDLE, Zoom / center view, , ")]),
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


def _default_preset() -> tuple[str, VDFValue]:
    return (
        "preset",
        [
            ("id", "0"),
            ("name", "Default"),
            (
                "group_source_bindings",
                [
                    ("6", "switch active"),
                    ("0", "button_diamond active"),
                    ("1", "left_trackpad active"),
                    ("2", "right_trackpad active"),
                    ("3", "joystick active"),
                    ("4", "left_trigger active"),
                    ("5", "right_trigger active"),
                    ("8", "right_joystick active"),
                    ("7", "dpad active"),
                ],
            ),
        ],
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
