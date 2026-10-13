"""Как числа и строки выглядят в сгенерированном C++.

Правила (план, пункт 1.5): целое значение -> 25, иначе кратчайшая точная запись
(repr), -0.0 -> 0; единицы всегда явные: *mm, *deg.
"""
from __future__ import annotations

from typing import Sequence


def num(x: float) -> str:
    x = float(x)
    if x == 0:
        return "0"                       # и 0.0, и -0.0
    if x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def mm(x: float) -> str:
    return num(x) + "*mm"


def vec_mm(v: Sequence[float]) -> str:
    return "G4ThreeVector(%s)" % ", ".join(mm(x) for x in v)


def sizes(v: Sequence[float]) -> str:
    """Размеры для комментария: 20 × 40 × 70."""
    return " × ".join(num(x) for x in v)


def cpp_str(s: str) -> str:
    """Строковый литерал C++. id из контракта состоят из [A-Za-z0-9_-], но экранируем на всякий случай."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def comment(s: str) -> str:
    """Текст для однострочного комментария // (имена из FreeCAD могут быть любыми)."""
    return " ".join(str(s).split())
