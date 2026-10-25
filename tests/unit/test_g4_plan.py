"""План генерации Geant4: порядок тел, C++ фрагменты, мир, пробные точки."""
import hashlib
import json
from itertools import product

import pytest

from mcscene.backends.geant4.filters import num
from mcscene.backends.geant4.plan import Geant4Planner, scene_name
from mcscene.io.contract import load_contract_validator
from mcscene.model import Scene
from mcscene.geometry import IDENTITY
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES, TEST_SCENES, all_test_scenes, scene_id

# Рукописный эталон коробки: в нём известны id ("Box") и размеры без поворота.
# Настоящий экспорт (scene.json рядом) проверяют тест эквивалентности, golden и e2e.sh.
BOX02 = FREECAD_FIXTURES / "02_box_20x40x70" / "etalon.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return Scene.model_validate(json.load(f))


def plan_of(path):
    r = Geant4Planner(load(path), path).build()
    assert r.plan is not None, [d for d in r.diagnostics if d.level == "ERROR"]
    return r.plan


# --- числа в C++ ---
@pytest.mark.parametrize("x, s", [(25.0, "25"), (25, "25"), (27.5, "27.5"), (-0.0, "0"), (0.0, "0"),
                                  (-150.0, "-150"), (0.1, "0.1"), (1100.55, "1100.55"),
                                  (1e20, "1e+20"), (1e-7, "1e-07")])
def test_number_format(x, s):
    assert num(x) == s


# --- коробка Никиты 02 ---
def test_box02_plan():
    p = plan_of(BOX02)
    assert p.scene_name == "etalon"
    assert p.input_name == "etalon.json"                      # без пути
    assert p.input_sha256 == hashlib.sha256(BOX02.read_bytes()).hexdigest()
    assert p.world.half_size == (352.0, 165.0, 165.0) and p.world.material == "air"
    assert [(m.id, m.g4_name, m.nist) for m in p.materials] == [
        ("air", "G4_AIR", "G4_AIR"),
        ("iron", "G4_Fe", "G4_Fe"),
    ]
    (b,) = p.bodies
    assert b.func == "BuildBody_Box" and b.mother == "world"
    # в плане только числа и имена; как это выглядит в C++, решает _solids.j2
    assert (b.solid.kind, b.solid.name, b.solid.size, b.solid.half) == ("box", "Box", (20, 40, 70), (10, 20, 35))
    assert not b.rotated
    assert b.title == 'Тело "Box" — «Железная коробка 20×40×70»; материал: Железо, G4_Fe'
    assert b.matrix == IDENTITY and b.translation == (310, -130, 115)
    assert b.cad_volume == 56000


def test_box02_probes_center_and_corners():
    (b,) = plan_of(BOX02).bodies
    expected = {(310.0, -130.0, 115.0)} | {(310 + sx * 8, -130 + sy * 16, 115 + sz * 28)
                                          for sx, sy, sz in product((-1, 1), repeat=3)}
    assert {pr.point for pr in b.probes} == expected
    assert {(pr.volume, pr.material) for pr in b.probes} == {("Box", "G4_Fe")}


def test_rotated_box_probes_follow_rotation():
    # 20×40×70, поворот 90° вокруг z: локальная x -> мировая y, локальная y -> мировая -x.
    # Значит в мире углы на ±16 по x (от 0.4·40) и на ±8 по y (от 0.4·20).
    (b,) = plan_of(TEST_SCENES / "rotated_box.json").bodies
    corners = {pr.point for pr in b.probes} - {(300.0, -150.0, 80.0)}
    assert corners == {(300 + sx * 16, -150 + sy * 8, 80 + sz * 28)
                       for sx, sy, sz in product((-1, 1), repeat=3)}


def test_nested_parent_first_and_probes_only_in_leaves():
    p = plan_of(TEST_SCENES / "nested_boxes.json")
    assert [(b.id, b.mother) for b in p.bodies] == [("outer", "world"), ("inner", "outer")]
    outer, inner = p.bodies
    assert outer.probes == ()                                   # у родителя есть ребёнок
    assert inner.translation == (50, -30, 10)                   # относительно родителя
    assert (50.0, -30.0, 110.0) in {pr.point for pr in inner.probes}   # а точка — в мире


