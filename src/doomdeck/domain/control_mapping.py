"""Domain concepts for DoomDeck controller-to-keyboard/mouse layouts."""
from __future__ import annotations

import dataclasses
import enum
from typing import Literal


class ControlProfile(str, enum.Enum):
    """Supported UZDoom/ZDoom-family control profile variants."""

    CLASSIC = "classic"
    MODERN = "modern"
    BRUTAL_DOOM = "brutal"
    PROJECT_BRUTALITY = "project-brutality"


class PhysicalInput(str, enum.Enum):
    """Steam Deck physical controls used by the generated Steam Input layout."""

    LEFT_STICK = "left_stick"
    RIGHT_STICK = "right_stick"
    RIGHT_TRACKPAD = "right_trackpad"
    LEFT_TRACKPAD = "left_trackpad"
    RIGHT_TRIGGER = "right_trigger"
    LEFT_TRIGGER = "left_trigger"
    RIGHT_BUMPER = "right_bumper"
    LEFT_BUMPER = "left_bumper"
    A = "a"
    B = "b"
    X = "x"
    Y = "y"
    DPAD = "dpad"
    MENU = "menu"
    VIEW = "view"
    L4 = "l4"
    R4 = "r4"
    L5 = "l5"
    R5 = "r5"


class ControlAction(str, enum.Enum):
    """User-facing Doom action represented by the layout."""

    MOVE = "move"
    AIM = "aim"
    FIRE = "fire"
    ALT_FIRE = "alt_fire"
    USE = "use"
    CROUCH = "crouch"
    JUMP = "jump"
    RELOAD = "reload"
    RUN_TOGGLE = "run_toggle"
    PREVIOUS_WEAPON = "previous_weapon"
    NEXT_WEAPON = "next_weapon"
    DIRECT_WEAPON = "direct_weapon"
    FLASHLIGHT_OR_ZOOM = "flashlight_or_zoom"
    QUICK_SAVE = "quick_save"
    QUICK_LOAD = "quick_load"
    MENU = "menu"
    MENU_NAVIGATION = "menu_navigation"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    AUTOMAP = "automap"
    MOD_ACTION = "mod_action"


OutputKind = Literal["key", "mouse_button", "mouse_wheel", "mouse", "radial_menu", "disabled"]
ActivationKind = Literal["Full_Press", "Soft_Press", "Long_Press", "chord"]


@dataclasses.dataclass(frozen=True)
class KeyboardMouseOutput:
    """A Steam Input output that intentionally stays in keyboard/mouse space."""

    kind: OutputKind
    value: str
    label: str

    def steam_input_binding(self) -> str:
        if self.kind == "key":
            return f"key_press {self.value}, {self.label}, , "
        if self.kind == "mouse_button":
            return f"mouse_button {self.value}, {self.label}, , "
        if self.kind == "mouse_wheel":
            return f"mouse_wheel {self.value}, {self.label}, , "
        if self.kind == "disabled":
            return "controller_action empty_binding, , "
        return self.value


@dataclasses.dataclass(frozen=True)
class SteamInputBinding:
    """A physical Steam Deck input mapped to one keyboard/mouse output."""

    physical_input: PhysicalInput
    action: ControlAction
    output: KeyboardMouseOutput
    activation: ActivationKind = "Full_Press"
    layer: str = "base"
    long_press_ms: int | None = None
    chord_button: str | None = None
    note: str = ""

    @property
    def is_quickload(self) -> bool:
        return self.action == ControlAction.QUICK_LOAD


@dataclasses.dataclass(frozen=True)
class SensitivitySettings:
    """Steam Input sensitivity/deadzone defaults documented for Deck users."""

    right_trackpad: int = 50
    right_stick: int = 35
    left_stick_deadzone: int = 6500
    right_stick_deadzone: int = 6000


@dataclasses.dataclass(frozen=True)
class ControlSchemeAlternative:
    name: str
    summary: str
    rejected_because: str


@dataclasses.dataclass(frozen=True)
class ControlScheme:
    """The selected cross-profile Steam Deck control scheme."""

    name: str
    description: str
    bindings: tuple[SteamInputBinding, ...]
    sensitivity: SensitivitySettings
    alternatives: tuple[ControlSchemeAlternative, ...]
    evidence: tuple[str, ...]
    rationale: str
    gyro_enabled: bool = False

    def bindings_for(self, physical_input: PhysicalInput) -> tuple[SteamInputBinding, ...]:
        return tuple(binding for binding in self.bindings if binding.physical_input == physical_input)


@dataclasses.dataclass(frozen=True)
class SourcePortBinding:
    input_name: str
    command: str


@dataclasses.dataclass(frozen=True)
class SourcePortAlias:
    name: str
    command: str


@dataclasses.dataclass(frozen=True)
class SourcePortControlProfile:
    """UZDoom/GZDoom-family interpretation of the Steam Input keyboard/mouse layout."""

    profile: ControlProfile
    description: str
    cvars: tuple[tuple[str, str], ...]
    aliases: tuple[SourcePortAlias, ...]
    bindings: tuple[SourcePortBinding, ...]

    @property
    def directory_name(self) -> str:
        return self.profile.value
