"""Пробные точки у тел с детьми (ProbePass, этап 3.2) и то, на чём они держатся:
принадлежность точки форме (Shape.contains) и обратное преобразование (Rigid.inverse).

Ожидаемые числа — свои; принадлежность сверяется с validate.py — он написан отдельно.
"""
import json
import math
import random

import pytest

from mcscene.diagnostics import Diagnostics
from mcscene.geometry import Rigid, Rotation
from mcscene.io.contract import load_contract_validator
from mcscene.model import Box, Cone, Cylinder, Scene, Sphere, Torus
from mcscene.paths import FREECAD_FIXTURES
from mcscene.passes import ProbePass

PIPE = FREECAD_FIXTURES / "08_pipe_vacuum" / "scene.json"


def probes(scene_dict):
    diags = Diagnostics()
    return ProbePass().run(Scene.from_dict(scene_dict), diags), list(diags)


def scene(*bodies):
    return {"format": "jinr-mc-scene", "format_version": "0.1",
            "units": {"length": "mm", "angle": "deg", "density": "g/cm3"},
            "world": {"material": "air"}, "materials": [{"id": "air", "nist": "G4_AIR"}],
            "bodies": [{"id": i, "parent": parent, "material": "air", "shape": shape,
                        "transform": {"translation": list(t), "rotation": {"convention": "identity"}},
                        "verification": {"cad_volume": 1}}
                       for i, parent, shape, t in bodies]}


# --- труба с вакуумом Никиты -------------------------------------------------------------
def test_pipe_probes_go_into_the_wall_and_the_caps():
    pts, diags = probes(json.loads(PIPE.read_text("utf-8")))
    assert diags == []
    # все обычные точки сплошного цилиндра (центр, ось, 0,5·R) — в вакууме, поэтому их нет;
    # лучи от центра находят стенку от R 55 до 60 и торцы от 495 до 500 — точки в их серединах
    assert sorted(pts["Pipe"]) == sorted([(57.5, 0.0, 0.0), (-57.5, 0.0, 0.0), (0.0, 57.5, 0.0),
                                          (0.0, -57.5, 0.0), (0.0, 0.0, 497.5), (0.0, 0.0, -497.5)])
    assert len(pts["Vacuum"]) == 7                      # у ребёнка — обычные точки цилиндра
    assert pts["Vacuum"][0] == (0.0, 0.0, 0.0)


def test_pipe_probes_in_cpp(tmp_path):
    from mcscene.cli import main
    out = tmp_path / "pipe"
    assert main(["generate", str(PIPE), "-o", str(out)]) == 0
    cc = (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")
    assert '  g4scene::Place(lv, LV("Pipe"), "Vacuum",\n' in cc
    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    assert '    {57.5, 0, 0, "Pipe", "G4_STAINLESS-STEEL"},\n' in checks
    assert '    {0, 0, -497.5, "Pipe", "G4_STAINLESS-STEEL"},\n' in checks
    assert '    {0, 0, 0, "Vacuum", "G4_Galactic"},\n' in checks
    assert 'new G4MultiFunctionalDetector("dose_Vacuum")' in (out / "user/DetectorConstruction.hh").read_text("utf-8")


def test_shifted_and_rotated_child():
    # ребёнок не в центре и повёрнут: точки родителя всё равно вне него
    child = {"type": "box", "size": [40, 10, 10]}
    d = scene(("P", None, {"type": "box", "size": [100, 100, 100]}, (0, 0, 0)),
              ("C", "P", child, (20, 0, 0)))
    d["bodies"][1]["transform"]["rotation"] = {"convention": "euler_xyz_extrinsic_deg", "angles": [0, 0, 90]}
    pts, diags = probes(d)
    assert diags == []
    c = Box(type="box", size=(40, 10, 10))
    to_child = Rigid(Rotation.about_z(90), (20.0, 0.0, 0.0)).inverse()
    assert pts["P"] and all(not c.contains(to_child.apply(p), -1e-6) for p in pts["P"])
    # ребёнок повёрнут на 90°: вдоль x он занимает от 15 до 25, луч +x свободен от 25 до 50
    assert (37.5, 0.0, 0.0) in pts["P"]


def test_child_fills_parent_gives_w340():
    d = scene(("P", None, {"type": "box", "size": [100, 100, 100]}, (0, 0, 0)),
              ("C", "P", {"type": "box", "size": [100, 100, 100]}, (0, 0, 0)))
    pts, diags = probes(d)
    assert pts["P"] == ()
    assert [(x.code, x.body_id) for x in diags] == [("W340", "P")]


# --- Rigid.inverse -----------------------------------------------------------------------
def test_rigid_inverse_undoes_apply():
    rig = Rigid(Rotation.euler_xyz_deg(20, 50, 30), (-100.0, 50.0, 20.0))
    for p in [(0, 0, 0), (1, 2, 3), (-40, 15, 70)]:
        q = rig.inverse().apply(rig.apply(p))
        assert all(math.isclose(q[i], p[i], abs_tol=1e-12) for i in range(3))


# --- Shape.contains против validate.py ---------------------------------------------------
SHAPES = [
    {"type": "box", "size": [20, 40, 70]},
    {"type": "cylinder", "radius": 30, "height": 120},
    {"type": "cylinder", "radius": 50, "inner_radius": 40, "height": 200},
    {"type": "cone", "radius_bottom": 40, "radius_top": 0, "height": 100},
    {"type": "cone", "radius_bottom": 60, "radius_top": 30, "height": 100,
     "inner_radius_bottom": 50, "inner_radius_top": 20},
    {"type": "sphere", "radius": 50},
    {"type": "sphere", "radius": 50, "inner_radius": 40},
    {"type": "torus", "major_radius": 100, "minor_radius": 20},
]
MODEL = {"box": Box, "cylinder": Cylinder, "cone": Cone, "sphere": Sphere, "torus": Torus}


@pytest.mark.parametrize("d", SHAPES, ids=lambda d: "%s%s" % (d["type"], "_hollow" if "inner_radius" in d
                                                                 or "inner_radius_bottom" in d else ""))
def test_contains_agrees_with_validate(d):
    ours = MODEL[d["type"]].from_dict(d)
    theirs = load_contract_validator().ShapeGeom(d)
    box = ours.local_bbox()
    rnd = random.Random(1)
    inside = 0
    for _ in range(3000):
        p = [rnd.uniform(box.lo[i] * 1.1, box.hi[i] * 1.1) for i in range(3)]
        # у границы ответы могут разойтись, поэтому сверка «с запасом»: сжатая форма ⊂ их форма ⊂ раздутая
        assert ours.contains(p, 1e-6) <= theirs.inside(p, 0) <= ours.contains(p, -1e-6), p
        inside += theirs.inside(p, 0)
    assert inside > 100                                   # точки внутри действительно были
