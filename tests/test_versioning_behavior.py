from __future__ import annotations

import re
import unittest
from pathlib import Path

import doomdeck

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def project_metadata() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject:
        return tomllib.load(pyproject)["project"]


class VersioningBehaviorTests(unittest.TestCase):
    def test_project_version_uses_semantic_versioning(self) -> None:
        version = project_metadata()["version"]

        self.assertIsInstance(version, str)
        self.assertRegex(version, SEMVER_PATTERN)

    def test_package_version_matches_project_metadata(self) -> None:
        self.assertEqual(doomdeck.__version__, project_metadata()["version"])

    def test_release_notes_describe_the_conventional_commit_bump_policy(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Conventional Commits", readme)
        self.assertIn("fix:", readme)
        self.assertIn("feat:", readme)
        self.assertIn("BREAKING CHANGE", readme)


if __name__ == "__main__":
    unittest.main()
