"""Steam compatibility-tool mapping helpers for non-Steam shortcuts."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterator, TypeAlias, cast

from doomdeck.domain.models import DoomDeckError

TextVDFObject: TypeAlias = OrderedDict[str, object]


def compat_mapping_key(appid: int) -> str:
    return str(appid & 0xFFFFFFFF)


def loads_text_vdf(text: str) -> TextVDFObject:
    try:
        tokens = list(_tokenize_text_vdf(text))
        index, root = _parse_object(tokens, 0, top_level=True)
        if index != len(tokens):
            raise ValueError("trailing tokens")
        return root
    except ValueError as exc:
        raise DoomDeckError(f"Could not parse Steam text VDF: {exc}") from exc


def dumps_text_vdf(root: TextVDFObject) -> str:
    lines: list[str] = []
    _dump_object(root, lines, indent=0)
    return "\n".join(lines) + "\n"


def load_text_vdf(path: Path) -> TextVDFObject:
    if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
        return OrderedDict({"UserLocalConfigStore": OrderedDict()})
    return loads_text_vdf(path.read_text(encoding="utf-8", errors="strict"))


def set_compat_tool_mapping(root: TextVDFObject, appid: int, compat_tool: str) -> None:
    user_store = _ensure_object(root, "UserLocalConfigStore")
    software = _ensure_object(user_store, "Software")
    valve = _ensure_object(software, "Valve")
    steam = _ensure_object(valve, "Steam")
    mapping = _ensure_object(steam, "CompatToolMapping")
    mapping[compat_mapping_key(appid)] = OrderedDict(
        {
            "name": compat_tool,
            "config": "",
            "priority": "250",
        }
    )


def _ensure_object(root: TextVDFObject, key: str) -> TextVDFObject:
    value = root.get(key)
    if isinstance(value, OrderedDict):
        return cast(TextVDFObject, value)
    if value is not None:
        raise DoomDeckError(f"Steam text VDF key is not an object: {key}")
    child: TextVDFObject = OrderedDict()
    root[key] = child
    return child


def _tokenize_text_vdf(text: str) -> Iterator[str]:
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "{}":
            yield char
            index += 1
            continue
        if char != '"':
            raise ValueError(f"unexpected character {char!r} at offset {index}")
        index += 1
        value: list[str] = []
        while index < len(text):
            char = text[index]
            if char == "\\":
                if index + 1 >= len(text):
                    raise ValueError("unterminated escape")
                value.append(text[index + 1])
                index += 2
                continue
            if char == '"':
                index += 1
                yield "".join(value)
                break
            value.append(char)
            index += 1
        else:
            raise ValueError("unterminated quoted string")


def _parse_object(tokens: list[str], index: int, *, top_level: bool = False) -> tuple[int, TextVDFObject]:
    root: TextVDFObject = OrderedDict()
    while index < len(tokens):
        if tokens[index] == "}":
            if top_level:
                raise ValueError("unexpected closing brace")
            return index + 1, root
        key = tokens[index]
        if key == "{":
            raise ValueError("unexpected opening brace")
        index += 1
        if index >= len(tokens):
            raise ValueError(f"missing value for key {key!r}")
        value = tokens[index]
        if value == "{":
            index, child = _parse_object(tokens, index + 1)
            root[key] = child
        elif value == "}":
            raise ValueError(f"missing value for key {key!r}")
        else:
            root[key] = value
            index += 1
    if not top_level:
        raise ValueError("missing closing brace")
    return index, root


def _dump_object(root: TextVDFObject, lines: list[str], indent: int) -> None:
    prefix = "\t" * indent
    for key, value in root.items():
        if isinstance(value, OrderedDict):
            lines.append(f'{prefix}"{_escape_text_vdf(key)}"')
            lines.append(f"{prefix}{{")
            _dump_object(cast(TextVDFObject, value), lines, indent + 1)
            lines.append(f"{prefix}}}")
        else:
            lines.append(f'{prefix}"{_escape_text_vdf(key)}"\t\t"{_escape_text_vdf(str(value))}"')


def _escape_text_vdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
