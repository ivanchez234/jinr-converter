"""Материалы: какие нужны и можно ли их построить.

В код попадают только материалы, на которые кто-то ссылается (мир или тело),
в порядке массива materials.

  - есть nist                 -> берём материал из базы NIST Geant4;
  - есть и nist, и composition -> всё равно nist, пометка I410;
  - нет nist (только состав)  -> до этапа 4 это E310 (allow_custom=False);
  - материал никем не используется -> I402, в код не попадает.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..diagnostics import Diagnostics
from .base import Pass


@dataclass(frozen=True)
class MaterialPlan:
    id: str
    name: Optional[str]
    nist: Optional[str]            # G4_Fe ... ; None — свой состав
    density: Optional[float]       # g/cm3, для своего состава
    state: Optional[str]
    composition: object            # model.Composition или None
    used_by: tuple[str, ...]       # "world" и/или id тел


class MaterialPass(Pass):
    """Сцена -> список нужных материалов. allow_custom — умеет ли цель свои составы."""

    def __init__(self, allow_custom: bool = False) -> None:
        self.allow_custom = allow_custom

    def run(self, scene, diags: Diagnostics) -> list[MaterialPlan]:
        users: dict[str, list[str]] = {}
        users.setdefault(scene.world.material, []).append("world")
        for b in scene.bodies:
            users.setdefault(b.material, []).append(b.id)

        plans: list[MaterialPlan] = []
        for m in scene.materials:
            where = "materials/%s" % m.id
            if m.id not in users:
                diags.info("I402", where, "материал никем не используется, в код не попадёт")
                continue
            if m.nist and m.composition is not None:
                diags.info("I410", where, "заданы и nist, и composition: для Geant4 берётся %s" % m.nist)
            if not m.nist and not self.allow_custom:
                diags.error("E310", where, "материал задан своим составом без nist: "
                                           "свои составы появятся на этапе 4")
            plans.append(MaterialPlan(m.id, m.name, m.nist, m.density, m.state, m.composition,
                                      tuple(users[m.id])))
        return plans
