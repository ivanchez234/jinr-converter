"""План генерации для Geant4 (пункты 1.2 и 1.6 плана).

Принтер C++ не видит ни сырой JSON, ни Scene IR: ему передаётся готовый G4Plan,
где всё уже посчитано — порядок тел, имена, матрицы, C++ для форм и материалов,
размер мира, пробные точки. Тогда шаблоны не ломаются, когда меняется схема.

Пробные точки — главная автоматическая проверка поворотов. Для каждого тела без
детей берутся точки внутри формы в её локальной системе, переводятся в мировые
координаты через всю цепочку родителей, и стенд в Geant4 проверяет, что в этой
точке находится именно это тело с этим материалом. Если перепутана ось или матрица,
у несимметричной коробки угловые точки окажутся снаружи.
"""
from __future__ import annotations

import hashlib
import heapq
import os
import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from ... import __version__
from ...diagnostics import Diagnostic, has_errors
from ...passes.materials import plan_materials
from ...passes.naming import WORLD, assign_names
from ...passes.rotations import IDENTITY, Mat3, Rigid, Vec3
from ...passes.world import WorldPlan, plan_world
from ..base import CheckRow
from . import cppfmt as f
from .capabilities import check

PROBE_FRACTION = 0.4     # доля полного размера: ±0.4·size лежит внутри коробки (половина — 0.5)
BOX_VOLUME_TOL = 1e-6    # объём коробки Geant4 считает точно


@dataclass(frozen=True)
class SolidPlan:
    cpp: str             # new G4Box("Body", 25*mm, 25*mm, 25*mm)
    comment: str         # коробка 50 × 50 × 50 мм (G4Box берёт половины)


@dataclass(frozen=True)
class Probe:
    point: Vec3          # мировые координаты, мм
    volume: str          # какой физический объём должен там найтись
    material: str        # имя G4Material, которое должно там найтись


@dataclass(frozen=True)
class MaterialEntry:
    id: str              # id из JSON — ключ в реестре материалов
    g4_name: str         # имя G4Material (для NIST — G4_Fe)
    cpp: str             # scene::Nist("G4_Fe")
    comment: str         # Железо


@dataclass(frozen=True)
class BodyPlan:
    id: str
    volume: str          # имя объёма в Geant4
    func: str            # BuildBody_Body
    title: str           # Тело "Body" — «Тело»; материал: Железо, G4_Fe
    solid: SolidPlan
    material_id: str
    mother: str          # имя объёма-матери: "world" или объём родителя
    matrix: Mat3         # поворот «тело -> родитель», по строкам
    rotation_note: str   # откуда поворот: «углы X, Y, Z = 0°, 0°, 90° ...»; "" — без поворота
    translation: Vec3    # центр тела в системе родителя, мм
    cad_volume: float    # мм3
    volume_tol: float    # относительный допуск объёма в стенде
    probes: tuple[Probe, ...]


@dataclass(frozen=True)
class G4Plan:
    scene_name: str      # имя сцены для CMake-проекта: kub, 02_box_20x40x70
    input_name: str      # имя входного файла (без пути: в коде не должно быть абсолютных путей)
    input_sha256: str
    format_version: str
    generator_version: str
    world: WorldPlan
    materials: tuple[MaterialEntry, ...]
    bodies: tuple[BodyPlan, ...]           # родители раньше детей


@dataclass(frozen=True)
class PlanResult:
    plan: G4Plan | None                    # None, если есть ошибки
    rows: list[CheckRow]
    diagnostics: list[Diagnostic]


