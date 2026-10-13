"""Что генератор Geant4 умеет сейчас.

На каждом этапе меняется одна строка таблицы: фигура переходит из ERROR в LEGAL.
"""
from __future__ import annotations

from ...diagnostics import Diagnostic
from ..base import Action, Capability, CheckRow

_NOT_YET = "фигура ещё не реализована в генераторе (%s)"

SHAPES: dict[str, Capability] = {
    "box":      Capability(Action.LEGAL),
    "cylinder": Capability(Action.ERROR, "E301", _NOT_YET % "этап 2"),
    "cone":     Capability(Action.ERROR, "E301", _NOT_YET % "этап 2"),
    "sphere":   Capability(Action.ERROR, "E301", _NOT_YET % "этап 2"),
    "torus":    Capability(Action.ERROR, "E301", _NOT_YET % "этап 2"),
    "boolean":  Capability(Action.ERROR, "E301", _NOT_YET % "этап 3"),
    "mesh":     Capability(Action.ERROR, "E301", _NOT_YET % "этап 4"),
}


def check(scene) -> tuple[list[CheckRow], list[Diagnostic]]:
    """По строке на тело: тип формы, что с ним сделает генератор и почему."""
    rows: list[CheckRow] = []
    diags: list[Diagnostic] = []
    for b in scene.bodies:
        cap = SHAPES.get(b.shape.type, Capability(Action.ERROR, "E301", "неизвестный тип формы"))
        rows.append(CheckRow(b.id, b.shape.type, cap.action, cap.reason))
        if cap.action is Action.ERROR:
            diags.append(Diagnostic("ERROR", cap.code or "E301", "bodies/%s/shape" % b.id,
                                    "%s: %s" % (b.shape.type, cap.reason),
                                    body_id=b.id, target="geant4"))
    return rows, diags
