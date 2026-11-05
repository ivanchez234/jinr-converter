"""Scene IR: модель сцены jinr-mc-scene v0.1 — неизменяемые записи (dataclass) на record.py.

Нормативна рукописная схема contracts/scene/v0.1/schema/scene.schema.json,
модель подстраивается под неё. Совпадение проверяют тесты:
tests/contract/test_equivalence.py и tests/unit/test_models.py.

Лишние поля — ошибка, как additionalProperties: false в схеме.
Все длины в мм, углы в градусах, плотность в g/cm3.

Разбор: Scene.from_dict(doc); обратно в JSON: scene.to_dict().

Каждая форма знает свою геометрию — габариты (local_bbox) и точки заведомо внутри
(probe_points). Это общее для всех целей; как записать форму в Geant4 или OpenMC,
решает цель (backends/<цель>/).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import product
from math import hypot, sqrt
from typing import ClassVar, Literal, Optional, Sequence, Union

from ..geometry import AABB, Rigid
from .record import AnyDict, List, Lit, Map, ModelError, Nullable, Num, Obj, OneOf, Record, Str, Vec

# --- общие виды полей (как $defs в схеме) ---
ID = Str(pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$", max_length=64)
EXT_NAME = Str(pattern=r"^(JINR|X_[A-Z]+)_[A-Za-z0-9_]+$")
VERSION = Str(pattern=r"^[0-9]+\.[0-9]+$")
NUM = Num()
POS = Num(gt=0)
NON_NEG = Num(ge=0)
VEC3 = Vec(NUM)
POS_VEC3 = Vec(POS)
EXTENSIONS = Nullable(Map(EXT_NAME, AnyDict()))
EXTRAS = Nullable(AnyDict())
TEXT = Nullable(Str())

Vec3 = tuple[float, float, float]
record = dataclass(frozen=True, kw_only=True)


def _on_axes(r: float) -> list[tuple[float, float, float]]:
    """Шесть точек на осях на расстоянии r от центра: (±r, 0, 0), (0, ±r, 0), (0, 0, ±r)."""
    return [(r, 0.0, 0.0), (-r, 0.0, 0.0), (0.0, r, 0.0), (0.0, -r, 0.0), (0.0, 0.0, r), (0.0, 0.0, -r)]


# --- поворот и размещение ---
@record
class RotIdentity(Record):
    convention: Literal["identity"] = Lit("identity").field()


@record
class RotMatrix(Record):
    convention: Literal["matrix_active"] = Lit("matrix_active").field()
    matrix: tuple[Vec3, Vec3, Vec3] = Vec(VEC3).field()      # по строкам; столбцы = оси тела в системе родителя


@record
class RotEuler(Record):
    convention: Literal["euler_xyz_extrinsic_deg"] = Lit("euler_xyz_extrinsic_deg").field()
    angles: Vec3 = VEC3.field()                               # вокруг неподвижных X, Y, Z: R = Rz·Ry·Rx


Rotation = Union[RotIdentity, RotMatrix, RotEuler]
ROTATION = OneOf("convention", lambda: {"identity": RotIdentity, "matrix_active": RotMatrix,
                                        "euler_xyz_extrinsic_deg": RotEuler})


@record
class Transform(Record):
    """Центр тела в системе родителя и активный поворот «тело -> родитель»."""
    translation: Vec3 = VEC3.field()
    rotation: Rotation = ROTATION.field()


TRANSFORM = Nullable(Obj(Transform))                         # у операнда булевой операции


# --- формы (все центрированы в своей локальной системе, размеры полные) ---
@record
class ShapeBase(Record):
    """Общее для всех форм: каждая форма знает свою геометрию, без привязки к цели."""

    def local_bbox(self) -> Optional[AABB]:
        """Габаритная коробка в собственной системе формы. None — неизвестна (меш)."""
        raise NotImplementedError(type(self).__name__)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Точки заведомо внутри формы, в её собственной системе (ими стенд проверяет
        повороты). Есть у всех примитивов; у булевых и мешей появятся на этапах 4 и 5."""
        return []

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        """Лежит ли точка (в собственной системе формы) внутри неё и не ближе margin мм
        к поверхности. Отрицательный margin — форма, раздутая на |margin|: так проверяют,
        что точка заведомо снаружи. Есть у всех примитивов; у булевых и мешей — этапы 4 и 5."""
        raise NotImplementedError(type(self).__name__)

    def placed_bbox(self) -> Optional[AABB]:
        """Коробка с учётом собственного transform (он есть у операндов булевых операций)."""
        box = self.local_bbox()
        tf = getattr(self, "transform", None)
        if box is None or tf is None:
            return box
        return box.transformed(Rigid.from_transform(tf))


