#!/usr/bin/env python3
"""Compatibility wrapper for the packaged DoomDeck CLI."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))


def _help_requested(argv: list[str]) -> bool:
    return any(arg in {"-h", "--help"} for arg in argv)


def _print_dependency_free_help() -> None:
    print(
        """usage: doom_deck_setup.py [-h] {install,install-wads,validate,backup,clean,restore,self-update} ...

Compatibility wrapper for the packaged DoomDeck CLI.

positional arguments:
  {install,install-wads,validate,backup,clean,restore,self-update}
    install             Install/update the managed Doom setup
    install-wads        Install/update ModDB WAD archives only
    validate            Validate the setup
    backup              Create a tar.gz backup of the managed Doom root
    clean               Safely clean the managed Doom root
    restore             Restore a backup archive
    self-update         Update the DoomDeck command installed by install.sh

options:
  -h, --help            show this help message and exit
"""
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        packaged_main = importlib.import_module("doomdeck.cli").main
    except ModuleNotFoundError:
        if _help_requested(args):
            _print_dependency_free_help()
            return 0
        raise
    return int(packaged_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
