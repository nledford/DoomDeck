from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from doomdeck.cli import build_arg_parser, select_release_asset
from doomdeck.domain.models import DoomDeckError


class CLIBehaviorTests(unittest.TestCase):
    def test_install_parser_accepts_stable_brutal_doom_channel(self) -> None:
        args = build_arg_parser().parse_args(["install", "--brutal-doom-channel", "stable"])

        self.assertEqual(args.command, "install")
        self.assertEqual(args.brutal_doom_channel, "stable")
        self.assertFalse(args.skip_downloads)
        self.assertTrue(callable(args.func))

    def test_install_parser_accepts_repeatable_moddb_wad_urls(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "install",
                "--moddb-wad-url",
                "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
                "--moddb-wad-url",
                "https://www.moddb.com/games/doom-ii/addons/doom-2-the-way-id-did",
            ]
        )

        self.assertEqual(
            args.moddb_wad_urls,
            [
                "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
                "https://www.moddb.com/games/doom-ii/addons/doom-2-the-way-id-did",
            ],
        )

    def test_parser_exposes_maintenance_commands(self) -> None:
        parser = build_arg_parser()

        for command in ["validate", "backup", "clean", "restore"]:
            with self.subTest(command=command):
                argv = [command, "archive.tar.gz"] if command == "restore" else [command]
                args = parser.parse_args(argv)
                self.assertEqual(args.command, command)
                self.assertTrue(callable(args.func))

    def test_release_asset_selection_rejects_assets_missing_download_urls(self) -> None:
        release = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "uzdoom-linux-x86_64.AppImage",
                    "size": 1234,
                }
            ],
        }

        with patch("doomdeck.cli.github_request_json", return_value=release):
            with self.assertRaisesRegex(DoomDeckError, "assets\\.0\\.browser_download_url"):
                select_release_asset("ZDoom/UZDoom", False, logging.getLogger("test"))

    def test_release_asset_selection_rejects_non_list_assets(self) -> None:
        release = {
            "tag_name": "v1.2.3",
            "assets": {
                "name": "uzdoom-linux-x86_64.AppImage",
                "browser_download_url": "https://example.test/uzdoom.AppImage",
            },
        }

        with patch("doomdeck.cli.github_request_json", return_value=release):
            with self.assertRaisesRegex(DoomDeckError, "assets"):
                select_release_asset("ZDoom/UZDoom", False, logging.getLogger("test"))


if __name__ == "__main__":
    unittest.main()
