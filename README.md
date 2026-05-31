# DoomDeck

Steam Deck Doom modding setup automation for Doom Runner, UZDoom, Brutal Doom, and Project Brutality.

## What This Script Does

`doom_deck_setup.py` is a helper script for setting up Doom modding on a Steam Deck without manually wiring together engines, game files, launchers, and Steam shortcuts.

In plain terms, it:

- Creates a managed Doom folder, by default at `/home/deck/Games/Doom`.
- Downloads and installs the Doom Runner AppImage.
- Downloads and installs the UZDoom AppImage.
- Finds your Steam-installed `DOOM + DOOM II` files and copies the usable Doom game data files into the managed folder.
- Looks for add-on WAD files from the Steam install and copies those too.
- Downloads or installs Brutal Doom.
- Downloads or installs Project Brutality.
- Creates ready-to-use Doom Runner presets.
- Creates direct launcher scripts for vanilla-style Doom, UZDoom, Brutal Doom, and Project Brutality.
- Writes Steam Deck-friendly UZDoom controller, display, and graphics settings.
- Adds Doom Runner as a non-Steam game shortcut, unless you tell it not to.
- Backs up files before replacing important generated files or modifying Steam shortcuts.

The script is designed to be rerun. If you already ran it once, running it again updates the setup and reuses files that are already current.

## What It Does Not Do

This repo does not include Doom game files. You need to own and install `DOOM + DOOM II` through Steam first. The script copies your existing Steam game data into the managed folder so Doom Runner and UZDoom can use it.

The script also does not require root access. It works in your user folders.

## Requirements

- Steam Deck or Linux.
- Python 3.10 or newer.
- Steam `DOOM + DOOM II` installed.
- Internet access if you want the script to download Doom Runner, UZDoom, Brutal Doom, or Project Brutality.

## Quick Start

From the repo folder:

```bash
python3 doom_deck_setup.py install
```

After it finishes, restart Steam. Doom Runner should appear as a non-Steam game. Launch Doom Runner and pick one of the generated presets.

To check the setup later:

```bash
python3 doom_deck_setup.py validate
```

To see what an install would do without changing files:

```bash
python3 doom_deck_setup.py install --dry-run
```

## Managed Folder Layout

By default, the script manages this folder:

```text
/home/deck/Games/Doom/
```

Important subfolders include:

- `tools/doomrunner/` - Doom Runner AppImage.
- `source-ports/uzdoom/` - UZDoom AppImage and wrapper script.
- `iwads/` - Main Doom game data files copied from Steam.
- `pwads/` - Add-on WAD files copied from Steam.
- `mods/brutal-doom/` - Brutal Doom files and metadata.
- `mods/project-brutality/` - Project Brutality files and metadata.
- `configs/doomrunner/` - Generated Doom Runner manifest and policy files.
- `configs/uzdoom/` - Generated UZDoom configs.
- `launchers/` - Direct shell launchers for presets.
- `saves/` - Save-game folders used by presets.
- `screenshots/` - Screenshot folders used by presets.
- `downloads/` - Downloaded upstream files.
- `backups/` - Backups made before replacements.
- `logs/` - Script log files.
- `docs/` - Extra generated setup notes.

## Commands

The script uses subcommands:

```bash
python3 doom_deck_setup.py <command> [options]
```

Available commands:

| Command | What it does | When to use it |
| --- | --- | --- |
| `install` | Creates or updates the full DoomDeck setup. | Use this first. Rerun it when you want to update downloaded tools, mods, configs, or launchers. |
| `validate` | Checks whether the setup looks complete and prints a pass/warn/fail report. | Use this after install, after moving files, or when something does not launch correctly. |
| `backup` | Creates a `.tar.gz` backup of the managed Doom folder. | Use this before large manual changes or before experimenting. |
| `clean` | Moves or deletes the managed Doom folder safely. | Use this when you want to remove the generated setup and start over. |
| `restore` | Restores a backup archive. | Use this to roll back to a previous backed-up managed folder. |

## Common Options

These options work with every command:

| Option | What it means | When to use it |
| --- | --- | --- |
| `-h`, `--help` | Shows help for the selected command. | Use this when you want a quick reminder in the terminal. |
| `--root ROOT` | Changes the managed Doom folder. Default: `/home/deck/Games/Doom`. | Use this if you want everything stored somewhere else, such as an SD card. |
| `--steam-root STEAM_ROOT` | Tells the script exactly where your Steam folder is. | Use this if Steam is installed in a non-standard place or auto-detection fails. |
| `--steam-user-id STEAM_USER_ID` | Tells the script which Steam userdata ID to use. | Use this if the wrong Steam profile is detected or you have multiple Steam users. |
| `--dry-run` | Prints planned actions and logs intent without writing files. | Use this before a first run if you want to preview changes. |
| `--verbose` | Shows more detailed debug logging in the terminal. | Use this when troubleshooting. |

