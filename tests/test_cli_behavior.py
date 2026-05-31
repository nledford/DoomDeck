from __future__ import annotations

import unittest

from doomdeck.cli import build_arg_parser


class CLIBehaviorTests(unittest.TestCase):
    def test_install_parser_accepts_stable_brutal_doom_channel(self) -> None:
        args = build_arg_parser().parse_args(["install", "--brutal-doom-channel", "stable"])

        self.assertEqual(args.command, "install")
        self.assertEqual(args.brutal_doom_channel, "stable")
        self.assertFalse(args.skip_downloads)
        self.assertTrue(callable(args.func))

    def test_parser_exposes_maintenance_commands(self) -> None:
        parser = build_arg_parser()

        for command in ["validate", "backup", "clean", "restore"]:
            with self.subTest(command=command):
                argv = [command, "archive.tar.gz"] if command == "restore" else [command]
                args = parser.parse_args(argv)
                self.assertEqual(args.command, command)
                self.assertTrue(callable(args.func))


if __name__ == "__main__":
    unittest.main()
