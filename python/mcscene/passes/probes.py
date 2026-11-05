"""Пробные точки каждого тела — в его собственной системе. Общее для всех целей.

Пробная точка — место, где заведомо лежит это тело: стенд спрашивает у Geant4, какое
тело в этой точке, и сверяет ответ. Так ловятся перепутанные повороты и сдвиги.

Тело без детей: точки его формы (Shape.probe_points).

Тело с детьми: внутри лежат дети, и точка формы может попасть в ребёнка (у трубы
с вакуумом все точки сплошного цилиндра — в вакууме). Поэтому у такого тела:
  1. точки формы, которые не попали ни в одного ребёнка;
  2. по точке на каждом из шести лучей от центра тела (±x, ±y, ±z): на луче ищется
     самый длинный отрезок, где есть тело и нет детей, и берётся его середина.
     Так у трубы с вакуумом точки попадают в середину стенки и в середины торцов.
Каждая точка отстоит от поверхности тела и от поверхностей детей хотя бы на MARGIN.
Внуки лежат внутри детей (это проверяет validate.py), поэтому смотреть надо только детей.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics import Diagnostics
from ..geometry import AABB, Rigid, Vec3
from .base import Pass


@dataclass(frozen=True)
class Child:
    """Ребёнок глазами родителя: как перейти в его систему и где его габарит."""
    to_child: Rigid      # система родителя -> система ребёнка
    shape: object        # форма ребёнка (Scene IR)
    box: AABB            # габарит ребёнка в системе родителя


class ProbePass(Pass):
    """Сцена -> {id тела: пробные точки в системе тела}."""

    STEPS = 2000         # шагов на луче при поиске свободного отрезка
    MARGIN = 0.01        # мм: точка не ближе этого к любой поверхности
    BISECT = 60          # уточнений границы отрезка (делением пополам)

    def run(self, scene, diags: Diagnostics) -> dict[str, tuple[Vec3, ...]]:
        kids: dict[str, list] = {}
        for b in scene.bodies:
            if b.parent is not None:
                kids.setdefault(b.parent, []).append(b)
        out: dict[str, tuple[Vec3, ...]] = {}
        for b in scene.bodies:
            if b.id not in kids:
                out[b.id] = tuple(b.shape.probe_points())
                continue
            try:
                out[b.id] = self.parent_points(b.shape, kids[b.id])
            except NotImplementedError:                     # булевы и меши — этапы 4 и 5
                out[b.id] = ()
            if not out[b.id]:
                diags.warn("W340", "bodies/%s" % b.id,
                           "в теле с детьми не нашлось места без детей для пробных точек: "
                           "стенд проверит у него только объём", body_id=b.id)
        return out

    def parent_points(self, shape, kids) -> tuple[Vec3, ...]:
        children = []
        for k in kids:
            place = Rigid.from_transform(k.transform)
            children.append(Child(place.inverse(), k.shape, k.shape.local_bbox().transformed(place)))
        pts = [tuple(p) for p in shape.probe_points() if self.free(shape, children, p, self.MARGIN)]
        box = shape.local_bbox()
        for axis in range(3):
            for sign in (1.0, -1.0):
                q = self.ray_point(shape, children, box, axis, sign)
                if q is not None and all(max(abs(q[i] - p[i]) for i in range(3)) > 1e-9 for p in pts):
                    pts.append(q)
        return tuple(pts)

    @staticmethod
    def free(shape, children, p, margin: float) -> bool:
        """Точка в теле и ни в одном ребёнке — с запасом margin от всех поверхностей."""
        return shape.contains(p, margin) and not any(c.shape.contains(c.to_child.apply(p), -margin)
                                                     for c in children)

    def ray_point(self, shape, children, box: AABB, axis: int, sign: float) -> Vec3 | None:
        """Середина самого длинного свободного отрезка на луче от центра вдоль ±оси."""
        length = box.hi[axis] if sign > 0 else -box.lo[axis]
        if length <= 0:
            return None
        lo = [0.0, 0.0, 0.0]
        hi = [0.0, 0.0, 0.0]
        lo[axis], hi[axis] = sorted((0.0, sign * length))
        seg = AABB(tuple(x - self.MARGIN for x in lo), tuple(x + self.MARGIN for x in hi))  # type: ignore[arg-type]
        near = [c for c in children if c.box.intersection(seg) is not None]   # остальные луч не задевает

        def point(t: float) -> Vec3:
            p = [0.0, 0.0, 0.0]
            p[axis] = sign * t
            return (p[0], p[1], p[2])

        def ok(t: float) -> bool:
            return self.free(shape, near, point(t), 0.0)

        step = length / self.STEPS
        ts = [(k + 0.5) * step for k in range(self.STEPS)]
        flags = [ok(t) for t in ts]
        best: tuple[float, float] | None = None
        k = 0
        while k < self.STEPS:
            if not flags[k]:
                k += 1
                continue
            a = k
            while k + 1 < self.STEPS and flags[k + 1]:
                k += 1
            start = self.edge(ok, ts[a - 1] if a > 0 else 0.0, ts[a])
            end = self.edge(ok, ts[k + 1] if k + 1 < self.STEPS else length, ts[k])
            if best is None or end - start >= best[1] - best[0]:   # при равенстве — дальний от центра
                best = (start, end)
            k += 1
        if best is None:
            return None
        q = point((best[0] + best[1]) / 2)
        return q if self.free(shape, near, q, self.MARGIN) else None

    def edge(self, ok, outside: float, inside: float) -> float:
        """Граница свободного отрезка между точкой снаружи и точкой внутри (делением пополам).
        Если «снаружи» на самом деле тоже свободно (центр тела или конец луча), граница — она."""
        if ok(outside):
            return outside
        for _ in range(self.BISECT):
            mid = (outside + inside) / 2
            if ok(mid):
                inside = mid
            else:
                outside = mid
        return inside
