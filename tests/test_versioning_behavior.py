from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Any, cast

import doomdeck
import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def pyproject_data() -> dict[str, Any]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject:
        return tomllib.load(pyproject)


def project_metadata() -> dict[str, Any]:
    return cast(dict[str, Any], pyproject_data()["project"])


def release_workflow() -> dict[str, Any]:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
    return cast(dict[str, Any], yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader))


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
        self.assertTrue(any(dependency.startswith("ruff") for dependency in dev_dependencies))
        self.assertTrue(any(dependency.startswith("ty") for dependency in dev_dependencies))
        self.assertEqual(semantic_release["assets"], ["uv.lock"])
        self.assertTrue(semantic_release["allow_zero_version"])
        self.assertEqual(semantic_release["build_command"], "uv lock && uv build --clear")
        self.assertIn("[skip ci]", semantic_release["commit_message"])
        self.assertEqual(semantic_release["commit_parser"], "conventional")
        self.assertEqual(semantic_release["tag_format"], "v{version}")
        self.assertEqual(semantic_release["version_toml"], ["pyproject.toml:project.version"])
        self.assertEqual(
            semantic_release["version_variables"],
            ["src/doomdeck/__init__.py:__version__"],
        )
        self.assertEqual(
            semantic_release["changelog"]["insertion_flag"],
            "<!-- version list -->",
        )
        self.assertEqual(
            semantic_release["changelog"]["default_templates"]["changelog_file"],
            "CHANGELOG.md",
        )
        self.assertTrue(semantic_release["remote"]["ignore_token_for_push"])
        self.assertTrue(semantic_release["publish"]["upload_to_vcs_release"])

    def test_justfile_exposes_noop_release_commands(self) -> None:
        justfile = (PROJECT_ROOT / "Justfile").read_text(encoding="utf-8")

        self.assertIn('[group("release")]', justfile)
        self.assertIn("release-check:", justfile)
        self.assertIn("semantic-release --noop version --print --no-push --no-vcs-release", justfile)
        self.assertIn("release-dry-run:", justfile)
        self.assertIn("semantic-release --noop version --no-push --no-vcs-release", justfile)

    def test_project_checks_run_lint_and_typecheck(self) -> None:
        pyproject = pyproject_data()
        justfile = (PROJECT_ROOT / "Justfile").read_text(encoding="utf-8")

        self.assertEqual(pyproject["tool"]["ruff"]["lint"]["extend-select"], ["C901"])
        self.assertEqual(pyproject["tool"]["ruff"]["lint"]["mccabe"]["max-complexity"], 15)
        self.assertIn("ruff-check:", justfile)
        self.assertIn("{{ uv }} run ruff check .", justfile)
        self.assertIn("ty-check:", justfile)
        self.assertIn("{{ uv }} run ty check", justfile)
        self.assertIn("check: just-check installer-check pycompile ruff-check ty-check test", justfile)

    def test_changelog_is_ready_for_semantic_release_updates(self) -> None:
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("# Changelog", changelog)
        self.assertIn("<!-- version list -->", changelog)
        self.assertIn("## v0.2.0", changelog)
        self.assertIn("## v0.1.0", changelog)

    def test_readme_describes_the_current_release_check_result(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("current release is `0.2.0`", readme)
        self.assertIn("`v0.2.0`", readme)
        self.assertIn("reports `0.2.0` as already released", readme)

    def test_justfile_uses_uv_from_path_by_default(self) -> None:
        justfile = (PROJECT_ROOT / "Justfile").read_text(encoding="utf-8")

        self.assertIn('uv := env_var_or_default("UV", "uv")', justfile)
        self.assertNotIn("/home/deck/.local/bin/uv", justfile)

    def test_github_release_workflow_runs_tests_before_publishing_release_assets(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        workflow_data = release_workflow()

        self.assertEqual(workflow_data["name"], "Release")
        self.assertIn("test", workflow_data["jobs"])
        self.assertIn("release", workflow_data["jobs"])
        self.assertIn("push:", workflow)
        self.assertIn('branches: ["master"]', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertEqual(
            workflow_data["jobs"]["test"]["strategy"]["matrix"]["python-version"],
            ["3.10", "3.11", "3.12", "3.13", "3.14"],
        )
        self.assertIn("uv python install ${{ matrix.python-version }}", workflow)
        self.assertIn("uv run pytest", workflow)
        self.assertIn("uv run ruff check .", workflow)
        self.assertIn("uv run ty check", workflow)
        self.assertIn("uv build --clear", workflow)
        self.assertIn("uv run semantic-release version", workflow)
        self.assertIn("uv run semantic-release publish", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("GIT_COMMIT_AUTHOR: github-actions[bot]", workflow)
        self.assertNotIn("pypi", workflow.lower())


if __name__ == "__main__":
    unittest.main()
