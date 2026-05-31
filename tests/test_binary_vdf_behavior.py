from __future__ import annotations

import unittest
from collections import OrderedDict

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.binary_vdf import (
    BKV_FLOAT32,
    BKV_INT32,
    BKV_OBJECT,
    BKV_STRING,
    BKV_UINT64,
    BKVValue,
    BinaryVDF,
)


class BinaryVDFBehaviorTests(unittest.TestCase):
    def test_round_trips_shortcut_style_values_without_reordering(self) -> None:
        shortcut = OrderedDict(
            {
                "appid": BKVValue(BKV_INT32, -123456),
                "appname": BKVValue(BKV_STRING, "Doom Runner"),
                "AllowOverlay": BKVValue(BKV_INT32, 1),
                "LastPlayed": BKVValue(BKV_UINT64, 123456789),
                "Scale": BKVValue(BKV_FLOAT32, 1.5),
            }
        )
        root = OrderedDict({"shortcuts": BKVValue(BKV_OBJECT, OrderedDict({"0": BKVValue(BKV_OBJECT, shortcut)}))})

        parsed = BinaryVDF.loads(BinaryVDF.dumps(root))

        self.assertEqual(list(parsed.keys()), ["shortcuts"])
        parsed_shortcuts = parsed["shortcuts"].value
        self.assertEqual(list(parsed_shortcuts.keys()), ["0"])
        parsed_entry = parsed_shortcuts["0"].value
        self.assertEqual(list(parsed_entry.keys()), list(shortcut.keys()))
        self.assertEqual(parsed_entry["appid"].value, -123456)
        self.assertEqual(parsed_entry["appname"].value, "Doom Runner")
        self.assertEqual(parsed_entry["AllowOverlay"].value, 1)
        self.assertEqual(parsed_entry["LastPlayed"].value, 123456789)
        self.assertAlmostEqual(parsed_entry["Scale"].value, 1.5)

    def test_rejects_unsupported_type_bytes_to_avoid_corrupting_shortcuts(self) -> None:
        with self.assertRaisesRegex(DoomDeckError, "Unsupported binary VDF type byte"):
            BinaryVDF.loads(b"\xffbad\x00")


if __name__ == "__main__":
    unittest.main()
