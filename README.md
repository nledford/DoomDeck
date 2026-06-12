# DoomDeck

Steam Deck Doom modding setup automation for Doom Runner, UZDoom, Brutal Doom, and Project Brutality.

## What This Tool Does

`doomdeck` is a helper command for setting up Doom modding on a Steam Deck without manually wiring together engines, game files, launchers, and Steam shortcuts.

In plain terms, it:

- Creates a managed Doom folder, by default at `$HOME/Games/Doom` (`/home/deck/Games/Doom` on Steam Deck).
- Downloads and installs the Windows builds of Doom Runner and UZDoom.
- Finds your Steam-installed `DOOM + DOOM II` files and copies the usable Doom game data files into the managed folder.
- Looks for add-on WAD files from the Steam install and copies those too.
- Downloads or installs Brutal Doom.
- Downloads or installs Project Brutality.
- Creates ready-to-use Doom Runner presets.
- Creates exactly one Steam shortcut for Doom Runner, with all generated presets available inside Doom Runner.
- Writes Steam Deck-friendly UZDoom controller, display, graphics, quick save, and quick load settings.
- Forces the generated Doom Runner shortcut to use Steam Proton by default, so Steam Input can expose Deck, Xbox, PlayStation, and other supported controllers to UZDoom as gamepads.
- Backs up files before replacing important generated files or modifying Steam shortcut/config files.

The tool is designed to be rerun. If you already ran it once, running it again updates the setup and reuses files that are already current.

## What It Does Not Do

This repo does not include Doom game files. You need to own and install `DOOM + DOOM II` through Steam first. DoomDeck copies your existing Steam game data into the managed folder so Doom Runner and UZDoom can use it.

DoomDeck does not require root access. It works in your user folders.

## Requirements

- Steam Deck or Linux.
- Python 3.10 or newer.
- `uv` if you are running from a source checkout or installing with uv.
- Steam `DOOM + DOOM II` installed.
- Internet access if you want DoomDeck to download Doom Runner, UZDoom, Brutal Doom, or Project Brutality.

## Running DoomDeck

Install the latest source version directly from GitHub:

```bash
curl -LsSf https://raw.githubusercontent.com/nledford/DoomDeck/master/install.sh | sh
```

The installer downloads the GitHub source archive, creates an isolated Python environment under `~/.local/share/doomdeck/source/.venv`, installs DoomDeck's runtime Python dependencies there, and creates a `doomdeck` command in `~/.local/bin`. This only installs DoomDeck itself; run `doomdeck install` separately when you are ready to create or update the managed Doom setup.

The command installed by this method includes the `self-update` subcommand. To update that installed DoomDeck command later:

```bash
doomdeck self-update
```

From this repo checkout, run commands through uv:

```bash
uv run doomdeck --help
```

After the package is published to PyPI, you will be able to run it without cloning the repo:

```bash
uvx doomdeck install
```

For a permanent command on your PATH:

```bash
uv tool install doomdeck
doomdeck install
```

Until the package is published, uv can also run it directly from GitHub:

```bash
uvx --from git+https://github.com/nledford/DoomDeck.git doomdeck install
```

The old script path still works from a checkout for compatibility:

```bash
python3 doom_deck_setup.py install
```

## Quick Start

From the repo folder:

```bash
uv run doomdeck install
```

After it finishes, restart Steam. A single `Doom Runner` non-Steam game should appear. Launch Doom Runner from Steam, then choose a generated preset from Doom Runner's UI. `Vanilla Doom` and `UZDoom` appear when DoomDeck finds a usable IWAD; `Brutal Doom` and `Project Brutality` appear when their managed mod files are installed.

To check the setup later:

```bash
uv run doomdeck validate
```

To see what an install would do without changing files:

```bash
uv run doomdeck install --dry-run
```

## Managed Folder Layout

By default, DoomDeck manages this folder:

```text
$HOME/Games/Doom/
```

On Steam Deck, this normally resolves to:

