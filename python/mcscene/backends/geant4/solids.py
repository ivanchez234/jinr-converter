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
from typing import ClassVar, Union

from ...geometry import Vec3
from ..base import Action, Capability


@dataclass(frozen=True)
class SolidPlan:
    """Коробка для G4Box. Что шаблону нужно, чтобы записать форму (_solids.j2): только числа и имена.

    У каждой фигуры свой вид данных (SolidPlan, TubsPlan…), общее у всех — kind и name:
    по kind шаблон выбирает макросы <kind> и <kind>_note.
    """
    kind: str            # вид solid: "box" -> макросы box и box_note в _solids.j2
    name: str            # имя solid в Geant4
    size: Vec3           # полные размеры, мм (для комментария)
    half: Vec3           # половины размеров, мм (их берёт G4Box)


@dataclass(frozen=True)
class TubsPlan:
    """Цилиндр или труба для G4Tubs: радиусы — как есть, высота — половина."""
    kind: str            # "tubs" -> макросы tubs и tubs_note
    name: str
    rmin: float          # внутренний радиус, мм (0 — сплошной цилиндр)
    rmax: float          # внешний радиус, мм
    height: float        # полная высота, мм (для комментария)
    half_z: float        # половина высоты, мм (её берёт G4Tubs)


@dataclass(frozen=True)
class OrbPlan:
    """Сплошной шар для G4Orb: только радиус."""
    kind: str            # "orb" -> макросы orb и orb_note
    name: str
    radius: float        # мм


@dataclass(frozen=True)
class SpherePlan:
    """Полый шар для G4Sphere: внутренний и внешний радиус, полный круг по обоим углам."""
    kind: str            # "sphere" -> макросы sphere и sphere_note
    name: str
    rmin: float          # мм
    rmax: float          # мм


@dataclass(frozen=True)
class ConsPlan:
    """Конус для G4Cons. Низ — край при z = -H/2 (в G4Cons он первый: rmin1, rmax1), верх — при +H/2."""
    kind: str            # "cons" -> макросы cons и cons_note
    name: str
    rmin_bottom: float   # мм
    rmax_bottom: float
    rmin_top: float
    rmax_top: float
    height: float        # мм, для подписи
    half_z: float        # G4Cons берёт половину высоты


@dataclass(frozen=True)
class TorusPlan:
    """Тор для G4Torus: радиусы трубки (внутренний всегда 0 — в контракте его нет) и радиус от оси до центра трубки."""
    kind: str            # "torus" -> макросы torus и torus_note
    name: str
    rmin: float          # мм, внутренний радиус трубки
    rmax: float          # мм, радиус трубки (minor_radius)
    rtor: float          # мм, от оси до центра трубки (major_radius)


SolidData = Union[SolidPlan, TubsPlan, OrbPlan, SpherePlan, ConsPlan, TorusPlan]


class SolidEmitter(ABC):
    """Одна фигура в Geant4."""

    shape_type: ClassVar[str]                                   # тип формы в JSON: "box"
    capability: ClassVar[Capability] = Capability(Action.LEGAL)
    volume_tol: ClassVar[float] = 1e-6                          # объём примитивов Geant4 считает точно

    @abstractmethod
    def solid(self, shape, name: str) -> SolidData:
        """Форма из Scene IR -> данные для шаблона."""


class BoxSolid(SolidEmitter):
    """Коробка -> G4Box (берёт половины размеров)."""
    shape_type = "box"

    def solid(self, shape, name: str) -> SolidPlan:
        return SolidPlan("box", name, tuple(shape.size), tuple(s / 2 for s in shape.size))


class TubeSolid(SolidEmitter):
    """Цилиндр (и труба с inner_radius) -> G4Tubs: радиусы как есть, половина высоты."""
    shape_type = "cylinder"

    def solid(self, shape, name: str) -> TubsPlan:
        return TubsPlan("tubs", name, shape.inner_radius, shape.radius, shape.height, shape.height / 2)


class SphereSolid(SolidEmitter):
    """Шар -> G4Orb (сплошной) или G4Sphere (полый, с inner_radius)."""
    shape_type = "sphere"

    def solid(self, shape, name: str) -> OrbPlan | SpherePlan:
        if shape.inner_radius == 0:
            return OrbPlan("orb", name, shape.radius)
        return SpherePlan("sphere", name, shape.inner_radius, shape.radius)


class ConeSolid(SolidEmitter):
    """Конус (в том числе острый и полый) -> G4Cons: радиусы как есть, половина высоты."""
    shape_type = "cone"

    def solid(self, shape, name: str) -> ConsPlan:
        return ConsPlan("cons", name, shape.inner_radius_bottom, shape.radius_bottom,
                        shape.inner_radius_top, shape.radius_top, shape.height, shape.height / 2)


class TorusSolid(SolidEmitter):
    """Тор -> G4Torus: сплошная трубка (rmin = 0), полный круг."""
    shape_type = "torus"

    def solid(self, shape, name: str) -> TorusPlan:
        return TorusPlan("torus", name, 0.0, shape.minor_radius, shape.major_radius)


# Фигуры, которые Geant4-цель уже умеет: тип формы -> её класс.
SOLIDS: dict[str, SolidEmitter] = {e.shape_type: e for e in
                                   (BoxSolid(), TubeSolid(), ConeSolid(), SphereSolid(), TorusSolid())}
