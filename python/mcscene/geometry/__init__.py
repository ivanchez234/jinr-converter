"""Геометрия — объекты-значения, общие для всех целей.

  Rotation — поворот (матрица 3×3);
  Rigid    — жёсткое преобразование p -> R·p + t;
  AABB     — габаритная коробка.

Сами фигуры (Box, Cylinder, ...) знают свою геометрию: model.Box.local_bbox(),
model.Box.probe_points() — см. model/scene.py.
"""
from .aabb import AABB
from .rotation import IDENTITY, ZERO, Mat3, Rigid, Rotation, Vec3

__all__ = ["AABB", "IDENTITY", "ZERO", "Mat3", "Rigid", "Rotation", "Vec3"]
