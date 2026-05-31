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


def pyproject_data() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject:
        return tomllib.load(pyproject)


def project_metadata() -> dict[str, object]:
    return pyproject_data()["project"]


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
        self.assertIn("just release-check", readme)

    def test_semantic_release_is_configured_for_local_version_checks(self) -> None:
        pyproject = pyproject_data()
        dev_dependencies = pyproject["dependency-groups"]["dev"]
        semantic_release = pyproject["tool"]["semantic_release"]

        self.assertTrue(
            any(dependency.startswith("python-semantic-release") for dependency in dev_dependencies)
        )
        self.assertTrue(semantic_release["allow_zero_version"])
        self.assertEqual(semantic_release["commit_parser"], "conventional")
        self.assertEqual(semantic_release["tag_format"], "v{version}")
        self.assertEqual(semantic_release["version_toml"], ["pyproject.toml:project.version"])
        self.assertEqual(
            semantic_release["version_variables"],
            ["src/doomdeck/__init__.py:__version__"],
        )
        self.assertTrue(semantic_release["remote"]["ignore_token_for_push"])
        self.assertFalse(semantic_release["publish"]["upload_to_vcs_release"])

    def test_justfile_exposes_a_noop_release_check(self) -> None:
        justfile = (PROJECT_ROOT / "Justfile").read_text(encoding="utf-8")

        self.assertIn('[group("release")]', justfile)
        self.assertIn("release-check:", justfile)
        self.assertIn("semantic-release --noop version --print --no-push --no-vcs-release", justfile)


if __name__ == "__main__":
    unittest.main()
