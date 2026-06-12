"""Steam non-Steam shortcut helpers."""
from __future__ import annotations

import dataclasses
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import cast

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.binary_vdf import BKV_INT32, BKV_OBJECT, BKV_STRING, BKVValue, BinaryVDF


@dataclasses.dataclass(frozen=True)
class ShortcutUpsertResult:
    key: str
    created: bool
    appid: int


def steam_quote_path(path: Path) -> str:
    return f'"{path}"'


def generate_shortcut_appid(exe_value: str, appname: str) -> int:
    # Stable non-Steam shortcut appid. Steam stores this as int32 in shortcuts.vdf.
    unsigned = (zlib.crc32(f"{exe_value}{appname}".encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
    return unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned


def empty_shortcuts_root() -> OrderedDict[str, BKVValue]:
    return OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict())})


def shortcut_entries(root: OrderedDict[str, BKVValue]) -> OrderedDict[str, BKVValue]:
    shortcuts = root.get("shortcuts")
    if shortcuts is None or shortcuts.type_code != BKV_OBJECT:
        raise DoomDeckError("shortcuts.vdf does not contain a top-level shortcuts object")
    return cast(OrderedDict[str, BKVValue], shortcuts.value)


def load_shortcuts(path: Path) -> OrderedDict[str, BKVValue]:
    if not path.exists():
        return empty_shortcuts_root()
    data = path.read_bytes()
    if not data:
        return empty_shortcuts_root()
    parsed = BinaryVDF.loads(data)
    shortcut_entries(parsed)
    return parsed


def get_bkv_str(obj: OrderedDict[str, BKVValue], *names: str) -> str:
    lower_map = {key.lower(): key for key in obj.keys()}
    for name in names:
        key = name if name in obj else lower_map.get(name.lower())
        if key and obj[key].type_code == BKV_STRING:
            return str(obj[key].value)
    return ""


def make_shortcut_entry(appname: str, exe: Path, start_dir: Path, tags: list[str], launch_options: str = "") -> BKVValue:
    exe_value = steam_quote_path(exe)
    start_dir_value = steam_quote_path(start_dir)
    appid = generate_shortcut_appid(exe_value, appname)
    fields: OrderedDict[str, BKVValue] = OrderedDict()
    fields["appid"] = BKVValue(BKV_INT32, appid)
    fields["appname"] = BKVValue(BKV_STRING, appname)
    fields["exe"] = BKVValue(BKV_STRING, exe_value)
    fields["StartDir"] = BKVValue(BKV_STRING, start_dir_value)
    fields["icon"] = BKVValue(BKV_STRING, "")
    fields["ShortcutPath"] = BKVValue(BKV_STRING, "")
    fields["LaunchOptions"] = BKVValue(BKV_STRING, launch_options)
    fields["IsHidden"] = BKVValue(BKV_INT32, 0)
    fields["AllowDesktopConfig"] = BKVValue(BKV_INT32, 1)
    fields["AllowOverlay"] = BKVValue(BKV_INT32, 1)
    fields["OpenVR"] = BKVValue(BKV_INT32, 0)
    fields["Devkit"] = BKVValue(BKV_INT32, 0)
    fields["DevkitGameID"] = BKVValue(BKV_STRING, "")
    fields["DevkitOverrideAppID"] = BKVValue(BKV_INT32, 0)
    fields["LastPlayTime"] = BKVValue(BKV_INT32, 0)
    fields["FlatpakAppID"] = BKVValue(BKV_STRING, "")
    tag_obj: OrderedDict[str, BKVValue] = OrderedDict()
    for idx, tag in enumerate(tags):
        tag_obj[str(idx)] = BKVValue(BKV_STRING, tag)
    fields["tags"] = BKVValue(BKV_OBJECT, tag_obj)
    return BKVValue(BKV_OBJECT, fields)


def upsert_shortcut(
    root: OrderedDict[str, BKVValue],
    appname: str,
    exe: Path,
    start_dir: Path,
    tags: list[str],
    launch_options: str = "",
    match_exe: bool = True,
) -> ShortcutUpsertResult:
    shortcuts = shortcut_entries(root)
    target_exe = steam_quote_path(exe)
    existing_key: str | None = None
    for key, value in shortcuts.items():
        if value.type_code != BKV_OBJECT:
            continue
        entry = cast(OrderedDict[str, BKVValue], value.value)
        existing_name = get_bkv_str(entry, "appname", "AppName")
        existing_exe = get_bkv_str(entry, "exe", "Exe")
        if existing_name == appname or (match_exe and existing_exe == target_exe):
            existing_key = key
            break

    entry_value = make_shortcut_entry(appname, exe, start_dir, tags=tags, launch_options=launch_options)
    appid_value = cast(OrderedDict[str, BKVValue], entry_value.value)["appid"].value
    appid = int(appid_value)
    if existing_key is not None:
        shortcuts[existing_key] = entry_value
        return ShortcutUpsertResult(existing_key, created=False, appid=appid)

    used = {int(key) for key in shortcuts.keys() if key.isdigit()}
    index = 0
    while index in used:
        index += 1
    key = str(index)
    shortcuts[key] = entry_value
    return ShortcutUpsertResult(key, created=True, appid=appid)
