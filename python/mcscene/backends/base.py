"""Общее для всех целей: что цель делает с каждым телом."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    LEGAL = "LEGAL"              # цель умеет это напрямую
    LOWER = "LOWER"              # точно, но другим способом (например, тор -> плоскости)
    APPROXIMATE = "APPROXIMATE"  # приближённо (например, меш)
    ERROR = "ERROR"              # не умеет

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Capability:
    action: Action
    code: str | None = None      # код диагностики для ERROR / LOWER / APPROXIMATE
    reason: str = ""


@dataclass(frozen=True)
class CheckRow:
    """Одна строка вывода mcscene check."""
    body_id: str
    shape_type: str
    action: Action
    note: str = ""
