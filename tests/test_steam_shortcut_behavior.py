from __future__ import annotations

import unittest
from pathlib import Path

from doomdeck.infrastructure.binary_vdf import BKV_INT32, BKV_OBJECT, BKV_STRING
from doomdeck.infrastructure.steam_shortcuts import (
    empty_shortcuts_root,
    generate_shortcut_appid,
    make_shortcut_entry,
    shortcut_entries,
    upsert_shortcut,
)


class SteamShortcutBehaviorTests(unittest.TestCase):
    def test_shortcut_appid_is_stable_and_stored_as_signed_int32(self) -> None:
        exe_value = '"/home/deck/Games/Doom/tools/doomrunner/DoomRunner.exe"'
        appname = "Doom Runner"

        first = generate_shortcut_appid(exe_value, appname)
        second = generate_shortcut_appid(exe_value, appname)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, -(2**31))
        self.assertLess(first, 2**31)

    def test_make_shortcut_entry_uses_expected_steam_fields(self) -> None:
        entry = make_shortcut_entry(
            "Doom Runner",
            Path("/home/deck/Games/Doom/tools/doomrunner/DoomRunner.exe"),
            Path("/home/deck/Games/Doom/tools/doomrunner"),
            tags=["Doom", "Tools"],
            launch_options="-iwad DOOM2.WAD",
        )

        self.assertEqual(entry.type_code, BKV_OBJECT)
        fields = entry.value
        self.assertEqual(fields["appname"].type_code, BKV_STRING)
        self.assertEqual(fields["appname"].value, "Doom Runner")
        self.assertEqual(fields["appid"].type_code, BKV_INT32)
        self.assertEqual(fields["AllowOverlay"].value, 1)
        self.assertEqual(fields["LaunchOptions"].value, "-iwad DOOM2.WAD")
        self.assertEqual(fields["tags"].type_code, BKV_OBJECT)
        self.assertEqual(fields["tags"].value["0"].value, "Doom")
        self.assertEqual(fields["tags"].value["1"].value, "Tools")

    def test_upsert_shortcut_adds_then_updates_same_shortcut(self) -> None:
        root = empty_shortcuts_root()

        created = upsert_shortcut(
            root,
            "Doom Runner",
            Path("/home/deck/Games/Doom/launchers/doom-runner.sh"),
            Path("/home/deck/Games/Doom"),
            tags=["Doom"],
            launch_options="",
        )
        updated = upsert_shortcut(
            root,
            "Doom Runner",
            Path("/home/deck/Games/Doom/launchers/doom-runner-v2.sh"),
            Path("/home/deck/Games/Doom"),
            tags=["Doom", "Tools"],
            launch_options="-config modern.ini",
        )

        shortcuts = shortcut_entries(root)
        self.assertTrue(created.created)
        self.assertFalse(updated.created)
        self.assertEqual(created.key, "0")
        self.assertEqual(updated.key, "0")
        self.assertEqual(list(shortcuts.keys()), ["0"])
        self.assertEqual(shortcuts["0"].value["exe"].value, '"/home/deck/Games/Doom/launchers/doom-runner-v2.sh"')
        self.assertEqual(shortcuts["0"].value["LaunchOptions"].value, "-config modern.ini")
        self.assertEqual(shortcuts["0"].value["tags"].value["1"].value, "Tools")
        self.assertIsInstance(updated.appid, int)

    def test_upsert_shortcut_can_keep_distinct_shortcuts_with_same_executable(self) -> None:
        root = empty_shortcuts_root()
        exe = Path("/home/deck/Games/Doom/source-ports/uzdoom/uzdoom.exe")

        first = upsert_shortcut(
            root,
            "DoomDeck - UZDoom",
            exe,
            exe.parent,
            tags=["Doom"],
            launch_options="-iwad DOOM2.WAD",
            match_exe=False,
        )
        second = upsert_shortcut(
            root,
            "DoomDeck - Brutal Doom",
            exe,
            exe.parent,
            tags=["Doom"],
            launch_options="-iwad DOOM2.WAD -file brutal-doom.pk3",
            match_exe=False,
        )

        shortcuts = shortcut_entries(root)
        self.assertTrue(first.created)
        self.assertTrue(second.created)
        self.assertEqual(list(shortcuts.keys()), ["0", "1"])
        self.assertEqual(shortcuts["0"].value["appname"].value, "DoomDeck - UZDoom")
        self.assertEqual(shortcuts["1"].value["appname"].value, "DoomDeck - Brutal Doom")


if __name__ == "__main__":
    unittest.main()
