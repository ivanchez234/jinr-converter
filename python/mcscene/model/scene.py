"""Scene IR: pydantic-модели сцены jinr-mc-scene v0.1.

Нормативна рукописная схема contracts/scene/v0.1/schema/scene.schema.json,
модели подстраиваются под неё. Совпадение проверяют тесты:
tests/contract/test_equivalence.py и tests/unit/test_models.py.

extra="forbid" повторяет additionalProperties: false из схемы.
Все длины в мм, углы в градусах, плотность в g/cm3.

Каждая форма знает свою геометрию — габариты (local_bbox) и точки заведомо внутри
(probe_points). Это общее для всех целей; как записать форму в Geant4 или OpenMC,
решает цель (backends/<цель>/).
"""
from __future__ import annotations

import heapq
from itertools import product
from typing import Annotated, ClassVar, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..geometry import AABB, Rigid


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- общие типы (как $defs в схеме) ---
Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$", max_length=64)]
ExtName = Annotated[str, StringConstraints(pattern=r"^(JINR|X_[A-Z]+)_[A-Za-z0-9_]+$")]
PosFloat = Annotated[float, Field(gt=0)]
NonNegFloat = Annotated[float, Field(ge=0)]
Vec3 = tuple[float, float, float]
PosVec3 = tuple[PosFloat, PosFloat, PosFloat]
Extensions = dict[ExtName, dict]
Version = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+$")]


# --- поворот и размещение ---
class RotIdentity(Strict):
    convention: Literal["identity"]


class RotMatrix(Strict):
    convention: Literal["matrix_active"]
    matrix: tuple[Vec3, Vec3, Vec3]          # по строкам; столбцы = оси тела в системе родителя


class RotEuler(Strict):
    convention: Literal["euler_xyz_extrinsic_deg"]
    angles: Vec3                              # вокруг неподвижных X, Y, Z: R = Rz·Ry·Rx


Rotation = Annotated[Union[RotIdentity, RotMatrix, RotEuler],
                     Field(discriminator="convention")]


class Transform(Strict):
    """Центр тела в системе родителя и активный поворот «тело -> родитель»."""
    translation: Vec3
    rotation: Rotation


# --- формы (все центрированы в своей локальной системе, размеры полные) ---
class ShapeBase(Strict):
    """Общее для всех форм: каждая форма знает свою геометрию, без привязки к цели."""

    def local_bbox(self) -> Optional[AABB]:
        """Габаритная коробка в собственной системе формы. None — неизвестна (меш)."""
        raise NotImplementedError(type(self).__name__)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Точки заведомо внутри формы, в её собственной системе (ими стенд проверяет
        повороты). Пока известны только у коробки, у остальных фигур появятся на этапе 3."""
        return []

    def placed_bbox(self) -> Optional[AABB]:
        """Коробка с учётом собственного transform (он есть у операндов булевых операций)."""
        box = self.local_bbox()
        tf = getattr(self, "transform", None)
        if box is None or tf is None:
            return box
        return box.transformed(Rigid.from_transform(tf))


class Box(ShapeBase):
    type: Literal["box"]
    size: PosVec3                             # полные размеры, не половинки
    transform: Optional[Transform] = None     # только у операнда булевой операции

    PROBE_FRACTION: ClassVar[float] = 0.4     # ±0.4·size — внутри (половина — 0.5)

    def local_bbox(self) -> AABB:
        hx, hy, hz = (s / 2 for s in self.size)
        return AABB.symmetric(hx, hy, hz)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Центр и 8 точек у углов."""
        hx, hy, hz = (self.PROBE_FRACTION * s for s in self.size)
        return [(0.0, 0.0, 0.0)] + [(sx * hx, sy * hy, sz * hz)
                                    for sx, sy, sz in product((-1, 1), repeat=3)]


class Cylinder(ShapeBase):
    type: Literal["cylinder"]                 # вдоль локальной z
    radius: PosFloat
    height: PosFloat                          # полная длина
    inner_radius: NonNegFloat = 0.0
    transform: Optional[Transform] = None

    def local_bbox(self) -> AABB:
        return AABB.symmetric(self.radius, self.radius, self.height / 2)


class Cone(ShapeBase):
    type: Literal["cone"]                     # вдоль локальной z, bottom при z = -height/2
    radius_bottom: NonNegFloat
    radius_top: NonNegFloat
    height: PosFloat
    inner_radius_bottom: NonNegFloat = 0.0
    inner_radius_top: NonNegFloat = 0.0
    transform: Optional[Transform] = None

    def local_bbox(self) -> AABB:
        r = max(self.radius_bottom, self.radius_top)
        return AABB.symmetric(r, r, self.height / 2)


class Sphere(ShapeBase):
    type: Literal["sphere"]
    radius: PosFloat
    inner_radius: NonNegFloat = 0.0
    transform: Optional[Transform] = None

    def local_bbox(self) -> AABB:
        return AABB.symmetric(self.radius, self.radius, self.radius)


class Torus(ShapeBase):
    type: Literal["torus"]                    # ось вращения = локальная z
    major_radius: PosFloat                    # от оси до центра трубки
    minor_radius: PosFloat                    # радиус трубки
    transform: Optional[Transform] = None

    def local_bbox(self) -> AABB:
        r = self.major_radius + self.minor_radius
        return AABB.symmetric(r, r, self.minor_radius)


