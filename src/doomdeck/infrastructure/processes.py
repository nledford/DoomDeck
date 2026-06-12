"""Process inspection helpers."""
from __future__ import annotations

import os
import subprocess


def is_process_running(patterns: list[str]) -> bool:
    try:
        result = subprocess.run(["pgrep", "-fa", "."], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    this_pid = os.getpid()
    for line in result.stdout.splitlines():
        if str(this_pid) in line:
            continue
        lowered = line.lower()
        if any(pattern.lower() in lowered for pattern in patterns):
            return True
    return False
