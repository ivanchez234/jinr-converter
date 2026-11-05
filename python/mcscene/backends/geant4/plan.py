"""План генерации для Geant4: Geant4Planner превращает сцену в G4Plan.

Шаблоны не видят ни сырой JSON, ни Scene IR: им передаётся готовый G4Plan, где всё
уже посчитано — порядок тел, имена, матрицы, половины размеров, материалы, размер мира,
пробные точки. C++ здесь нет: как это записать, решают шаблоны в templates/
(решение 001). Тогда шаблоны не ломаются, когда меняется схема.

Пробные точки — главная автоматическая проверка поворотов. Точки каждого тела в его
локальной системе считает общий проход ProbePass (passes/probes.py; у тела с детьми —
только там, где детей нет). Здесь они переводятся в мировые координаты через всю цепочку
родителей, и стенд в Geant4 проверяет, что в этой точке находится именно это тело с этим
материалом. Если перепутана ось или матрица, у несимметричной коробки угловые точки
окажутся снаружи.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ... import __version__
from ...diagnostics import Diagnostics
from ...geometry import IDENTITY, Mat3, Rigid, Rotation, Vec3
from ...passes import MaterialPass, MaterialPlan, ProbePass, WorldPass, WorldPlan
from ..base import PlanResult, check_shapes
from .capabilities import SHAPES
from .filters import comment, num
from .naming import WORLD, BodyNames, Geant4Naming
from .solids import SOLIDS, SolidData


@dataclass(frozen=True)
class Probe:
    point: Vec3          # мировые координаты, мм
    volume: str          # какой физический объём должен там найтись
    material: str        # имя G4Material, которое должно там найтись


@dataclass(frozen=True)
class MaterialEntry:
    id: str              # id из JSON — ключ в реестре материалов
    g4_name: str         # имя G4Material (для NIST — G4_Fe)
    nist: str            # имя в базе NIST Geant4: G4_Fe
    comment: str         # Железо


@dataclass(frozen=True)
class BodyPlan:
    id: str
    volume: str          # имя объёма в Geant4
    func: str            # BuildBody_Body
    title: str           # Тело "Body" — «Тело»; материал: Железо, G4_Fe
    solid: SolidData     # данные фигуры для _solids.j2 (SolidPlan, TubsPlan…)
    material_id: str
    mother: str          # имя объёма-матери: "world" или объём родителя
    matrix: Mat3         # поворот «тело -> родитель», по строкам
    rotation_note: str   # откуда поворот: «углы X, Y, Z = 0°, 0°, 90° ...»; "" — без поворота
    axes_note: str       # куда смотрят оси тела: «x -> +y, y -> -x, z -> +z»; "" — без поворота
    translation: Vec3    # центр тела в системе родителя, мм
    cad_volume: float    # мм3
    volume_tol: float    # относительный допуск объёма в стенде
    probes: tuple[Probe, ...]

    @property
    def rotated(self) -> bool:
        """Есть ли поворот: без него шаблон пишет g4scene::kIdentity."""
        return self.matrix != IDENTITY


@dataclass(frozen=True)
class G4Plan:
    scene_name: str      # имя сцены для CMake-проекта: kub, 02_box_20x40x70
    namespace: str       # пространство имён C++ классов сцены: kub, scene_02_box_20x40x70
    input_name: str      # имя входного файла (без пути: в коде не должно быть абсолютных путей)
    input_sha256: str
    format_version: str
    generator_version: str
    world: WorldPlan
    materials: tuple[MaterialEntry, ...]
    bodies: tuple[BodyPlan, ...]           # родители раньше детей
    unsafe: bool = False                   # сгенерировано с --unsafe-skip-checks (отладка)


class Geant4Planner:
    """Сцена -> G4Plan.

    Шаги — проходы с общим входом run(scene, diags): фигуры, мир, имена, материалы.
    Ошибки всех шагов собираются вместе (человек сразу видит все); если они есть,
    плана нет.
    """

    def __init__(self, scene, source: str | os.PathLike, unsafe: bool = False) -> None:
        self.scene = scene
        self.source = Path(source)
        self.unsafe = unsafe

    def build(self) -> PlanResult:
        diags = Diagnostics()
        rows, found = check_shapes(self.scene, SHAPES, "geant4")
        diags.extend(found)
        world = WorldPass().run(self.scene, diags)
        names = Geant4Naming().run(self.scene, diags)
        mats = MaterialPass().run(self.scene, diags)
        if diags.has_errors or world is None:
            return PlanResult(None, rows, list(diags))
        probes = ProbePass().run(self.scene, diags)
        if diags.has_errors:
            return PlanResult(None, rows, list(diags))

        materials = self._materials(mats)
        plan = G4Plan(
            scene_name=scene_name(self.source),
            namespace=Geant4Naming.cpp_namespace(scene_name(self.source)),
            input_name=self.source.name,
            input_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
            format_version=self.scene.format_version,
            generator_version=__version__,
            world=world,
            materials=materials,
            bodies=self._bodies(names, materials, probes),
            unsafe=self.unsafe,
        )
        return PlanResult(plan, rows, list(diags))

    def _materials(self, mats: list[MaterialPlan]) -> tuple[MaterialEntry, ...]:
        return tuple(MaterialEntry(m.id, m.nist or m.id, m.nist, comment(m.name or m.id)) for m in mats)

    def _bodies(self, names: dict[str, BodyNames], materials: tuple[MaterialEntry, ...],
                local_probes: dict[str, tuple[Vec3, ...]]) -> tuple[BodyPlan, ...]:
        g4_name = {m.id: m.g4_name for m in materials}
        mat_title = {m.id: m.comment for m in materials}
        to_world = self.scene.world_transforms()

        out = []
        for b in self.scene.parents_first():
            n = names[b.id]
            emitter = SOLIDS[b.shape.type]          # check_shapes пропустил только умеющие фигуры
            local = Rigid.from_transform(b.transform)
            probes = tuple(Probe(_clean(to_world[b.id].apply(p)), n.volume, g4_name[b.material])
                           for p in local_probes[b.id])
            out.append(BodyPlan(
                id=b.id,
                volume=n.volume,
                func=n.func,
                title=_title(b, mat_title[b.material], g4_name[b.material]),
                solid=emitter.solid(b.shape, n.volume),
                material_id=b.material,
                mother=names[b.parent].volume if b.parent is not None else WORLD,
                matrix=local.rotation.matrix,
                rotation_note=_rotation_note(b.transform.rotation, local.rotation),
                axes_note=_axes_note(local.rotation),
                translation=_clean(local.t),
                cad_volume=b.verification.cad_volume,
                volume_tol=emitter.volume_tol,
                probes=probes,
            ))
        assert len(out) == len(self.scene.bodies)
        return tuple(out)


# --- мелкие помощники (без состояния) ----------------------------------------------
def scene_name(path: Path) -> str:
    """kub.json -> kub; tests/fixtures/freecad/02_box/scene.json -> 02_box."""
    stem = path.parent.name if path.stem == "scene" and path.parent.name else path.stem
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    return name if re.search(r"[A-Za-z0-9]", name) else "scene"


def _title(b, mat_name: str, g4_name: str) -> str:
    parts = ['Тело "%s"' % b.id]
    if b.name:
        parts.append("«%s»" % comment(b.name))
    mat = mat_name if mat_name == g4_name else "%s, %s" % (mat_name, g4_name)
    return "%s; материал: %s" % (" — ".join(parts), mat)


def _rotation_note(rot, rotation: Rotation) -> str:
    if rotation.is_identity:
        return ""
    if rot.convention == "euler_xyz_extrinsic_deg":
        return "из JSON: углы X, Y, Z = %s (сначала X, потом Y, потом Z)" % ", ".join(
            num(a) + "°" for a in rot.angles)
    return "из JSON: матрица, столбцы — оси тела в системе родителя"


def _axes_note(rotation: Rotation) -> str:
    """Куда смотрят оси тела в системе родителя (столбцы матрицы) — подпись к матрице в коде.

    Ось, которая легла вдоль оси родителя, пишется как «+y» / «-z», остальные — вектором
    с тремя знаками после точки: «(0.707, 0.707, 0)». Сама матрица в коде не округляется.
    """
    if rotation.is_identity:
        return ""
    m = rotation.matrix
    parts = []
    for j, axis in enumerate("xyz"):
        col = [m[i][j] for i in range(3)]
        along = [i for i in range(3) if abs(abs(col[i]) - 1.0) < 1e-12]
        if along:
            i = along[0]
            parts.append("%s -> %s%s" % (axis, "+" if col[i] > 0 else "-", "xyz"[i]))
        else:
            parts.append("%s -> (%s)" % (axis, ", ".join(num(round(x, 3)) for x in col)))
    return ", ".join(parts)


def _clean(v) -> Vec3:
    return tuple(round(float(x), 9) + 0.0 for x in v)  # type: ignore[return-value]