```text
/home/deck/Games/Doom/
```

Important subfolders include:

- `tools/doomrunner/` - Windows Doom Runner executable and primary generated `options.json`.
- `source-ports/uzdoom/` - Windows UZDoom executable.
- `iwads/` - Main Doom game data files copied from Steam.
- `pwads/` - Add-on WAD files copied from Steam.
- `mods/brutal-doom/` - Brutal Doom files and metadata.
- `mods/project-brutality/` - Project Brutality files and metadata.
- `configs/doomrunner/` - Generated Doom Runner manifest and policy files.
- `configs/uzdoom/` - Generated UZDoom configs.
- `launchers/` - Helper scripts for generated presets. These are not added to Steam.
- `saves/` - Save-game folders used by presets.
- `screenshots/` - Screenshot folders used by presets.
- `downloads/` - Downloaded upstream files.
- `backups/` - Backups made before replacements.
- `logs/` - Script log files.
- `docs/` - Extra generated setup notes.

## Commands

DoomDeck uses subcommands:

```bash
doomdeck <command> [options]
```

When running from a source checkout, use `uv run doomdeck` in place of `doomdeck`.

Available commands:

| Command | What it does | When to use it |
| --- | --- | --- |
| `install` | Creates or updates the full DoomDeck setup. | Use this first. Rerun it when you want to update downloaded tools, mods, configs, or Steam launch metadata. |
| `install-wads` | Downloads ModDB WAD archives into the managed `pwads/` folder only. | Use this after the base install when you want to add or update map WADs without running the full installer. |
| `validate` | Checks whether the setup looks complete and prints a pass/warn/fail report. | Use this after install, after moving files, or when something does not launch correctly. |
| `backup` | Creates a `.tar.gz` backup of the managed Doom folder. | Use this before large manual changes or before experimenting. |
| `clean` | Moves or deletes the managed Doom folder safely. | Use this when you want to remove the generated setup and start over. |
| `restore` | Restores a backup archive. | Use this to roll back to a previous backed-up managed folder. |
| `self-update` | Updates the DoomDeck command installed by `install.sh`. | Use this when you want the latest DoomDeck application code without rerunning the shell installer. |

## Common Options

These options work with the managed Doom setup commands: `install`, `install-wads`, `validate`, `backup`, `clean`, and `restore`.

| Option | What it means | When to use it |
| --- | --- | --- |
| `-h`, `--help` | Shows help for the selected command. | Use this when you want a quick reminder in the terminal. |
| `--root ROOT` | Changes the managed Doom folder. Default: `$HOME/Games/Doom`. | Use this if you want everything stored somewhere else, such as an SD card. |
| `--steam-root STEAM_ROOT` | Tells DoomDeck exactly where your Steam folder is. | Use this if Steam is installed in a non-standard place or auto-detection fails. |
| `--steam-user-id STEAM_USER_ID` | Tells DoomDeck which Steam userdata ID to use. | Use this if the wrong Steam profile is detected or you have multiple Steam users. |
| `--dry-run` | Prints planned actions and logs intent without writing files. | Use this before a first run if you want to preview changes. |
| `--verbose` | Shows more detailed debug logging in the terminal. | Use this when troubleshooting. |

Example with a custom root:

```bash
doomdeck install --root /run/media/mmcblk0p1/Games/Doom
```

## `install` Options

Basic install:

```bash
doomdeck install
```

The `install` command creates the folder layout, installs Windows Doom tools, copies Doom files from Steam, writes configs, creates presets, installs mods, and adds one Doom Runner Steam shortcut that runs through Proton.