def test_parents_first_keeps_file_order_otherwise(scene, box):
    s = scene(box("A", (1, 1, 1), (-50, 0, 0)),
              box("B", (2, 2, 2), parent="C"),
              box("C", (10, 10, 10), (0, 0, 0)),
              box("D", (1, 1, 1), (50, 0, 0)))
    assert [b.id for b in s.parents_first()] == ["A", "C", "B", "D"]


def test_unsupported_scene_has_no_plan():
    r = Geant4Planner(load(CONTRACT_V0_1 / "examples" / "02_nested_pipe.json"),
                      CONTRACT_V0_1 / "examples" / "02_nested_pipe.json").build()
    assert r.plan is None
    assert {d.code for d in r.diagnostics if d.level == "ERROR"} == {"E301", "E310"}


def test_deterministic():
    assert plan_of(BOX02) == plan_of(BOX02)


def test_scene_name():
    from pathlib import Path
    assert scene_name(Path("tests/scenes/kub.json")) == "kub"
    assert scene_name(Path("x/02_box_20x40x70/scene.json")) == "02_box_20x40x70"
    assert scene_name(Path("hall v2.json")) == "hall_v2"
    assert scene_name(Path("моя сцена.json")) == "scene"          # из одних подчёркиваний — запасное имя


# --- независимая проверка пробных точек кодом validate.py ---
GOOD = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()


def _buildable():
    for path in GOOD:
        if Geant4Planner(load(path), path).build().plan is not None:
            yield pytest.param(path, id=scene_id(path))


def _local_point(doc, body_id, p):
    """Мировая точка -> система тела, через Transform из validate.py (не через наш код)."""
    V = load_contract_validator()
    bodies = {b["id"]: b for b in doc["bodies"]}
    chain = []
    b = bodies[body_id]
    while b is not None:
        chain.append(b)
        b = bodies.get(b["parent"]) if b["parent"] else None
    for b in reversed(chain):                     # от корня к телу
        p = V.Transform(b["transform"]).inverse_apply(p)
    return p


def _inside_box(p, size, margin=1e-6):
    return all(abs(p[i]) < size[i] / 2 - margin for i in range(3))


@pytest.mark.parametrize("path", list(_buildable()))
def test_every_probe_lies_inside_its_body(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    sizes = {b["id"]: b["shape"]["size"] for b in doc["bodies"]}
    plan = plan_of(path)
    n = 0
    for b in plan.bodies:
        for pr in b.probes:
            assert _inside_box(_local_point(doc, b.id, pr.point), sizes[b.id]), (b.id, pr.point)
            n += 1
    assert n >= 9


def test_probes_catch_transposed_matrix(scene, box, tmp_path):
    """Если генератор возьмёт Rᵀ вместо R, часть пробных точек окажется снаружи.

    Это и есть то, что на этапе 1 проверит стенд в Geant4. Поворот 90° не годится
    (у коробки R и Rᵀ дают одно и то же место), поэтому здесь 30° и 45°.
    """
    rot = {"convention": "euler_xyz_extrinsic_deg", "angles": [30, 0, 45]}
    good = scene(box("b", (20, 40, 70), (300, -150, 80), rotation=rot))
    path = tmp_path / "scene.json"
    path.write_text(good.model_dump_json(exclude_unset=True), encoding="utf-8")
    doc = json.loads(path.read_text(encoding="utf-8"))

    probes = plan_of(path).bodies[0].probes
    assert all(_inside_box(_local_point(doc, "b", pr.point), (20, 40, 70)) for pr in probes)

    # та же сцена, но с транспонированной матрицей — как будто генератор ошибся
    m = plan_of(path).bodies[0].matrix
    doc_t = json.loads(json.dumps(doc))
    doc_t["bodies"][0]["transform"]["rotation"] = {
        "convention": "matrix_active", "matrix": [[m[j][i] for j in range(3)] for i in range(3)]}
    path_t = tmp_path / "transposed.json"
    path_t.write_text(json.dumps(doc_t), encoding="utf-8")
    wrong = plan_of(path_t).bodies[0].probes
    outside = [pr for pr in wrong if not _inside_box(_local_point(doc, "b", pr.point), (20, 40, 70))]
    assert len(outside) >= 4
