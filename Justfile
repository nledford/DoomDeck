set shell := ["bash", "-cu"]

uv := env_var_or_default("UV", "uv")

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

# Run the test suite with package coverage.
[group("test")]
coverage:
    {{ uv }} run pytest --cov=doomdeck --cov-report=term-missing

# Check that this Justfile is formatted.
[group("check")]
just-check:
    just --fmt --check

# Compile Python files to catch syntax/import-time parser errors.
[group("check")]
pycompile:
    {{ uv }} run python -m compileall -q doom_deck_setup.py src tests

# Run Python lint checks.
[group("check")]
ruff-check:
    {{ uv }} run ruff check .

# Run Python type checks.
[group("check")]
ty-check:
    {{ uv }} run ty check

# Check the installer shell script parses.
[group("check")]
installer-check:
    sh -n install.sh

# Verify the checked-in runtime dependency export matches uv.lock.
[group("check")]
runtime-lock-check:
    @tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT; {{ uv }} export --frozen --no-dev --no-emit-project --no-header --format requirements.txt --output-file "$tmp" >/dev/null; diff -u requirements-runtime.lock "$tmp"

# Run the standard local verification set.
[group("check")]
check: just-check installer-check runtime-lock-check pycompile ruff-check ty-check test cli-help module-help legacy-help

# Report cyclomatic complexity.
[group("analysis")]
complexity:
    {{ uv }} run radon cc src tests -s

# Report maintainability index.
[group("analysis")]
maintainability:
    {{ uv }} run radon mi src tests -s

# Audit Python dependencies for known vulnerabilities.
[group("analysis")]
audit:
    {{ uv }} run pip-audit

# Check declared dependencies against imports.
[group("analysis")]
deps:
    {{ uv }} run deptry . --known-first-party doomdeck

# Fail on severe complexity regressions.
[group("analysis")]
complexity-gate:
    @output="$({{ uv }} run radon cc src tests -s -n E 2>&1)"; status=$?; if [ "$status" -ne 0 ]; then echo "$output"; exit "$status"; fi; if [ -n "$output" ]; then echo "$output"; exit 1; fi

# Reject new C-ranked files while allowing the documented existing baseline.
[group("analysis")]
maintainability-gate:
    @tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT; {{ uv }} run radon mi src tests -n C > "$tmp"; diff -u maintainability-baseline.txt "$tmp"

# Run non-gating local analysis reports.
[group("analysis")]
analysis: coverage complexity maintainability audit deps

# Run stricter local quality gates.
[group("analysis")]
quality: coverage complexity-gate maintainability-gate audit deps

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

# Upgrade locked dependencies and sync the local environment.
[group("maintenance")]
update:
    {{ uv }} lock --upgrade
    {{ uv }} sync

# Install the console script as a uv tool from this checkout.
[group("setup")]
install:
    {{ uv }} tool install --force .

# Print the next semantic-release version without writing files, tags, or releases.
[group("release")]
release-check:
    @set -euo pipefail; current_version="$( {{ uv }} run python -c 'import doomdeck; print(doomdeck.__version__)' )"; current_tag="v$current_version"; if git rev-parse --verify --quiet "refs/tags/$current_tag" >/dev/null && ! git merge-base --is-ancestor "$current_tag^{commit}" HEAD; then {{ uv }} run semantic-release --noop version --patch --print --no-push --no-vcs-release; else {{ uv }} run semantic-release --noop version --print --no-push --no-vcs-release; fi

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
