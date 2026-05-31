"""Steam non-Steam shortcut helpers."""
from __future__ import annotations

import zlib
from collections import OrderedDict
from pathlib import Path

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.binary_vdf import BKV_INT32, BKV_OBJECT, BKV_STRING, BKVValue, BinaryVDF


def steam_quote_path(path: Path) -> str:
    return f'"{path}"'


def generate_shortcut_appid(exe_value: str, appname: str) -> int:
    # Stable non-Steam shortcut appid. Steam stores this as int32 in shortcuts.vdf.
    unsigned = (zlib.crc32(f"{exe_value}{appname}".encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
    return unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned


def load_shortcuts(path: Path) -> OrderedDict[str, BKVValue]:
    if not path.exists():
        return OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict())})
    data = path.read_bytes()
    if not data:
        return OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict())})
    parsed = BinaryVDF.loads(data)
    if "shortcuts" not in parsed or parsed["shortcuts"].type_code != BKV_OBJECT:
        raise DoomDeckError("shortcuts.vdf does not contain a top-level shortcuts object")
    return parsed


def get_bkv_str(obj: OrderedDict[str, BKVValue], *names: str) -> str:
    lower_map = {key.lower(): key for key in obj.keys()}
    for name in names:
        key = name if name in obj else lower_map.get(name.lower())
        if key and obj[key].type_code == BKV_STRING:
            return str(obj[key].value)
    return ""


def make_shortcut_entry(appname: str, exe: Path, start_dir: Path, tags: list[str]) -> BKVValue:
    exe_value = steam_quote_path(exe)
    start_dir_value = steam_quote_path(start_dir)
    fields: OrderedDict[str, BKVValue] = OrderedDict()
    fields["appid"] = BKVValue(BKV_INT32, generate_shortcut_appid(exe_value, appname))
    fields["appname"] = BKVValue(BKV_STRING, appname)
    fields["exe"] = BKVValue(BKV_STRING, exe_value)
    fields["StartDir"] = BKVValue(BKV_STRING, start_dir_value)
    fields["icon"] = BKVValue(BKV_STRING, "")
    fields["ShortcutPath"] = BKVValue(BKV_STRING, "")
    fields["LaunchOptions"] = BKVValue(BKV_STRING, "")
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
