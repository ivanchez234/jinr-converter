"""Фигуры в Geant4: по классу на каждый тип формы из scene.json.

Класс фигуры говорит, умеет ли Geant4 её строить (capability), какой у неё допуск
объёма в стенде и какие данные нужны шаблону _solids.j2, чтобы её записать (solid).
Геометрия самой формы (габариты, точки внутри) — у формы в model/scene.py:
она общая для всех целей.

Новая фигура (этап 3) = класс здесь + запись в SOLIDS + макросы в templates/_solids.j2.
Таблица возможностей (capabilities.py) и план (plan.py) подхватят её сами.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from ...geometry import Vec3
from ..base import Action, Capability


@dataclass(frozen=True)
class SolidPlan:
    """Что шаблону нужно, чтобы записать форму (_solids.j2): только числа и имена.

    Пока только коробка. У других фигур на этапе 3 будут свои поля (радиусы,
    полувысота, углы) — каждая фигура будет возвращать свой вид данных.
    """
    kind: str            # вид solid: "box" -> макросы box и box_note в _solids.j2
    name: str            # имя solid в Geant4
    size: Vec3           # полные размеры, мм (для комментария)
    half: Vec3           # половины размеров, мм (их берёт G4Box)


class SolidEmitter(ABC):
    """Одна фигура в Geant4."""

    shape_type: ClassVar[str]                                   # тип формы в JSON: "box"
    capability: ClassVar[Capability] = Capability(Action.LEGAL)
    volume_tol: ClassVar[float] = 1e-6                          # объём примитивов Geant4 считает точно

    @abstractmethod
    def solid(self, shape, name: str) -> SolidPlan:
        """Форма из Scene IR -> данные для шаблона."""


class BoxSolid(SolidEmitter):
    """Коробка -> G4Box (берёт половины размеров)."""
    shape_type = "box"

    def solid(self, shape, name: str) -> SolidPlan:
        return SolidPlan("box", name, tuple(shape.size), tuple(s / 2 for s in shape.size))


# Фигуры, которые Geant4-цель уже умеет: тип формы -> её класс.
SOLIDS: dict[str, SolidEmitter] = {e.shape_type: e for e in (BoxSolid(),)}
