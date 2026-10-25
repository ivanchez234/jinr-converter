"""Что генератор Geant4 умеет сейчас.

PLANNED — все формы контракта и этап плана, на котором они появятся. Что уже
умеем, берётся из классов фигур (solids.SOLIDS): добавили класс — строка таблицы
сама стала LEGAL. Номера этапов — по плану v3 (docs/output-module-step-plan.md).
"""
from __future__ import annotations

from ..base import Action, Capability
from .solids import SOLIDS

_NOT_YET = "фигура ещё не реализована в генераторе (%s)"

PLANNED: dict[str, Capability] = {
    "box":      Capability(Action.ERROR, "E301", _NOT_YET % "этап 1"),
    "cylinder": Capability(Action.ERROR, "E301", _NOT_YET % "этап 3"),
    "cone":     Capability(Action.ERROR, "E301", _NOT_YET % "этап 3"),
    "sphere":   Capability(Action.ERROR, "E301", _NOT_YET % "этап 3"),
    "torus":    Capability(Action.ERROR, "E301", _NOT_YET % "этап 3"),
    "boolean":  Capability(Action.ERROR, "E301", _NOT_YET % "этап 4"),
    "mesh":     Capability(Action.ERROR, "E301", _NOT_YET % "этап 5"),
}

# порядок строк — как в PLANNED; умеющие фигуры заменяют свою строку
SHAPES: dict[str, Capability] = {**PLANNED, **{t: e.capability for t, e in SOLIDS.items()}}
