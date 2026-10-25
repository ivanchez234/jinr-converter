"""Имена объёмов Geant4 и C++ функций — правила цели geant4.

У каждой цели свои правила имён: у Geant4 подходит id как есть, у FLUKA имена
не длиннее 8 символов, у MCNP вместо имён номера. Поэтому это проход цели, а не общий.

id из JSON (^[A-Za-z_][A-Za-z0-9_-]*$) годится как имя объёма Geant4 как есть.
Для имени C++ функции BuildBody_<id> дефис заменяется на подчёркивание.

  - Если два id после замены совпали, второе имя получает суффикс _2 (_3, ...) -> I401.
  - "world" занято под мир: тело с id "world" получает объём "world_body" -> I401.

Кто первый в массиве bodies, тот сохраняет простое имя: результат детерминирован.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...diagnostics import Diagnostics
from ...passes import Pass

WORLD = "world"
RESERVED = frozenset({WORLD})


@dataclass(frozen=True)
class BodyNames:
    id: str          # id из JSON
    volume: str      # имя solid / логического / физического объёма в Geant4
    func: str        # имя C++ функции, которая строит тело


class Geant4Naming(Pass):
    """Сцена -> {id тела: BodyNames}."""

    def run(self, scene, diags: Diagnostics) -> dict[str, BodyNames]:
        ids = [b.id for b in scene.bodies]

        taken = set(RESERVED) | {i for i in ids if i not in RESERVED}
        volumes: dict[str, str] = {}
        for i in ids:
            if i in RESERVED:
                v = _unique(i + "_body", taken)
                taken.add(v)
                diags.info("I401", "bodies/%s" % i,
                           "имя %r занято под мир, объём тела назван %r" % (i, v), body_id=i)
            else:
                v = i
            volumes[i] = v

        used: set[str] = set()
        names: dict[str, BodyNames] = {}
        for i in ids:
            base = "BuildBody_" + volumes[i].replace("-", "_")
            f = _unique(base, used)
            used.add(f)
            if f != base:
                diags.info("I401", "bodies/%s" % i,
                           "имя функции %s уже занято другим телом, взято %s" % (base, f), body_id=i)
            names[i] = BodyNames(i, volumes[i], f)
        return names


def _unique(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while "%s_%d" % (base, n) in taken:
        n += 1
    return "%s_%d" % (base, n)