Example with a custom root:

```bash
python3 doom_deck_setup.py install --root /run/media/mmcblk0p1/Games/Doom
```

## `install` Options

Basic install:

```bash
python3 doom_deck_setup.py install
```

The `install` command creates the folder layout, installs tools, copies Doom files from Steam, writes configs, creates presets, installs mods, and adds the Steam shortcut.

| Option | What it means | When to use it |
| --- | --- | --- |
| `--skip-downloads` | Does not download AppImages or managed mod archives. It only reuses files already present. | Use this when offline, or when you already placed files in the managed folder and do not want network access. |
| `--force-download` | Downloads release assets and managed mod archives again, even if files already exist in `downloads/`. | Use this to refresh corrupted downloads or force an update check to replace cached files. |
| `--doomrunner-asset-url URL` | Uses a specific Doom Runner AppImage URL instead of auto-selecting the latest GitHub release asset. | Use this if auto-selection picks the wrong file or you want a specific build. |
| `--uzdoom-asset-url URL` | Uses a specific UZDoom AppImage URL instead of auto-selecting the latest GitHub release asset. | Use this if you need a specific UZDoom build. |
| `--brutal-doom-url URL` | Downloads Brutal Doom from a specific `.pk3` or `.zip` URL. | Use this if ModDB auto-discovery fails or you want a known exact file. |
| `--project-brutality-url URL` | Downloads Project Brutality from a specific `.pk3` or `.zip` URL. | Use this if GitHub auto-selection is not what you want. |
| `--prefer-legacy-appimage` | Prefers AppImage assets with `legacy` in the name when the script chooses from GitHub releases. | Use this if the normal AppImage does not run on your Steam Deck or Linux install. |
| `--brutal-doom-channel latest` | Lets the script pick the newest Brutal Doom candidate it can find, including beta or test builds. This is the default. | Use this if you want the newest available Brutal Doom build. |
| `--brutal-doom-channel stable` | Prefers non-beta Brutal Doom candidates. | Use this if you prefer a less experimental Brutal Doom version. |
| `--brutal-doom-file PATH` | Installs Brutal Doom from a local `.pk3`, `.wad`, or `.zip` file. | Use this if you downloaded Brutal Doom manually in a browser. |
| `--project-brutality-file PATH` | Installs Project Brutality from a local `.pk3`, `.wad`, or `.zip` file. | Use this if you downloaded Project Brutality manually. |
| `--skip-brutal-doom` | Does not download, update, or install Brutal Doom. If an existing managed Brutal Doom file exists, it can still be used. | Use this if you only want vanilla UZDoom or Project Brutality. |
| `--skip-project-brutality` | Does not download or install Project Brutality. If an existing managed Project Brutality file exists, it can still be used. | Use this if you only want vanilla UZDoom or Brutal Doom. |
| `--skip-steam-shortcut` | Does not edit Steam's `shortcuts.vdf`. | Use this if you do not want the script to add Doom Runner to Steam, or if you want to add launchers manually. |
| `--skip-doomrunner-live-config` | Does not write Doom Runner's live `options.json`. | Use this if you already customized Doom Runner and do not want the script to overwrite its active settings. Existing options are backed up when rewritten, but this avoids touching them at all. |
| `--shutdown-steam` | Attempts to shut down Steam before editing `shortcuts.vdf`. | Use this if Steam is running and you want the script to close it before adding or updating the shortcut. |
| `--allow-steam-running` | Allows `shortcuts.vdf` modification even if Steam appears to be running. | Use this only if you understand the risk. Steam can overwrite shortcut changes while it is open. |
| `--experimental-doomrunner-config` | Deprecated compatibility flag. Doom Runner live config is now written by default. | You usually do not need this. It only records that the old flag was requested. |

Examples:

```bash
python3 doom_deck_setup.py install --brutal-doom-channel stable
```

```bash
python3 doom_deck_setup.py install --brutal-doom-file ~/Downloads/brutal-doom.pk3
```

```bash
python3 doom_deck_setup.py install --project-brutality-file ~/Downloads/Project_Brutality.pk3
```

```bash
python3 doom_deck_setup.py install --skip-steam-shortcut
```

```bash
python3 doom_deck_setup.py install --shutdown-steam
```