| Option | What it means | When to use it |
| --- | --- | --- |
| `--skip-downloads` | Does not download Windows tools or managed mod archives. It only reuses files already present. | Use this when offline, or when you already placed files in the managed folder and do not want network access. |
| `--force-download` | Downloads release assets and managed mod archives again, even if files already exist in `downloads/`. | Use this to refresh corrupted downloads or force an update check to replace cached files. |
| `--doomrunner-asset-url URL` | Uses a specific Doom Runner Windows ZIP URL instead of auto-selecting the latest GitHub release asset. | Use this if auto-selection picks the wrong file or you want a specific build. |
| `--uzdoom-asset-url URL` | Uses a specific UZDoom Windows ZIP URL instead of auto-selecting the latest GitHub release asset. | Use this if you need a specific UZDoom build. |
| `--brutal-doom-url URL` | Downloads Brutal Doom from a specific `.pk3` or `.zip` URL. | Use this if ModDB auto-discovery fails or you want a known exact file. |
| `--project-brutality-url URL` | Downloads Project Brutality from a specific `.pk3` or `.zip` URL. | Use this if GitHub auto-selection is not what you want. |
| `--prefer-legacy-appimage` | Deprecated compatibility flag. Windows ZIP assets are now used. | You usually do not need this. |
| `--proton-compat-tool TOOL` | Sets the Steam compatibility tool for the generated Doom Runner shortcut. Default: `proton_10`. | Use this to try another Steam tool such as `proton_experimental` if the default has a compatibility issue. |
| `--brutal-doom-channel latest` | Lets DoomDeck pick the newest Brutal Doom candidate it can find, including beta or test builds. This is the default. | Use this if you want the newest available Brutal Doom build. |
| `--brutal-doom-channel stable` | Prefers non-beta Brutal Doom candidates. | Use this if you prefer a less experimental Brutal Doom version. |
| `--brutal-doom-file PATH` | Installs Brutal Doom from a local `.pk3`, `.wad`, or `.zip` file. | Use this if you downloaded Brutal Doom manually in a browser. |
| `--project-brutality-file PATH` | Installs Project Brutality from a local `.pk3`, `.wad`, or `.zip` file. | Use this if you downloaded Project Brutality manually. |
| `--skip-brutal-doom` | Does not download, update, or install Brutal Doom. If an existing managed Brutal Doom file exists, it can still be used; otherwise the Brutal Doom preset is omitted. | Use this if you only want vanilla UZDoom or Project Brutality. |
| `--skip-project-brutality` | Does not download or install Project Brutality. If an existing managed Project Brutality file exists, it can still be used; otherwise the Project Brutality preset is omitted. | Use this if you only want vanilla UZDoom or Brutal Doom. |
| `--skip-steam-shortcut` | Does not edit Steam's `shortcuts.vdf` or Proton compatibility mapping. | Use this if you do not want DoomDeck to add Doom Runner to Steam. |
| `--skip-doomrunner-live-config` | Does not write Doom Runner's generated `options.json` copies. | Use this if you already customized Doom Runner and do not want DoomDeck to overwrite generated settings. Existing options are backed up when rewritten, but this avoids touching the portable Doom Runner options file and compatibility mirrors. |
| `--shutdown-steam` | Attempts to shut down Steam before editing `shortcuts.vdf` and `localconfig.vdf`. | Use this if Steam is running and you want the script to close it before adding or updating shortcuts. |
| `--allow-steam-running` | Allows Steam config modification even if Steam appears to be running. | Use this only if you understand the risk. Steam can overwrite shortcut or compatibility changes while it is open. |
| `--experimental-doomrunner-config` | Deprecated compatibility flag. Doom Runner generated options are now written by default. | You usually do not need this. It only records that the old flag was requested. |

Examples:

```bash
doomdeck install --brutal-doom-channel stable
```

```bash
doomdeck install --brutal-doom-file ~/Downloads/brutal-doom.pk3
```

```bash
doomdeck install --project-brutality-file ~/Downloads/Project_Brutality.pk3
```

```bash
doomdeck install --skip-steam-shortcut
```

```bash
doomdeck install --shutdown-steam
```

## `install-wads` Options

Install or update ModDB WAD archives without running the full install workflow:

```bash
doomdeck install-wads https://www.moddb.com/games/doom/addons/doom-the-way-id-did-v11
```

