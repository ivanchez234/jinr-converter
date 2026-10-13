"""Размер мира.

Мир — коробка с центром в начале координат (так его строит Geant4). Полуразмер
по каждой оси = наибольшее |координата| среди всех корневых тел (parent = null),
увеличенное на margin_percent.

Где лежит тело, берётся из verification.bbox (его посчитал FreeCAD), а если его
нет — считается по форме. Дети лежат внутри родителей и на мир не влияют.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics import Diagnostic
from .bbox import AABB, body_bbox_from_shape, hull
from .rotations import Vec3


@dataclass(frozen=True)
class WorldPlan:
    material: str            # id материала мира
    half_size: Vec3          # мм, полуразмеры коробки мира (как у G4Box)
    extent: AABB             # где лежат корневые тела, мм (для комментария в коде)
    margin_percent: float


def plan_world(scene) -> tuple[WorldPlan | None, list[Diagnostic]]:
    diags: list[Diagnostic] = []
    extent: AABB | None = None

    for body in scene.bodies:
        if body.parent is not None:
            continue
        box = body.verification.bbox or body_bbox_from_shape(body)
        if box is None:
            diags.append(Diagnostic(
                "ERROR", "E330", "bodies/%s/verification/bbox" % body.id,
                "у тела-меша нет verification.bbox, а размер STL без чтения файла неизвестен: "
                "не могу оценить размер мира (добавьте bbox при экспорте)", body_id=body.id))
            continue
        extent = box if extent is None else hull(extent, box)

    if extent is None:
        return None, diags

    m = scene.world.margin_percent
    half = tuple(_clean(max(abs(extent[0][i]), abs(extent[1][i])) * (100 + m) / 100)
                 for i in range(3))
    return WorldPlan(scene.world.material, half, extent, m), diags  # type: ignore[arg-type]


def _clean(x: float) -> float:
    """Убирает шум последних разрядов: 27.500000000000004 -> 27.5 (точность 1e-9 мм)."""
    return round(x, 9) + 0.0
