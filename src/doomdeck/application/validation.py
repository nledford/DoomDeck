"""Validation result helpers."""
from __future__ import annotations

from typing import Iterable

from doomdeck.domain.models import ValidationItem, ValidationLevel


def add_validation_item(items: list[ValidationItem], level: ValidationLevel | str, message: str) -> None:
    items.append(ValidationItem(ValidationLevel.from_value(level), message))


def validation_has_failures(items: Iterable[ValidationItem]) -> bool:
    return any(item.level == ValidationLevel.FAIL for item in items)


def format_validation_report(items: Iterable[ValidationItem]) -> str:
    lines = ["", "Validation report", "================="]
    lines.extend(f"[{item.level.value}] {item.message}" for item in items)
    lines.append("")
    return "\n".join(lines)