| Argument or option | What it means | When to use it |
| --- | --- | --- |
| `moddb_url` | ModDB add-on or file page URL to download and extract `.wad` or `.pk3` map payloads into `pwads/`. Pass multiple URLs to install multiple archives. | Use this when you want to add WADs after the base DoomDeck install. |
| `--force-download` | Downloads WAD archives again, even if files already exist in `downloads/`. | Use this to refresh a cached archive or force an update from ModDB. |

## `self-update` Options

Basic self-update:

```bash
doomdeck self-update
```

`self-update` updates DoomDeck's own source-archive install, normally at `~/.local/share/doomdeck/source`. It downloads the GitHub source archive, extracts it to a temporary directory, creates a fresh isolated Python environment with DoomDeck's runtime dependencies, runs an import smoke test, and then swaps the managed DoomDeck source directory with rollback support.

It does not change the managed Doom folder, Doom Runner, UZDoom, WADs, mods, presets, saves, or Steam shortcuts. After updating DoomDeck itself, run `doomdeck install` when you want the new application code to refresh the game setup.

If you are running from a Git checkout, use `git pull` instead. `self-update` intentionally refuses to replace checkout directories.

| Option | What it means | When to use it |
| --- | --- | --- |
| `--check` | Prints the current DoomDeck version, source path, and update archive without downloading. | Use this to confirm what would be updated. |
| `--dry-run` | Prints the planned self-update actions without downloading or writing files. | Use this before updating if you want to inspect the target paths. |
| `--verbose` | Shows more detailed debug logging in the terminal. | Use this when troubleshooting the update. |
| `--repo-url URL` | Builds the default source archive URL from a different GitHub repository URL. | Use this only when testing a fork. |
| `--ref REF` | Builds the default source archive URL from a different branch name. Default: `master`. | Use this to update from another branch. |
| `--archive-url URL` | Downloads a specific DoomDeck source `.tar.gz` archive. | Use this for a known archive URL or non-branch archive. |
| `--install-dir PATH` | Overrides the DoomDeck source install directory. | Use this only for a custom `install.sh` install location or testing. |

## `validate` Options

Basic validation:

```bash
doomdeck validate
```

`validate` checks for the generated folder layout, Windows Doom Runner and UZDoom executables, IWADs, add-on WADs, mod aliases, preset manifest, Doom Runner options, launchable preset paths, UZDoom configs, shell script syntax, Steam detection, the single generated Doom Runner Steam shortcut, Proton compatibility mapping, and backups.

It prints results as:

- `PASS` - This part looks good.
- `WARN` - This may be okay, but you should read the message.
- `FAIL` - Something required is missing or broken.

Use the common options with `validate` when needed:

```bash
doomdeck validate --verbose
```

```bash
doomdeck validate --root /path/to/Doom
```

## `backup` Options

Basic backup:

```bash
doomdeck backup
```

`backup` creates a compressed `.tar.gz` archive in the managed folder's `backups/` directory. It excludes nested backup archives so backups do not recursively contain older backups.

Use it before manual edits or before trying a different set of mods:

```bash
doomdeck backup
```

Preview without writing:

```bash
doomdeck backup --dry-run
```

## `clean` Options

Basic clean:

```bash
doomdeck clean
```

By default, `clean` does not delete the managed Doom folder. It moves it aside to a timestamped folder such as:

```text
$HOME/Games/Doom.removed-YYYYMMDD-HHMMSS
```

This is useful when you want to start over but still keep the old files nearby.

| Option | What it means | When to use it |
| --- | --- | --- |
| `--yes-delete` | Creates an external backup archive, then permanently deletes the managed root folder. | Use this only when you really want the managed folder removed instead of moved aside. |

Preview clean actions:

```bash
doomdeck clean --dry-run
```

Delete after making an external backup archive:

```bash
doomdeck clean --yes-delete
```

## `restore` Options

Basic restore:

