"""Габаритные коробки (AABB) форм и тел.

AABB = ((xmin, ymin, zmin), (xmax, ymax, zmax)), мм.

Коробка, посчитанная по форме, всегда содержит тело целиком, но у повёрнутых
круглых фигур и у пересечения (intersect) она может быть шире настоящей.
Для размера мира этого достаточно: мир получится чуть больше, но не меньше.
"""
from __future__ import annotations

from itertools import product
from typing import Optional

from .rotations import Rigid, Vec3

AABB = tuple[Vec3, Vec3]


def local_bbox(shape) -> Optional[AABB]:
    """Коробка формы в её собственной системе. None — для меша (размер знает только STL)."""
    t = shape.type
    if t == "box":
        hx, hy, hz = (s / 2 for s in shape.size)
        return _sym(hx, hy, hz)
    if t == "cylinder":
        return _sym(shape.radius, shape.radius, shape.height / 2)
    if t == "cone":
        r = max(shape.radius_bottom, shape.radius_top)
        return _sym(r, r, shape.height / 2)
    if t == "sphere":
        return _sym(shape.radius, shape.radius, shape.radius)
    if t == "torus":
        r = shape.major_radius + shape.minor_radius
        return _sym(r, r, shape.minor_radius)
    if t == "boolean":
        left, right = operand_bbox(shape.left), operand_bbox(shape.right)
        if left is None or right is None:
            return None
        if shape.op == "union":
            return hull(left, right)
        if shape.op == "subtract":
            return left                                  # вычитание тело не увеличивает
        return intersection(left, right) or left         # intersect
    if t == "mesh":
        return None
    raise ValueError("неизвестный тип формы: %r" % t)


def operand_bbox(op) -> Optional[AABB]:
    """Коробка операнда булевой операции в системе тела (с учётом его transform)."""
    box = local_bbox(op)
    if box is None or op.transform is None:
        return box
    return transform_aabb(box, Rigid.from_transform(op.transform))


def body_bbox_from_shape(body) -> Optional[AABB]:
    """Коробка тела в системе родителя, посчитанная по форме и transform тела."""
    box = local_bbox(body.shape)
    if box is None:
        return None
    return transform_aabb(box, Rigid.from_transform(body.transform))


def transform_aabb(box: AABB, rigid: Rigid) -> AABB:
    """Коробка после поворота и сдвига: 8 углов -> min/max."""
    pts = [rigid.apply(c) for c in product(*zip(*box))]
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))  # type: ignore[return-value]


def hull(a: AABB, b: AABB) -> AABB:
    return (tuple(min(a[0][i], b[0][i]) for i in range(3)),
            tuple(max(a[1][i], b[1][i]) for i in range(3)))  # type: ignore[return-value]


def intersection(a: AABB, b: AABB) -> Optional[AABB]:
    lo = tuple(max(a[0][i], b[0][i]) for i in range(3))
    hi = tuple(min(a[1][i], b[1][i]) for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return None
    return (lo, hi)  # type: ignore[return-value]


def _sym(hx: float, hy: float, hz: float) -> AABB:
    return ((-hx, -hy, -hz), (hx, hy, hz))
