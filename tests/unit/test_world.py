"""Размер мира (проход WorldPass)."""
import json

import pytest

from mcscene.diagnostics import Diagnostics
from mcscene.model import Scene
from mcscene.passes import WorldPass
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES, TEST_SCENES


def run(p, scene):
    """Проход над сценой -> (результат, сообщения)."""
    diags = Diagnostics()
    return p.run(scene, diags), diags


def load(path):
    with open(path, encoding="utf-8") as f:
        return Scene.model_validate(json.load(f))


CUBE_BBOX = ((-25, -25, 0), (25, 25, 50))


def test_cube_from_plan(scene, box):
    # первый юнит-тест из плана: куб 50 мм, стоящий на z = 0
    w, diags = run(WorldPass(), scene(box("Body", (50, 50, 50), (0, 0, 25), bbox=CUBE_BBOX)))
    assert diags == []
    assert w.half_size == (27.5, 27.5, 55.0)          # ровно, без 27.500000000000004
    assert w.extent == CUBE_BBOX
    assert w.material == "air"


def test_without_verification_bbox_size_comes_from_shape(scene, box):
    w, _ = run(WorldPass(), scene(box("Body", (50, 50, 50), (0, 0, 25))))
    assert w.half_size == (27.5, 27.5, 55.0)


def test_margin_zero_world_touches_bodies(scene, box):
    w, _ = run(WorldPass(), scene(box("Body", (50, 50, 50), (0, 0, 25)), margin=0))
    assert w.half_size == (25, 25, 50)


def test_fixture_02_box_20x40x70():
    # bbox [300, -150, 80]..[320, -110, 150] -> max |x|, |y|, |z| = 320, 150, 150
    w, diags = run(WorldPass(), load(FREECAD_FIXTURES / "02_box_20x40x70" / "scene.json"))
    assert diags == []
    assert w.half_size == (352.0, 165.0, 165.0)


def test_rotated_box_bbox_from_shape(scene, box):
    # 20×40×70, поворот 90° вокруг z: в мире 40×20×70 вокруг (300, -150, 80)
    rot = {"convention": "euler_xyz_extrinsic_deg", "angles": [0, 0, 90]}
    w, _ = run(WorldPass(), scene(box("b", (20, 40, 70), (300, -150, 80), rotation=rot)))
    assert w.extent == ((280, -160, 45), (320, -140, 115))
    assert w.half_size == (352.0, 176.0, 126.5)


def test_children_do_not_change_world():
    w, _ = run(WorldPass(), load(TEST_SCENES / "nested_boxes.json"))
    assert w.extent == ((-200, -150, 0), (200, 150, 200))   # только внешний блок
    assert w.half_size == (220.0, 165.0, 220.0)


def test_several_root_bodies(scene, box):
    w, _ = run(WorldPass(), scene(box("a", (10, 10, 10), (-100, 0, 0)),
                            box("b", (10, 10, 10), (0, 0, 300))))
    assert w.extent == ((-105, -5, -5), (5, 5, 305))
    assert w.half_size == (115.5, 5.5, 335.5)


def test_all_types_example():
    # корневые тела: стена, труба, коллиматор, ярмо-меш (у меша bbox из verification)
    w, diags = run(WorldPass(), load(CONTRACT_V0_1 / "examples" / "05_hall_all_types.json"))
    assert diags == []
    assert w.half_size == (2200.0, 1650.0, 1100.55)


def test_mesh_without_bbox_is_an_error_but_others_count():
    doc = json.loads((CONTRACT_V0_1 / "examples" / "05_hall_all_types.json").read_text("utf-8"))
    for b in doc["bodies"]:
        if b["shape"]["type"] == "mesh":
            del b["verification"]["bbox"]
    w, diags = run(WorldPass(), Scene.model_validate(doc))
    assert [d.code for d in diags] == ["E330"]
    assert diags[0].body_id == "magnet_yoke"
    assert w.half_size == (2200.0, 1650.0, 1100.0)          # без ярма


KUB = TEST_SCENES / "kub.json"


@pytest.mark.skipif(not KUB.exists(), reason="kub.json Никиты не положен в tests/scenes")
def test_nikita_cube():
    w, diags = run(WorldPass(), load(KUB))
    assert diags == []
    assert w.half_size == (27.5, 27.5, 55.0)
