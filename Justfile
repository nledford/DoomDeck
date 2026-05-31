set shell := ["bash", "-cu"]

uv := env_var_or_default("UV", "/home/deck/.local/bin/uv")

# Show available recipes.
default:
    @just --list

# Sync the project environment, including dev dependencies.
[group("setup")]
sync:
    {{ uv }} sync

# Run the full test suite.
[group("test")]
test:
    {{ uv }} run pytest

# Run the test suite with verbose output.
[group("test")]
test-verbose:
    {{ uv }} run pytest -vv

# Run one test file or test node, e.g. `just test-path tests/test_cli_behavior.py`.
[group("test")]
test-path path:
    {{ uv }} run pytest "{{ path }}"

# Check that this Justfile is formatted.
[group("check")]
just-check:
    just --fmt --check

# Compile Python files to catch syntax/import-time parser errors.
[group("check")]
pycompile:
    {{ uv }} run python -m compileall -q doom_deck_setup.py src tests

# Check the installer shell script parses.
[group("check")]
installer-check:
    sh -n install.sh

# Run the standard local verification set.
[group("check")]
check: just-check installer-check pycompile test cli-help module-help legacy-help

# Show the packaged console-script help.
[group("cli")]
cli-help:
    {{ uv }} run doomdeck --help

# Show the `python -m doomdeck` help.
[group("cli")]
module-help:
    {{ uv }} run python -m doomdeck --help

# Show the legacy wrapper help.
[group("cli")]
legacy-help:
    python3 doom_deck_setup.py --help

# Preview validation without writing logs.
[group("cli")]
validate:
    {{ uv }} run doomdeck validate --dry-run

# Preview an install without downloads or Steam shortcut changes.
[group("cli")]
install-plan:
    {{ uv }} run doomdeck install --dry-run --skip-downloads --skip-steam-shortcut

# Build the source distribution and wheel.
[group("package")]
build:
    {{ uv }} build --clear

# Build and list wheel contents.
[group("package")]
wheel-files: build
    python3 -m zipfile -l "$(ls -1 dist/*.whl | head -n 1)"

# Build and list source distribution contents.
[group("package")]
sdist-files: build
    tar -tf "$(ls -1 dist/*.tar.gz | head -n 1)"

# Build both package artifacts and inspect their contents.
[group("package")]
package-check: build
    python3 -m zipfile -l "$(ls -1 dist/*.whl | head -n 1)"
    tar -tf "$(ls -1 dist/*.tar.gz | head -n 1)"

# Print the next semantic-release version without writing files, tags, or releases.
[group("release")]
release-check:
    {{ uv }} run semantic-release --noop version --print --no-push --no-vcs-release

# Preview semantic-release changelog, version, commit, tag, and build actions.
[group("release")]
release-dry-run:
    {{ uv }} run semantic-release --noop version --no-push --no-vcs-release

# Remove generated local artifacts.
[group("maintenance")]
clean:
    rm -rf build dist .pytest_cache .coverage htmlcov
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