def build_plan(scene, input_path: str | os.PathLike) -> PlanResult:
    diags: list[Diagnostic] = []
    rows, d = check(scene)
    diags += d
    world, d = plan_world(scene)
    diags += d
    names, d = assign_names(scene)
    diags += d
    mats, d = plan_materials(scene)
    diags += d
    if has_errors(diags) or world is None:
        return PlanResult(None, rows, diags)

    materials = tuple(MaterialEntry(
        m.id, m.nist or m.id, "scene::Nist(%s)" % f.cpp_str(m.nist), f.comment(m.name or m.id))
        for m in mats)
    g4_name = {m.id: m.g4_name for m in materials}
    mat_title = {m.id: m.comment for m in materials}

    by_id = {b.id: b for b in scene.bodies}
    has_children = {b.parent for b in scene.bodies if b.parent is not None}
    to_world = _world_transforms(scene)

    bodies = []
    for b in topological_order(scene):
        n = names[b.id]
        local = Rigid.from_transform(b.transform)
        probes = () if b.id in has_children else tuple(
            Probe(_clean(to_world[b.id].apply(p)), n.volume, g4_name[b.material])
            for p in local_probe_points(b.shape))
        bodies.append(BodyPlan(
            id=b.id,
            volume=n.volume,
            func=n.func,
            title=_title(b, mat_title[b.material], g4_name[b.material]),
            solid=solid_plan(b.shape, n.volume),
            material_id=b.material,
            mother=names[b.parent].volume if b.parent is not None else WORLD,
            matrix=local.r,
            rotation_note=_rotation_note(b.transform.rotation, local.r),
            translation=_clean(local.t),
            cad_volume=b.verification.cad_volume,
            volume_tol=BOX_VOLUME_TOL,
            probes=probes,
        ))
    assert len(bodies) == len(by_id)

    path = Path(input_path)
    plan = G4Plan(
        scene_name=scene_name(path),
        input_name=path.name,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        format_version=scene.format_version,
        generator_version=__version__,
        world=world,
        materials=materials,
        bodies=tuple(bodies),
    )
    return PlanResult(plan, rows, diags)


# --- формы (этап 1: только коробка) ---
def solid_plan(shape, name: str) -> SolidPlan:
    if shape.type == "box":
        hx, hy, hz = (s / 2 for s in shape.size)
        return SolidPlan(
            "new G4Box(%s, %s, %s, %s)" % (f.cpp_str(name), f.mm(hx), f.mm(hy), f.mm(hz)),
            "коробка %s мм (G4Box берёт половины)" % f.sizes(shape.size))
    raise NotImplementedError(shape.type)      # check() не пропустит сюда другие формы


def local_probe_points(shape) -> list[Vec3]:
    """Точки заведомо внутри формы, в её локальной системе."""
    if shape.type == "box":
        hx, hy, hz = (PROBE_FRACTION * s for s in shape.size)
        return [(0.0, 0.0, 0.0)] + [(sx * hx, sy * hy, sz * hz)
                                    for sx, sy, sz in product((-1, 1), repeat=3)]
    return []


# --- порядок и цепочки родителей ---
def topological_order(scene) -> list:
    """Родитель раньше ребёнка, а в остальном — порядок в файле."""
    index = {b.id: i for i, b in enumerate(scene.bodies)}
    children: dict[str, list[str]] = {}
    ready = []
    for b in scene.bodies:
        if b.parent is None:
            heapq.heappush(ready, index[b.id])
        else:
            children.setdefault(b.parent, []).append(b.id)
    order = []
    while ready:
        b = scene.bodies[heapq.heappop(ready)]
        order.append(b)
        for c in children.get(b.id, []):
            heapq.heappush(ready, index[c])
    return order


def _world_transforms(scene) -> dict[str, Rigid]:
    """id тела -> преобразование «тело -> мир» через всю цепочку родителей."""
    out: dict[str, Rigid] = {}
    for b in topological_order(scene):
        local = Rigid.from_transform(b.transform)
        out[b.id] = local if b.parent is None else out[b.parent].then_child(local)
    return out


# --- мелочи ---
def scene_name(path: Path) -> str:
    """kub.json -> kub; tests/fixtures/freecad/02_box/scene.json -> 02_box."""
    stem = path.parent.name if path.stem == "scene" and path.parent.name else path.stem
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    return name if re.search(r"[A-Za-z0-9]", name) else "scene"


def _title(b, mat_name: str, g4_name: str) -> str:
    parts = ['Тело "%s"' % b.id]
    if b.name:
        parts.append("«%s»" % f.comment(b.name))
    mat = mat_name if mat_name == g4_name else "%s, %s" % (mat_name, g4_name)
    return "%s; материал: %s" % (" — ".join(parts), mat)


def _rotation_note(rot, m: Mat3) -> str:
    if m == IDENTITY:
        return ""
    if rot.convention == "euler_xyz_extrinsic_deg":
        return "из JSON: углы X, Y, Z = %s (сначала X, потом Y, потом Z)" % ", ".join(
            f.num(a) + "°" for a in rot.angles)
    return "из JSON: матрица, столбцы — оси тела в системе родителя"


def _clean(v) -> Vec3:
    return tuple(round(float(x), 9) + 0.0 for x in v)  # type: ignore[return-value]