## `validate` Options

Basic validation:

```bash
python3 doom_deck_setup.py validate
```

`validate` checks for the generated folder layout, AppImages, wrappers, IWADs, add-on WADs, mod aliases, preset manifest, Doom Runner options, UZDoom configs, shell script syntax, Steam detection, the Doom Runner Steam shortcut, and backups.

It prints results as:

- `PASS` - This part looks good.
- `WARN` - This may be okay, but you should read the message.
- `FAIL` - Something required is missing or broken.

Use the common options with `validate` when needed:

```bash
python3 doom_deck_setup.py validate --verbose
```

```bash
python3 doom_deck_setup.py validate --root /path/to/Doom
```

## `backup` Options

Basic backup:

```bash
python3 doom_deck_setup.py backup
```

`backup` creates a compressed `.tar.gz` archive in the managed folder's `backups/` directory. It excludes nested backup archives so backups do not recursively contain older backups.

Use it before manual edits or before trying a different set of mods:

```bash
python3 doom_deck_setup.py backup
```

Preview without writing:

```bash
python3 doom_deck_setup.py backup --dry-run
```

## `clean` Options

Basic clean:

```bash
python3 doom_deck_setup.py clean
```

By default, `clean` does not delete the managed Doom folder. It moves it aside to a timestamped folder such as:

```text
/home/deck/Games/Doom.removed-YYYYMMDD-HHMMSS
```

This is useful when you want to start over but still keep the old files nearby.

| Option | What it means | When to use it |
| --- | --- | --- |
| `--yes-delete` | Creates an external backup archive, then permanently deletes the managed root folder. | Use this only when you really want the managed folder removed instead of moved aside. |

Preview clean actions:

```bash
python3 doom_deck_setup.py clean --dry-run
```

Delete after making an external backup archive:

```bash
python3 doom_deck_setup.py clean --yes-delete
```

## `restore` Options

Basic restore:

```bash
python3 doom_deck_setup.py restore /path/to/backup.tar.gz
```

`restore` extracts a backup archive under the managed folder's parent directory. If the managed folder already exists, it moves the current folder aside first using a timestamped name like:

```text
/home/deck/Games/Doom.pre-restore-YYYYMMDD-HHMMSS
```

| Argument | What it means | When to use it |
| --- | --- | --- |
| `backup_archive` | Path to a `.tar.gz` backup archive. | Use this to choose which saved backup to restore. |

Preview a restore:

```bash
python3 doom_deck_setup.py restore /path/to/backup.tar.gz --dry-run
```

## Steam Notes

The script tries to find Steam automatically in common Steam Deck and Linux locations. It looks for:

- Steam library folders.
- The Steam `DOOM + DOOM II` app install.
- Your Steam userdata folder.
- `shortcuts.vdf`, where non-Steam game shortcuts are stored.

If detection fails, pass `--steam-root` or `--steam-user-id`.

If Steam is running, the script normally refuses to edit `shortcuts.vdf` because Steam may overwrite changes. Close Steam first, use `--shutdown-steam`, or use `--skip-steam-shortcut`.

After adding or updating the Steam shortcut, restart Steam before expecting Doom Runner to appear in Gaming Mode.

## Mod Notes

### Brutal Doom

By default, the script checks ModDB and installs Brutal Doom as:

```text
mods/brutal-doom/brutal-doom.pk3
```

Use `--brutal-doom-channel stable` if you prefer non-beta candidates. Use `--brutal-doom-file` if you already downloaded a file yourself.

### Project Brutality

By default, the script checks GitHub and installs Project Brutality as:

```text
mods/project-brutality/project-brutality.pk3
```

Use `--project-brutality-file` if you already downloaded a file yourself.

## Troubleshooting

Run validation first:

```bash
python3 doom_deck_setup.py validate
```

Run with more detail:

```bash
python3 doom_deck_setup.py validate --verbose
```

If downloads fail, rerun later or manually download the mod and pass `--brutal-doom-file` or `--project-brutality-file`.

If Steam shortcut creation fails, close Steam and rerun:

```bash
python3 doom_deck_setup.py install --shutdown-steam
```

If you do not want the script touching Steam shortcuts:

```bash
python3 doom_deck_setup.py install --skip-steam-shortcut
```

If Doom Runner already has settings you want to keep untouched:

```bash
python3 doom_deck_setup.py install --skip-doomrunner-live-config
```

## Legal Note

You need to provide your own legally owned Doom game files. This script only copies files from your Steam installation and installs community tools or mods from their upstream locations.