@record
class Box(ShapeBase):
    type: Literal["box"] = Lit("box").field()
    size: Vec3 = POS_VEC3.field()                            # полные размеры, не половинки
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    PROBE_FRACTION: ClassVar[float] = 0.4                    # ±0.4·size — внутри (половина — 0.5)

    def local_bbox(self) -> AABB:
        hx, hy, hz = (s / 2 for s in self.size)
        return AABB.symmetric(hx, hy, hz)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Центр и 8 точек у углов."""
        hx, hy, hz = (self.PROBE_FRACTION * s for s in self.size)
        return [(0.0, 0.0, 0.0)] + [(sx * hx, sy * hy, sz * hz)
                                    for sx, sy, sz in product((-1, 1), repeat=3)]

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        return all(abs(p[i]) <= self.size[i] / 2 - margin for i in range(3))


@record
class Cylinder(ShapeBase):
    type: Literal["cylinder"] = Lit("cylinder").field()      # вдоль локальной z
    radius: float = POS.field()
    height: float = POS.field()                              # полная длина
    inner_radius: float = NON_NEG.field(default=0.0)
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    PROBE_AXIAL: ClassVar[float] = 0.4                       # ±0.4·height — внутри (половина — 0.5)
    PROBE_RADIAL: ClassVar[float] = 0.5                      # 0.5·radius у сплошного цилиндра

    def local_bbox(self) -> AABB:
        return AABB.symmetric(self.radius, self.radius, self.height / 2)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Сплошной: центр, две точки на оси при ±0,4·H и четыре на 0,5·R по x и y.
        Труба (inner_radius > 0): внутри пусто, поэтому точки — в середине стенки,
        четыре по x и y при z = 0 и две при z = ±0,4·H."""
        z = self.PROBE_AXIAL * self.height
        if self.inner_radius == 0:
            r = self.PROBE_RADIAL * self.radius
            return [(0.0, 0.0, 0.0), (0.0, 0.0, z), (0.0, 0.0, -z),
                    (r, 0.0, 0.0), (-r, 0.0, 0.0), (0.0, r, 0.0), (0.0, -r, 0.0)]
        r = (self.inner_radius + self.radius) / 2
        return [(r, 0.0, 0.0), (-r, 0.0, 0.0), (0.0, r, 0.0), (0.0, -r, 0.0),
                (r, 0.0, z), (-r, 0.0, -z)]

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        r = hypot(p[0], p[1])
        return (abs(p[2]) <= self.height / 2 - margin and r <= self.radius - margin
                and (self.inner_radius == 0 or r >= self.inner_radius + margin))


@record
class Cone(ShapeBase):
    type: Literal["cone"] = Lit("cone").field()              # вдоль локальной z, bottom при z = -height/2
    radius_bottom: float = NON_NEG.field()
    radius_top: float = NON_NEG.field()
    height: float = POS.field()
    inner_radius_bottom: float = NON_NEG.field(default=0.0)
    inner_radius_top: float = NON_NEG.field(default=0.0)
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    PROBE_AXIAL: ClassVar[float] = 0.4                       # ±0.4·height, как у цилиндра
    PROBE_RADIAL: ClassVar[float] = 0.5                      # 0.5·радиуса при z = 0
    PROBE_END: ClassVar[float] = 0.75                        # 0.75·радиуса у концов: ловит перепутанный низ и верх

    def local_bbox(self) -> AABB:
        r = max(self.radius_bottom, self.radius_top)
        return AABB.symmetric(r, r, self.height / 2)

    def radii_at(self, z: float) -> tuple[float, float]:
        """Внутренний и внешний радиус на высоте z (линейно от низа при -H/2 до верха при +H/2)."""
        f = z / self.height + 0.5
        return (self.inner_radius_bottom + (self.inner_radius_top - self.inner_radius_bottom) * f,
                self.radius_bottom + (self.radius_top - self.radius_bottom) * f)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Сплошной: центр, две точки на оси при ±0,4·H, четыре на 0,5·R(0) по x и y
        и по одной у концов на 0,75·R(z) — у низа по x, у верха по y. Если в Geant4
        перепутать низ и верх, точка у широкого конца окажется снаружи.
        Полый (есть внутренний радиус): точки в середине стенки — четыре при z = 0
        и по одной при z = ±0,4·H."""
        z = self.PROBE_AXIAL * self.height
        if self.inner_radius_bottom == 0 and self.inner_radius_top == 0:
            r0 = self.PROBE_RADIAL * self.radii_at(0.0)[1]
            rb = self.PROBE_END * self.radii_at(-z)[1]
            rt = self.PROBE_END * self.radii_at(z)[1]
            return [(0.0, 0.0, 0.0), (0.0, 0.0, z), (0.0, 0.0, -z),
                    (r0, 0.0, 0.0), (-r0, 0.0, 0.0), (0.0, r0, 0.0), (0.0, -r0, 0.0),
                    (rb, 0.0, -z), (0.0, rt, z)]
        r0, rb, rt = (sum(self.radii_at(h)) / 2 for h in (0.0, -z, z))
        return [(r0, 0.0, 0.0), (-r0, 0.0, 0.0), (0.0, r0, 0.0), (0.0, -r0, 0.0),
                (rb, 0.0, -z), (-rt, 0.0, z)]

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        # margin у боковой поверхности отсчитывается по радиусу: по нормали выходит чуть меньше
        if abs(p[2]) > self.height / 2 - margin:
            return False
        ri, ro = self.radii_at(p[2])
        r = hypot(p[0], p[1])
        hollow = self.inner_radius_bottom > 0 or self.inner_radius_top > 0
        return r <= ro - margin and (not hollow or r >= ri + margin)


@record
class Sphere(ShapeBase):
    type: Literal["sphere"] = Lit("sphere").field()
    radius: float = POS.field()
    inner_radius: float = NON_NEG.field(default=0.0)
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    PROBE_RADIAL: ClassVar[float] = 0.5                      # 0.5·radius у сплошного шара

    def local_bbox(self) -> AABB:
        return AABB.symmetric(self.radius, self.radius, self.radius)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Сплошной шар: центр и шесть точек на осях на 0,5·R.
        Полый (inner_radius > 0): внутри пусто — шесть точек на осях в середине стенки."""
        if self.inner_radius == 0:
            r = self.PROBE_RADIAL * self.radius
            return [(0.0, 0.0, 0.0)] + _on_axes(r)
        return _on_axes((self.inner_radius + self.radius) / 2)

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        d = sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
        return d <= self.radius - margin and (self.inner_radius == 0 or d >= self.inner_radius + margin)