```bash
doomdeck restore /path/to/backup.tar.gz
```

`restore` extracts a backup archive under the managed folder's parent directory. The archive must contain the selected managed root folder name, such as `Doom/`, at its top level. If the managed folder already exists, DoomDeck validates the archive first, then moves the current folder aside using a timestamped name like:

```text
$HOME/Games/Doom.pre-restore-YYYYMMDD-HHMMSS
```

| Argument | What it means | When to use it |
| --- | --- | --- |
| `backup_archive` | Path to a `.tar.gz` backup archive. | Use this to choose which saved backup to restore. |

Preview a restore:

```bash
doomdeck restore /path/to/backup.tar.gz --dry-run
```

## Steam Notes

DoomDeck tries to find Steam automatically in common Steam Deck and Linux locations. It looks for:

- Steam library folders.
- The Steam `DOOM + DOOM II` app install.
- Your Steam userdata folder.
- `shortcuts.vdf`, where non-Steam game shortcuts are stored.
- `localconfig.vdf`, where Steam stores per-shortcut compatibility tool mappings.

If detection fails, pass `--steam-root` or `--steam-user-id`.

If Steam is running, DoomDeck normally refuses to edit Steam shortcut and compatibility files because Steam may overwrite changes. Close Steam first, use `--shutdown-steam`, or use `--skip-steam-shortcut`.

After adding or updating the Steam shortcut, restart Steam before expecting `Doom Runner` to appear in Gaming Mode.

Windows Doom Runner stores its data beside `DoomRunner.exe` when that directory is writable. DoomDeck installs Doom Runner into your user-managed Doom folder, so it writes the primary generated Doom Runner configuration to:

```text
$HOME/Games/Doom/tools/doomrunner/options.json
```

DoomDeck also writes compatibility mirror copies under the managed config folders and the generated Steam shortcut's Proton prefix.

## Mod Notes

### Brutal Doom

By default, DoomDeck checks ModDB and installs Brutal Doom as:

```text
mods/brutal-doom/brutal-doom.pk3
```

Use `--brutal-doom-channel stable` if you prefer non-beta candidates. Use `--brutal-doom-file` if you already downloaded a file yourself.

### Project Brutality

By default, DoomDeck checks GitHub and installs Project Brutality as:

```text
mods/project-brutality/project-brutality.pk3
```

Use `--project-brutality-file` if you already downloaded a file yourself.

### ModDB WAD Archives

Use `doomdeck install-wads` with one or more ModDB add-on or file page URLs to download map archives and extract playable `.wad` or `.pk3` files into:

```text
pwads/
```

`install-wads` is the targeted command for adding WADs after the base setup is complete. DoomDeck does not create a preset for these downloads. Doom Runner already points its map directory at `pwads/`, so the extracted WAD can be selected inside an existing preset.

Rerunning the full installer preserves existing custom PWADs. If a Steam add-on WAD has the same destination name as a file already in `pwads/`, DoomDeck leaves the existing file in place.

### Automatic Content Groups

DoomDeck builds Doom Runner-style group metadata for presets, map packs, and mods. The generated group data is written to:

```text
configs/doomrunner/preset-manifest.json
configs/doomrunner/content-groups.json
```

Full installs also include the same metadata in Doom Runner's generated `options.json` copies. Running `install-wads` refreshes `content-groups.json` and updates the existing preset manifest or generated options file when they are present.

Grouping is automatic. DoomDeck prefers explicit metadata such as managed mod metadata and preset categories, then directory/package names, then conservative filename heuristics. Current groups include Brutal Doom forks, weapon mods, total conversions, Master Levels, map packs, mutators, textures, visors, music, and Other.

Custom WADs can also have friendly display names without changing the actual WAD filename or path. DoomDeck resolves PWAD display names from optional user overrides, manifest metadata, a small curated list of well-known filenames such as `DTWID.wad`, and finally a conservative cleanup of separator-heavy filenames. The original path remains the selectable/launchable value.

