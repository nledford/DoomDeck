from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from doomdeck.cli import build_arg_parser, main, restore, select_release_asset, select_windows_release_asset
from doomdeck.domain.models import DoomDeckError


class CLIBehaviorTests(unittest.TestCase):
    def test_install_parser_accepts_stable_brutal_doom_channel(self) -> None:
        args = build_arg_parser().parse_args(["install", "--brutal-doom-channel", "stable"])

        self.assertEqual(args.command, "install")
        self.assertEqual(args.brutal_doom_channel, "stable")
        self.assertFalse(args.skip_downloads)
        self.assertEqual(args.proton_compat_tool, "proton_10")
        self.assertTrue(callable(args.func))

    def test_install_parser_accepts_proton_compat_tool_override(self) -> None:
        args = build_arg_parser().parse_args(["install", "--proton-compat-tool", "proton_experimental"])

        self.assertEqual(args.proton_compat_tool, "proton_experimental")

    def test_install_parser_rejects_moddb_wad_url_option(self) -> None:
        with self.assertRaises(SystemExit):
            build_arg_parser().parse_args(
                [
                    "install",
                    "--moddb-wad-url",
                    "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
                ]
            )

    def test_install_wads_parser_accepts_positional_moddb_wad_urls(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "install-wads",
                "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
                "https://www.moddb.com/games/doom-ii/addons/doom-2-the-way-id-did",
            ]
        )

        self.assertEqual(args.command, "install-wads")
        self.assertEqual(
            args.moddb_wad_urls,
            [
                "https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11",
                "https://www.moddb.com/games/doom-ii/addons/doom-2-the-way-id-did",
            ],
        )
        self.assertTrue(callable(args.func))

    def test_install_wads_command_runs_wad_installer_without_full_install_discovery(self) -> None:
        urls = ["https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11"]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve() / "Doom"
            expected = root / "pwads" / "DTWID.WAD"

            def fake_install_moddb_wad_urls(
                page_urls,
                downloads_dir,
                pwads_dir,
                backups_dir,
                dry_run,
                logger,
                force_download=False,
                user_agent="",
            ):
                self.assertEqual(page_urls, urls)
                self.assertEqual(downloads_dir, root / "downloads")
                self.assertEqual(pwads_dir, root / "pwads")
                self.assertEqual(backups_dir, root / "backups")
                self.assertFalse(dry_run)
                self.assertFalse(force_download)
                self.assertTrue(user_agent)
                return [expected]

            with (
                patch("doomdeck.cli.install_moddb_wad_urls", side_effect=fake_install_moddb_wad_urls),
                patch("doomdeck.cli.discover_steam") as discover_steam,
            ):
                result = main(["install-wads", "--root", str(root), urls[0]])

            self.assertEqual(result, 0)
            discover_steam.assert_not_called()
            self.assertTrue((root / "downloads").is_dir())
            self.assertTrue((root / "pwads").is_dir())
            self.assertTrue((root / "backups").is_dir())
            content_groups = json.loads((root / "configs" / "doomrunner" / "content-groups.json").read_text(encoding="utf-8"))
            self.assertEqual(content_groups["schema"], "doom-deck-setup/content-groups/v1")

    def test_parser_exposes_maintenance_commands(self) -> None:
        parser = build_arg_parser()

        for command in ["validate", "backup", "clean", "restore", "self-update"]:
            with self.subTest(command=command):
                argv = [command, "archive.tar.gz"] if command == "restore" else [command]
                args = parser.parse_args(argv)
                self.assertEqual(args.command, command)
                self.assertTrue(callable(args.func))

    def test_top_level_help_mentions_install_wads_command(self) -> None:
        self.assertIn("install-wads", build_arg_parser().format_help())

    def test_restore_rejects_wrong_backup_root_before_moving_existing_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Doom"
            root.mkdir()
            marker = root / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            archive_path = Path(temp_dir) / "wrong-root.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"wrong"
                member = tarfile.TarInfo("OtherRoot/file.txt")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))

            args = argparse.Namespace(root=str(root), backup_archive=str(archive_path), verbose=False, dry_run=False)

            with (
                patch("doomdeck.cli.configure_logging", return_value=logging.getLogger("test")),
                patch("doomdeck.cli.print_plan"),
                self.assertRaisesRegex(DoomDeckError, "Unexpected backup archive root"),
            ):
                restore(args)

            self.assertTrue(root.is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(root.parent.glob("Doom.pre-restore-*")), [])

    def test_self_update_parser_accepts_check_and_ref_options(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "self-update",
                "--check",
                "--ref",
                "main",
                "--install-dir",
                "/tmp/doomdeck/source",
            ]
        )

        self.assertEqual(args.command, "self-update")
        self.assertTrue(args.check)
        self.assertEqual(args.ref, "main")
        self.assertEqual(args.install_dir, "/tmp/doomdeck/source")

    def test_self_update_check_does_not_download_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "source"
            (install_dir / "src" / "doomdeck").mkdir(parents=True)
            (install_dir / "pyproject.toml").write_text("[project]\nname = 'doomdeck'\n", encoding="utf-8")

            with patch("doomdeck.cli.download_url") as download:
                result = main(
                    [
                        "self-update",
                        "--check",
                        "--install-dir",
                        str(install_dir),
                        "--archive-url",
                        "https://example.test/doomdeck.tar.gz",
                    ]
                )

            self.assertEqual(result, 0)
            download.assert_not_called()

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

    def test_windows_release_asset_selection_prefers_x86_64_zip_over_appimage_and_legacy(self) -> None:
        release = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "DoomRunner-1.9.2-Windows-legacy_i386-static_exe.zip",
                    "browser_download_url": "https://example.test/doomrunner-i386.zip",
                    "size": 1234,
                },
                {
                    "name": "DoomRunner-1.9.2-Linux-x86_64.AppImage",
                    "browser_download_url": "https://example.test/doomrunner.AppImage",
                    "size": 1234,
                },
                {
                    "name": "DoomRunner-1.9.2-Windows-recent_x86_64-static_exe.zip",
                    "browser_download_url": "https://example.test/doomrunner-x86_64.zip",
                    "size": 1234,
                },
            ],
        }

        with patch("doomdeck.cli.github_request_json", return_value=release):
            asset = select_windows_release_asset("Youda008/DoomRunner", logging.getLogger("test"))

        self.assertEqual(asset.name, "DoomRunner-1.9.2-Windows-recent_x86_64-static_exe.zip")

    def test_windows_release_asset_selection_finds_uzdoom_windows_zip(self) -> None:
        release = {
            "tag_name": "4.14.3",
            "assets": [
                {
                    "name": "Linux-UZDoom-4.14.3.AppImage",
                    "browser_download_url": "https://example.test/uzdoom.AppImage",
                    "size": 1234,
                },
                {
                    "name": "Windows-UZDoom-4.14.3.zip",
                    "browser_download_url": "https://example.test/uzdoom.zip",
                    "size": 1234,
                },
            ],
        }

        with patch("doomdeck.cli.github_request_json", return_value=release):
            asset = select_windows_release_asset("UZDoom/UZDoom", logging.getLogger("test"))

        self.assertEqual(asset.name, "Windows-UZDoom-4.14.3.zip")


if __name__ == "__main__":
    unittest.main()
