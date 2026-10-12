"""Scene IR: pydantic-модели сцены jinr-mc-scene v0.1.

Нормативна рукописная схема contracts/scene/v0.1/schema/scene.schema.json,
модели подстраиваются под неё. Совпадение проверяют тесты:
tests/contract/test_equivalence.py и tests/unit/test_models.py.

extra="forbid" повторяет additionalProperties: false из схемы.
Все длины в мм, углы в градусах, плотность в g/cm3.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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
class Box(Strict):
    type: Literal["box"]
    size: PosVec3                             # полные размеры, не половинки
    transform: Optional[Transform] = None     # только у операнда булевой операции


class Cylinder(Strict):
    type: Literal["cylinder"]                 # вдоль локальной z
    radius: PosFloat
    height: PosFloat                          # полная длина
    inner_radius: NonNegFloat = 0.0
    transform: Optional[Transform] = None


class Cone(Strict):
    type: Literal["cone"]                     # вдоль локальной z, bottom при z = -height/2
    radius_bottom: NonNegFloat
    radius_top: NonNegFloat
    height: PosFloat
    inner_radius_bottom: NonNegFloat = 0.0
    inner_radius_top: NonNegFloat = 0.0
    transform: Optional[Transform] = None


class Sphere(Strict):
    type: Literal["sphere"]
    radius: PosFloat
    inner_radius: NonNegFloat = 0.0
    transform: Optional[Transform] = None


class Torus(Strict):
    type: Literal["torus"]                    # ось вращения = локальная z
    major_radius: PosFloat                    # от оси до центра трубки
    minor_radius: PosFloat                    # радиус трубки
    transform: Optional[Transform] = None


class Boolean(Strict):
    type: Literal["boolean"]
    op: Literal["union", "subtract", "intersect"]   # subtract = left минус right
    left: Operand
    right: Operand
    transform: Optional[Transform] = None


class Tessellation(Strict):
    linear_deflection: Optional[PosFloat] = None
    angular_deflection_deg: Optional[PosFloat] = None


class Mesh(Strict):
    type: Literal["mesh"]                     # STL в мм, в локальной системе тела
    uri: Annotated[str, StringConstraints(pattern=r"^[^\\:]+\.stl$")]
    encoding: Literal["stl-binary", "stl-ascii"]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    n_facets: Annotated[int, Field(ge=4)]
    fallback_reason: Literal["SPLINE_SURFACE", "PRIMITIVE_FIT_FAILED",
                             "BOOLEAN_TOO_COMPLEX", "USER_FORCED"]
    tessellation: Optional[Tessellation] = None
    note: Optional[str] = None


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
