"""Цель geant4: CMake-проект Geant4 с геометрией сцены, стендом проверки и окном с моделью.

Здесь только то, что отличает Geant4 от других целей:
  - какие фигуры он умеет (capabilities.py);
  - как из сцены получаются данные для шаблонов (Geant4Planner в plan.py -> G4Plan);
  - что видят шаблоны (context) — в том числе цвета для vis.mac;
  - где лежит пакет шаблонов (templates/) и фильтры записи (filters.py);
  - report.json и копия g4scene.
Порядок шагов (план -> шаблоны -> запись) — общий, в Backend.generate (base.py).

C++ здесь нет: весь текст файлов — в templates/, правила записи значений — в filters.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ...diagnostics import Diagnostic
from ...paths import G4SCENE_SRC
from ..base import Backend, PlanResult
from .capabilities import SHAPES
from .filters import FILTERS
from .plan import G4Plan, Geant4Planner

TEMPLATES = Path(__file__).resolve().parent / "templates"
REPORT = "report.json"        # пишется json.dumps, а не шаблоном (правило 5 решения 001)

# Цвета тел по материалам (r, g, b): различимые и стабильные от запуска к запуску.
PALETTE = [(0.12, 0.47, 0.71), (1.0, 0.5, 0.05), (0.17, 0.63, 0.17), (0.84, 0.15, 0.16),
           (0.58, 0.4, 0.74), (0.55, 0.34, 0.29), (0.89, 0.47, 0.76), (0.5, 0.5, 0.5),
           (0.74, 0.74, 0.13), (0.09, 0.75, 0.81)]
PARENT_OPACITY = 0.3     # тела, внутри которых есть другие тела, — полупрозрачные


@dataclass(frozen=True)
class VisColour:
    """Строка /vis/geometry/set/colour в vis.mac."""
    volume: str
    material_id: str
    material_name: str
    first_of_material: bool  # перед первым телом материала печатается строка-подпись
    rgb: tuple[float, float, float]
    alpha: float


class Geant4Backend(Backend):
    name = "geant4"
    description = "CMake-проект Geant4: геометрия сцены, стенд check_geometry, окно scene_app"
    capabilities = SHAPES
    templates_dir = TEMPLATES
    filters = FILTERS

    def plan(self, scene, source: Path, unsafe: bool = False) -> PlanResult:
        return Geant4Planner(scene, source, unsafe=unsafe).build()

    def context(self, plan: G4Plan) -> dict[str, Any]:
        """Всё, что видят шаблоны. Считается здесь, в шаблонах — только печать."""
        return {
            "plan": plan,
            "world": plan.world,
            "materials": plan.materials,
            "bodies": plan.bodies,
            "solid_kinds": sorted({b.solid.kind for b in plan.bodies}),
            "colours": self.vis_colours(plan),
        }

    def extra_files(self, plan: G4Plan, diagnostics: list[Diagnostic]) -> dict[str, str]:
        return {REPORT: self.report(plan, diagnostics)}

    def resources(self) -> dict[str, Path]:
        return {"g4scene": G4SCENE_SRC}

    def next_steps(self, out_dir: str) -> list[str]:
        return ["source $HOME/geant4/install/bin/geant4.sh      # или g4env",
                "cmake -S %s -B %s/build" % (out_dir, out_dir),
                "cmake --build %s/build -j$(nproc)" % out_dir,
                "%s/build/check_geometry                 # стенд проверки" % out_dir,
                "cd %s/build && ./scene_app             # окно Geant4 с моделью" % out_dir]

    # --- помощники цели ------------------------------------------------------------
    @staticmethod
    def vis_colours(plan: G4Plan) -> list[VisColour]:
        """Цвет по материалу (по порядку появления), родители — полупрозрачные."""
        names = {m.id: m.comment for m in plan.materials}
        parents = {b.mother for b in plan.bodies}
        colour: dict[str, tuple[float, float, float]] = {}
        out = []
        for b in plan.bodies:
            first = b.material_id not in colour
            if first:
                colour[b.material_id] = PALETTE[len(colour) % len(PALETTE)]
            out.append(VisColour(b.volume, b.material_id, names.get(b.material_id, ""), first,
                                 colour[b.material_id], PARENT_OPACITY if b.volume in parents else 1))
        return out

    @staticmethod
    def report(plan: G4Plan, diagnostics: list[Diagnostic]) -> str:
        """report.json: что сгенерировано, из чего и с какими сообщениями."""
        report = {
            "generator": {"name": "mcscene", "version": plan.generator_version},
            "target": "geant4",
            "flags": {"unsafe_skip_checks": plan.unsafe},
            "input": {"file": plan.input_name, "sha256": plan.input_sha256,
                      "format_version": plan.format_version},
            "world": {"material": plan.world.material, "half_size_mm": list(plan.world.half_size),
                      "margin_percent": plan.world.margin_percent},
            "materials": [{"id": m.id, "geant4": m.g4_name} for m in plan.materials],
            "bodies": [{"id": b.id, "volume": b.volume, "mother": b.mother, "material": b.material_id,
                        "cad_volume_mm3": b.cad_volume, "probes": len(b.probes)} for b in plan.bodies],
            "diagnostics": [{k: v for k, v in asdict(d).items() if v is not None} for d in diagnostics],
        }
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