@record
class Torus(ShapeBase):
    type: Literal["torus"] = Lit("torus").field()            # ось вращения = локальная z
    major_radius: float = POS.field()                        # от оси до центра трубки
    minor_radius: float = POS.field()                        # радиус трубки
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    PROBE_TUBE: ClassVar[float] = 0.5                        # сдвиг от центра трубки: 0.5·minor_radius

    def local_bbox(self) -> AABB:
        r = self.major_radius + self.minor_radius
        return AABB.symmetric(r, r, self.minor_radius)

    def probe_points(self) -> list[tuple[float, float, float]]:
        """Центр тора пустой (там дырка), поэтому точки — в трубке: четыре на её осевой
        окружности (радиус major_radius в плоскости z = 0) и четыре со сдвигом на 0,5·r
        от неё — наружу, внутрь, вверх и вниз."""
        big, d = self.major_radius, self.PROBE_TUBE * self.minor_radius
        return [(big, 0.0, 0.0), (-big, 0.0, 0.0), (0.0, big, 0.0), (0.0, -big, 0.0),
                (big + d, 0.0, 0.0), (0.0, big - d, 0.0), (-big, 0.0, d), (0.0, -big, -d)]

    def contains(self, p: Sequence[float], margin: float = 0.0) -> bool:
        return hypot(hypot(p[0], p[1]) - self.major_radius, p[2]) <= self.minor_radius - margin


OPERAND = OneOf("type", lambda: OPERANDS)                    # словарь OPERANDS — ниже


@record
class Boolean(ShapeBase):
    type: Literal["boolean"] = Lit("boolean").field()
    op: Literal["union", "subtract", "intersect"] = Lit("union", "subtract", "intersect").field()
    left: Operand = OPERAND.field()                          # subtract = left минус right
    right: Operand = OPERAND.field()
    transform: Optional[Transform] = TRANSFORM.field(default=None)

    def local_bbox(self) -> Optional[AABB]:
        left, right = self.left.placed_bbox(), self.right.placed_bbox()
        if left is None or right is None:
            return None
        if self.op == "union":
            return left.hull(right)
        if self.op == "subtract":
            return left                                     # вычитание тело не увеличивает
        return left.intersection(right) or left             # intersect


@record
class Tessellation(Record):
    linear_deflection: Optional[float] = Nullable(POS).field(default=None)
    angular_deflection_deg: Optional[float] = Nullable(POS).field(default=None)


@record
class Mesh(ShapeBase):
    type: Literal["mesh"] = Lit("mesh").field()              # STL в мм, в локальной системе тела
    uri: str = Str(pattern=r"^[^\\:]+\.stl$").field()
    encoding: Literal["stl-binary", "stl-ascii"] = Lit("stl-binary", "stl-ascii").field()
    sha256: str = Str(pattern=r"^[0-9a-f]{64}$").field()
    n_facets: int = Num(ge=4, integer=True).field()
    fallback_reason: str = Lit("SPLINE_SURFACE", "PRIMITIVE_FIT_FAILED",
                               "BOOLEAN_TOO_COMPLEX", "USER_FORCED").field()
    tessellation: Optional[Tessellation] = Nullable(Obj(Tessellation)).field(default=None)
    note: Optional[str] = TEXT.field(default=None)

    def local_bbox(self) -> None:
        return None                               # размер знает только сам STL