class Boolean(ShapeBase):
    type: Literal["boolean"]
    op: Literal["union", "subtract", "intersect"]   # subtract = left минус right
    left: Operand
    right: Operand
    transform: Optional[Transform] = None

    def local_bbox(self) -> Optional[AABB]:
        left, right = self.left.placed_bbox(), self.right.placed_bbox()
        if left is None or right is None:
            return None
        if self.op == "union":
            return left.hull(right)
        if self.op == "subtract":
            return left                                     # вычитание тело не увеличивает
        return left.intersection(right) or left             # intersect


class Tessellation(Strict):
    linear_deflection: Optional[PosFloat] = None
    angular_deflection_deg: Optional[PosFloat] = None


class Mesh(ShapeBase):
    type: Literal["mesh"]                     # STL в мм, в локальной системе тела
    uri: Annotated[str, StringConstraints(pattern=r"^[^\\:]+\.stl$")]
    encoding: Literal["stl-binary", "stl-ascii"]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    n_facets: Annotated[int, Field(ge=4)]
    fallback_reason: Literal["SPLINE_SURFACE", "PRIMITIVE_FIT_FAILED",
                             "BOOLEAN_TOO_COMPLEX", "USER_FORCED"]
    tessellation: Optional[Tessellation] = None
    note: Optional[str] = None

    def local_bbox(self) -> None:
        return None                               # размер знает только сам STL


Operand = Annotated[Union[Box, Cylinder, Cone, Sphere, Torus, Boolean],
                    Field(discriminator="type")]
Shape = Annotated[Union[Box, Cylinder, Cone, Sphere, Torus, Boolean, Mesh],
                  Field(discriminator="type")]
Boolean.model_rebuild()


# --- материалы ---
class Component(Strict):
    element: Annotated[str, StringConstraints(pattern=r"^[A-Z][a-z]?$")]
    fraction: Annotated[float, Field(gt=0, le=1)]


class Composition(Strict):
    basis: Literal["mass", "atom"]
    components: Annotated[list[Component], Field(min_length=1)]


class Material(Strict):
    id: Id
    name: Optional[str] = None
    nist: Optional[Annotated[str, StringConstraints(pattern=r"^G4_[A-Za-z0-9_-]+$")]] = None
    density: Optional[PosFloat] = None        # g/cm3
    state: Optional[Literal["solid", "liquid", "gas"]] = None
    composition: Optional[Composition] = None
    provenance: Optional[str] = None
    extensions: Optional[Extensions] = None
    extras: Optional[dict] = None

    @model_validator(mode="after")
    def _nist_or_composition(self) -> "Material":
        # схема: anyOf [nist] | [density, composition]
        if self.nist is None and (self.density is None or self.composition is None):
            raise ValueError("нужно nist или density + composition")
        return self


# --- тела и сцена ---
class Verification(Strict):
    """Посчитано FreeCAD по B-rep; детей не вычитать."""
    cad_volume: PosFloat                      # мм3
    cad_area: Optional[PosFloat] = None       # мм2
    bbox: Optional[tuple[Vec3, Vec3]] = None  # в системе родителя (для корневых — в мировой)


class Body(Strict):
    id: Id
    name: Optional[str] = None
    parent: Optional[Id]                      # обязательно в файле, null = лежит в мире
    material: Id
    transform: Transform
    shape: Shape
    verification: Verification
    extensions: Optional[Extensions] = None
    extras: Optional[dict] = None

    def bbox_from_shape(self) -> Optional[AABB]:
        """Коробка тела в системе родителя, посчитанная по форме и transform тела."""
        box = self.shape.local_bbox()
        return None if box is None else box.transformed(Rigid.from_transform(self.transform))


class World(Strict):
    material: Id
    margin_percent: NonNegFloat = 10.0


class Source(Strict):
    tool: Optional[str] = None
    tool_version: Optional[str] = None
    document: Optional[str] = None
    exported_at: Optional[str] = None


class Units(Strict):
    length: Literal["mm"]
    angle: Literal["deg"]
    density: Literal["g/cm3"]


class Scene(Strict):
    format: Literal["jinr-mc-scene"]
    format_version: Version
    min_reader_version: Optional[Version] = None
    source: Optional[Source] = None
    units: Units
    extensions_used: list[ExtName] = Field(default_factory=list)
    extensions_required: list[ExtName] = Field(default_factory=list)
    world: World
    materials: list[Material]
    bodies: Annotated[list[Body], Field(min_length=1)]
    extensions: Optional[Extensions] = None
    extras: Optional[dict] = None

    def parents_first(self) -> list[Body]:
        """Тела так, чтобы родитель шёл раньше ребёнка, а в остальном — порядок в файле."""
        index = {b.id: i for i, b in enumerate(self.bodies)}
        children: dict[str, list[str]] = {}
        ready: list[int] = []
        for b in self.bodies:
            if b.parent is None:
                heapq.heappush(ready, index[b.id])
            else:
                children.setdefault(b.parent, []).append(b.id)
        order = []
        while ready:
            b = self.bodies[heapq.heappop(ready)]
            order.append(b)
            for c in children.get(b.id, []):
                heapq.heappush(ready, index[c])
        return order

    def world_transforms(self) -> dict[str, Rigid]:
        """id тела -> преобразование «тело -> мир» через всю цепочку родителей."""
        out: dict[str, Rigid] = {}
        for b in self.parents_first():
            local = Rigid.from_transform(b.transform)
            out[b.id] = local if b.parent is None else out[b.parent].then_child(local)
        return out
