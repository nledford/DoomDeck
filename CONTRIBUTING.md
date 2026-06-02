# Contributing

Thanks for helping improve DoomDeck. This project is a Python CLI for Steam Deck Doom setup automation, so changes should stay conservative, testable, and safe to rerun.

## Development Setup

Install the local development environment with uv:

```bash
uv sync --dev
```

Useful commands are available through `just`:

```bash
just --list
just check
just package-check
```

The Justfile runs `uv` from your `PATH` by default. If `uv` is not on your `PATH`, set `UV=/path/to/uv` when running `just`.

## Project Layout

- `src/doomdeck/domain/` contains domain models, Doom/Steam Deck defaults, path layout, and WAD naming policy.
- `src/doomdeck/application/` contains application services, such as Doom Runner options generation.
- `src/doomdeck/infrastructure/` contains file format and integration helpers.
- `src/doomdeck/cli.py` contains the CLI orchestration and user-facing install/validate flows.
- `tests/` contains behavior-focused pytest tests.

Keep domain code independent from CLI, filesystem, network, and external service details where practical.

## Testing

Run the full local suite before submitting changes:

```bash
just check
```

For packaging-sensitive changes, also run:

```bash
just package-check
```

For GitHub Actions workflow changes, run:

```bash
actionlint .github/workflows/release.yml
```

## Commit Messages

DoomDeck uses Conventional Commits because Python Semantic Release reads commit history to choose the next version.

Use:

- `fix:` for bug fixes that should produce a patch release.
- `feat:` for user-facing features that should produce a minor release.
- `docs:`, `test:`, `refactor:`, `chore:`, `ci:`, `build:`, or `style:` for non-releasing changes.
- `BREAKING CHANGE:` in the commit body, or `!` in the commit type, for breaking changes.

## Releases

Do not publish manually. Releases are created by GitHub Actions after tests pass on `master`.

Local release previews:

```bash
just release-check
just release-dry-run
```

The release workflow may update `CHANGELOG.md`, package version metadata, and `uv.lock`. This project is not publishing to PyPI yet.

## Safety

- Do not commit Doom game files, WADs, downloaded mod archives, credentials, tokens, or user-specific Steam data.
- Keep installer behavior idempotent and rerunnable.
- Prefer behavior tests for user-visible flows and focused unit tests for parsing, archive handling, and file format logic.