Operand = Union[Box, Cylinder, Cone, Sphere, Torus, Boolean]
Shape = Union[Box, Cylinder, Cone, Sphere, Torus, Boolean, Mesh]
OPERANDS = {"box": Box, "cylinder": Cylinder, "cone": Cone, "sphere": Sphere, "torus": Torus,
            "boolean": Boolean}
SHAPES = {**OPERANDS, "mesh": Mesh}


# --- материалы ---
@record
class Component(Record):
    element: str = Str(pattern=r"^[A-Z][a-z]?$").field()
    fraction: float = Num(gt=0, le=1).field()


@record
class Composition(Record):
    basis: Literal["mass", "atom"] = Lit("mass", "atom").field()
    components: tuple[Component, ...] = List(Obj(Component), min_length=1).field()


@record
class Material(Record):
    id: str = ID.field()
    name: Optional[str] = TEXT.field(default=None)
    nist: Optional[str] = Nullable(Str(pattern=r"^G4_[A-Za-z0-9_-]+$")).field(default=None)
    density: Optional[float] = Nullable(POS).field(default=None)       # g/cm3
    state: Optional[str] = Nullable(Lit("solid", "liquid", "gas")).field(default=None)
    composition: Optional[Composition] = Nullable(Obj(Composition)).field(default=None)
    provenance: Optional[str] = TEXT.field(default=None)
    extensions: Optional[dict] = EXTENSIONS.field(default=None)
    extras: Optional[dict] = EXTRAS.field(default=None)

    def check(self, where: str) -> None:
        # схема: anyOf [nist] | [density, composition]
        if self.nist is None and (self.density is None or self.composition is None):
            raise ModelError(where, "у материала нужно nist или density + composition")


# --- тела и сцена ---
@record
class Verification(Record):
    """Посчитано FreeCAD по B-rep; детей не вычитать."""
    cad_volume: float = POS.field()                          # мм3
    cad_area: Optional[float] = Nullable(POS).field(default=None)      # мм2
    bbox: Optional[tuple[Vec3, Vec3]] = Nullable(Vec(VEC3, 2)).field(default=None)  # в системе родителя


@record
class Body(Record):
    id: str = ID.field()
    name: Optional[str] = TEXT.field(default=None)
    parent: Optional[str] = Nullable(ID).field()             # обязательно в файле, null = лежит в мире
    material: str = ID.field()
    transform: Transform = Obj(Transform).field()
    shape: Shape = OneOf("type", lambda: SHAPES).field()
    verification: Verification = Obj(Verification).field()
    extensions: Optional[dict] = EXTENSIONS.field(default=None)
    extras: Optional[dict] = EXTRAS.field(default=None)

    def bbox_from_shape(self) -> Optional[AABB]:
        """Коробка тела в системе родителя, посчитанная по форме и transform тела."""
        box = self.shape.local_bbox()
        return None if box is None else box.transformed(Rigid.from_transform(self.transform))


@record
class World(Record):
    material: str = ID.field()
    margin_percent: float = NON_NEG.field(default=10.0)


@record
class Source(Record):
    tool: Optional[str] = TEXT.field(default=None)
    tool_version: Optional[str] = TEXT.field(default=None)
    document: Optional[str] = TEXT.field(default=None)
    exported_at: Optional[str] = TEXT.field(default=None)


@record
class Units(Record):
    length: Literal["mm"] = Lit("mm").field()
    angle: Literal["deg"] = Lit("deg").field()
    density: Literal["g/cm3"] = Lit("g/cm3").field()


@record
class Scene(Record):
    format: Literal["jinr-mc-scene"] = Lit("jinr-mc-scene").field()
    format_version: str = VERSION.field()
    min_reader_version: Optional[str] = Nullable(VERSION).field(default=None)
    source: Optional[Source] = Nullable(Obj(Source)).field(default=None)
    units: Units = Obj(Units).field()
    extensions_used: tuple[str, ...] = List(EXT_NAME).field(default=())
    extensions_required: tuple[str, ...] = List(EXT_NAME).field(default=())
    world: World = Obj(World).field()
    materials: tuple[Material, ...] = List(Obj(Material)).field()
    bodies: tuple[Body, ...] = List(Obj(Body), min_length=1).field()
    extensions: Optional[dict] = EXTENSIONS.field(default=None)
    extras: Optional[dict] = EXTRAS.field(default=None)

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
