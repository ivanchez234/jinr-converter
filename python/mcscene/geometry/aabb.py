"""Габаритная коробка (AABB) — объект-значение: от (xmin, ymin, zmin) до (xmax, ymax, zmax), мм.

Коробка, посчитанная по форме, всегда содержит тело целиком, но у повёрнутых
круглых фигур и у пересечения (intersect) она может быть шире настоящей.
Для размера мира этого достаточно: мир получится чуть больше, но не меньше.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Optional, Sequence

from .rotation import Rigid, Vec3


@dataclass(frozen=True)
class AABB:
    lo: Vec3
    hi: Vec3

    @classmethod
    def of(cls, pair: Sequence[Sequence[float]]) -> "AABB":
        """Из пары [[xmin, ymin, zmin], [xmax, ymax, zmax]] — как verification.bbox в JSON."""
        lo, hi = pair
        return cls(tuple(float(x) for x in lo), tuple(float(x) for x in hi))  # type: ignore[arg-type]

    @classmethod
    def symmetric(cls, hx: float, hy: float, hz: float) -> "AABB":
        """Коробка ±hx, ±hy, ±hz вокруг начала координат."""
        return cls((-hx, -hy, -hz), (hx, hy, hz))

    def as_tuple(self) -> tuple[Vec3, Vec3]:
        return (self.lo, self.hi)

    def corners(self) -> list[Vec3]:
        return [tuple(c) for c in product(*zip(self.lo, self.hi))]  # type: ignore[misc]

    def transformed(self, rigid: Rigid) -> "AABB":
        """Коробка после поворота и сдвига: 8 углов -> min/max."""
        pts = [rigid.apply(c) for c in self.corners()]
        return AABB(tuple(min(p[i] for p in pts) for i in range(3)),
                    tuple(max(p[i] for p in pts) for i in range(3)))  # type: ignore[arg-type]

    def hull(self, other: "AABB") -> "AABB":
        """Наименьшая коробка, в которой лежат обе."""
        return AABB(tuple(min(self.lo[i], other.lo[i]) for i in range(3)),
                    tuple(max(self.hi[i], other.hi[i]) for i in range(3)))  # type: ignore[arg-type]

    def intersection(self, other: "AABB") -> Optional["AABB"]:
        """Общая часть двух коробок или None, если они не пересекаются."""
        lo = tuple(max(self.lo[i], other.lo[i]) for i in range(3))
        hi = tuple(min(self.hi[i], other.hi[i]) for i in range(3))
        if any(lo[i] > hi[i] for i in range(3)):
            return None
        return AABB(lo, hi)  # type: ignore[arg-type]
