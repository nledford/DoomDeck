from __future__ import annotations

import logging
from pathlib import Path

from doomdeck.infrastructure import files as file_helpers


def test_backup_path_uses_unique_destination_for_repeated_labels(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(file_helpers, "now_stamp", lambda: "20260612-120000")
    source = tmp_path / "options.json"
    backups = tmp_path / "backups"
    source.write_text("first\n", encoding="utf-8")

    first = file_helpers.backup_path(source, backups, dry_run=False, logger=logging.getLogger("test"))
    source.write_text("second\n", encoding="utf-8")
    second = file_helpers.backup_path(source, backups, dry_run=False, logger=logging.getLogger("test"))

    assert first is not None
    assert second is not None
    assert first != second
    assert first.read_text(encoding="utf-8") == "first\n"
    assert second.read_text(encoding="utf-8") == "second\n"
    assert second.name == "options.json.20260612-120000.001"
