"""Minimal Steam binary KeyValues reader/writer."""
from __future__ import annotations

import dataclasses
import struct
from collections import OrderedDict
from typing import Any

from doomdeck.domain.models import DoomDeckError


# Binary VDF value type bytes used by Steam shortcuts.vdf.
BKV_OBJECT = 0x00
BKV_STRING = 0x01
BKV_INT32 = 0x02
BKV_FLOAT32 = 0x03
BKV_UINT64 = 0x07
BKV_END = 0x08


@dataclasses.dataclass
class BKVValue:
    type_code: int
    value: Any


class BinaryVDF:
    """Minimal binary KeyValues reader/writer for Steam shortcuts.vdf.

    This intentionally supports only the value types normally seen in
    shortcuts.vdf and fails closed on unknown types so the script will not
    silently corrupt a user's Steam shortcut database.
    """

    def __init__(self, data: bytes = b"") -> None:
        self.data = data
        self.offset = 0

    @staticmethod
    def loads(data: bytes) -> OrderedDict[str, BKVValue]:
        parser = BinaryVDF(data)
        root = parser._read_object(implicit_root=True)
        return root

    @staticmethod
    def dumps(root: OrderedDict[str, BKVValue]) -> bytes:
        out = bytearray()
        for key, value in root.items():
            BinaryVDF._write_entry(out, key, value)
        out.append(BKV_END)
        return bytes(out)

    def _read_cstring(self) -> str:
        try:
            end = self.data.index(b"\x00", self.offset)
        except ValueError as exc:
            raise DoomDeckError("Invalid binary VDF: unterminated string") from exc
        raw = self.data[self.offset : end]
        self.offset = end + 1
        return raw.decode("utf-8", errors="replace")

    def _read_object(self, implicit_root: bool = False) -> OrderedDict[str, BKVValue]:
        obj: OrderedDict[str, BKVValue] = OrderedDict()
        while self.offset < len(self.data):
            type_code = self.data[self.offset]
            self.offset += 1
            if type_code == BKV_END:
                break

            key = self._read_cstring()

            if type_code == BKV_OBJECT:
                obj[key] = BKVValue(type_code, self._read_object())
            elif type_code == BKV_STRING:
                obj[key] = BKVValue(type_code, self._read_cstring())
            elif type_code == BKV_INT32:
                self._require_bytes(4)
                obj[key] = BKVValue(type_code, struct.unpack_from("<i", self.data, self.offset)[0])
                self.offset += 4
            elif type_code == BKV_FLOAT32:
                self._require_bytes(4)
                obj[key] = BKVValue(type_code, struct.unpack_from("<f", self.data, self.offset)[0])
                self.offset += 4
            elif type_code == BKV_UINT64:
                self._require_bytes(8)
                obj[key] = BKVValue(type_code, struct.unpack_from("<Q", self.data, self.offset)[0])
                self.offset += 8
            else:
                scope = "top-level" if implicit_root else "nested"
                raise DoomDeckError(
                    f"Unsupported binary VDF type byte 0x{type_code:02x} in {scope} object near offset {self.offset - 1}. "
                    "Not modifying shortcuts.vdf."
                )
        return obj

    def _require_bytes(self, count: int) -> None:
        if self.offset + count > len(self.data):
            raise DoomDeckError("Invalid binary VDF: truncated scalar value")

    @staticmethod
    def _write_cstring(out: bytearray, text: str) -> None:
        out.extend(text.encode("utf-8"))
        out.append(0)

    @staticmethod
    def _write_entry(out: bytearray, key: str, value: BKVValue) -> None:
        out.append(value.type_code)
        BinaryVDF._write_cstring(out, key)
        if value.type_code == BKV_OBJECT:
            for child_key, child_value in value.value.items():
                BinaryVDF._write_entry(out, child_key, child_value)
            out.append(BKV_END)
        elif value.type_code == BKV_STRING:
            BinaryVDF._write_cstring(out, str(value.value))
        elif value.type_code == BKV_INT32:
            out.extend(struct.pack("<i", int(value.value)))
        elif value.type_code == BKV_FLOAT32:
            out.extend(struct.pack("<f", float(value.value)))
        elif value.type_code == BKV_UINT64:
            out.extend(struct.pack("<Q", int(value.value)))
        else:
            raise DoomDeckError(f"Cannot write unsupported binary VDF type 0x{value.type_code:02x}")
