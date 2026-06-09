from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_wrapper_help_does_not_require_site_packages() -> None:
    result = subprocess.run(
        [sys.executable, "-S", "doom_deck_setup.py", "--help"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "install" in result.stdout
