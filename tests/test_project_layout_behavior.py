from __future__ import annotations

import unittest
from pathlib import Path

from doomdeck.domain.paths import all_managed_dirs, build_dirs


class ProjectLayoutBehaviorTests(unittest.TestCase):
    def test_build_dirs_maps_the_managed_doom_tree(self) -> None:
        root = Path("/tmp/DoomDeckTest")

        dirs = build_dirs(root)

        self.assertEqual(dirs.root, root)
        self.assertEqual(dirs.doomrunner, root / "tools" / "doomrunner")
        self.assertEqual(dirs.uzdoom, root / "source-ports" / "uzdoom")
        self.assertEqual(dirs.brutal, root / "mods" / "brutal-doom")
        self.assertEqual(dirs.project_brutality, root / "mods" / "project-brutality")
        self.assertEqual(dirs.xdg_config, root / "configs" / "xdg-config")
        self.assertEqual(dirs.steam_input_config, root / "configs" / "steam-input")
        self.assertEqual(dirs.docs, root / "docs")

    def test_all_managed_dirs_lists_unique_directories_with_root_first(self) -> None:
        dirs = build_dirs(Path("/tmp/DoomDeckTest"))

        managed_dirs = all_managed_dirs(dirs)

        self.assertEqual(managed_dirs[0], dirs.root)
        self.assertEqual(len(managed_dirs), len(set(managed_dirs)))
        self.assertIn(dirs.downloads, managed_dirs)
        self.assertIn(dirs.backups, managed_dirs)
        self.assertIn(dirs.steam_input_config, managed_dirs)


if __name__ == "__main__":
    unittest.main()
