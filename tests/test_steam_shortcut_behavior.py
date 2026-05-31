from __future__ import annotations

import unittest
from pathlib import Path

from doomdeck.infrastructure.binary_vdf import BKV_INT32, BKV_OBJECT, BKV_STRING
from doomdeck.infrastructure.steam_shortcuts import generate_shortcut_appid, make_shortcut_entry


class SteamShortcutBehaviorTests(unittest.TestCase):
    def test_shortcut_appid_is_stable_and_stored_as_signed_int32(self) -> None:
        exe_value = '"/home/deck/Games/Doom/tools/doomrunner/DoomRunner.AppImage"'
        appname = "Doom Runner"

        first = generate_shortcut_appid(exe_value, appname)
        second = generate_shortcut_appid(exe_value, appname)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, -(2**31))
        self.assertLess(first, 2**31)

    def test_make_shortcut_entry_uses_expected_steam_fields(self) -> None:
        entry = make_shortcut_entry(
            "Doom Runner",
            Path("/home/deck/Games/Doom/tools/doomrunner/DoomRunner.AppImage"),
            Path("/home/deck/Games/Doom/tools/doomrunner"),
            tags=["Doom", "Tools"],
        )

        self.assertEqual(entry.type_code, BKV_OBJECT)
        fields = entry.value
        self.assertEqual(fields["appname"].type_code, BKV_STRING)
        self.assertEqual(fields["appname"].value, "Doom Runner")
        self.assertEqual(fields["appid"].type_code, BKV_INT32)
        self.assertEqual(fields["AllowOverlay"].value, 1)
        self.assertEqual(fields["tags"].type_code, BKV_OBJECT)
        self.assertEqual(fields["tags"].value["0"].value, "Doom")
        self.assertEqual(fields["tags"].value["1"].value, "Tools")


if __name__ == "__main__":
    unittest.main()