To override a WAD label, create `configs/doomrunner/wad-display-names.json`:

```json
{
  "schema": "doom-deck-setup/wad-display-names/v1",
  "display_names": {
    "DTWID.wad": "Doom The Way ID Did",
    "pwads/custom-map.wad": "My Custom Map"
  }
}
```

Keys may be a filename, a path relative to the managed root, a path relative to `pwads/`, or an absolute path. Values are display labels only; DoomDeck does not rename, move, or replace WAD files.

Group headers are metadata only. They are not written as selectable WADs, mods, map packs, or launchable presets, so existing launch paths and preset references remain valid.

## Safety Boundaries

DoomDeck downloads executable tools and mod archives only over HTTPS. For automatically discovered GitHub and ModDB downloads, DoomDeck also restricts the initial download host to the expected upstream service and verifies available size or checksum metadata before installing the payload.

Explicit `--brutal-doom-url`, `--project-brutality-url`, `--doomrunner-asset-url`, and `--uzdoom-asset-url` values are still accepted, but they must use HTTPS. Prefer local file options when you need to install an artifact from another source you already inspected.

Restore archives are intentionally strict. `doomdeck restore` only restores regular files and directories whose archive paths stay under the selected managed root parent and start with the selected managed root folder name. It rejects absolute paths, path traversal, links, special file entries, and archives with an unexpected top-level folder even if an older archive extractor would have accepted them.

## Troubleshooting

Run validation first:

```bash
doomdeck validate
```

Run with more detail:

```bash
doomdeck validate --verbose
```

If downloads fail, rerun later or manually download the mod and pass `--brutal-doom-file` or `--project-brutality-file`.

If Steam shortcut creation fails, close Steam and rerun:

```bash
doomdeck install --shutdown-steam
```

If you do not want DoomDeck touching Steam shortcuts:

```bash
doomdeck install --skip-steam-shortcut
```

If Doom Runner already has settings you want to keep untouched:

```bash
doomdeck install --skip-doomrunner-live-config
```

## Development

DoomDeck uses a `src/` package layout for PyPI-ready packaging:

```text
src/doomdeck/
```

The CLI orchestration lives in `doomdeck.cli`. Core domain data, Steam Deck defaults, WAD naming policy, download policy, managed mod identity, and managed path layout helpers live in `doomdeck.domain`. Application services such as WAD discovery, preset manifest generation, and Doom Runner options generation live in `doomdeck.application`, while Steam, download, and archive file format helpers live in `doomdeck.infrastructure`.

Run the test suite with:

```bash
uv run pytest
```

Common local quality checks are available through `just`:

```bash
just check
just coverage
just analysis
just quality
```

### Versioning and Releases

DoomDeck uses Semantic Versioning for package versions. The current release is `0.2.0`, which means the project is still before a stable `1.0.0` release.

DoomDeck's GitHub release workflow uses Conventional Commits to infer the next version from commit history:

- `fix:` commits should become patch releases, such as `0.1.1`.
- `feat:` commits should become minor releases, such as `0.2.0`.
- `BREAKING CHANGE` footers or `!` markers should become major releases, such as `1.0.0`.

To preview the next calculated version locally without writing files, creating tags, pushing, or publishing anything, run:

```bash
just release-check
```

Python Semantic Release calculates from Git release tags, not from the version currently written in `pyproject.toml`. The latest release tag is `v0.2.0`, so `just release-check` reports `0.2.0` as already released until a later `fix:`, `feat:`, or breaking-change commit requires a new version.

When a release is needed, GitHub Actions runs the test suite, updates `pyproject.toml`, `src/doomdeck/__init__.py`, and `uv.lock`, creates a release commit and tag, builds the source distribution and wheel, and uploads those files to the GitHub Release. It does not publish to PyPI.

## Legal Note

You need to provide your own legally owned Doom game files. DoomDeck only copies files from your Steam installation and installs community tools or mods from their upstream locations.
