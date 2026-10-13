"""Габаритные коробки форм: формулы против того, что посчитал FreeCAD."""
import json

import pytest

from mcscene.model import Scene
from mcscene.passes.bbox import body_bbox_from_shape, local_bbox
from mcscene.passes.rotations import is_axis_permutation, to_matrix
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES, scene_id

ID = {"convention": "identity"}


def shape(d):
    """Форма из словаря через модель тела (так проверяются и дискриминаторы)."""
    body = {"id": "b", "parent": None, "material": "iron",
            "transform": {"translation": [0, 0, 0], "rotation": ID},
            "shape": d, "verification": {"cad_volume": 1}}
    doc = {"format": "jinr-mc-scene", "format_version": "0.1",
           "units": {"length": "mm", "angle": "deg", "density": "g/cm3"},
           "world": {"material": "iron"}, "materials": [{"id": "iron", "nist": "G4_Fe"}],
           "bodies": [body]}
    return Scene.model_validate(doc).bodies[0].shape


@pytest.mark.parametrize("d, expected", [
    ({"type": "box", "size": [20, 40, 70]}, ((-10, -20, -35), (10, 20, 35))),
    ({"type": "cylinder", "radius": 60, "height": 200}, ((-60, -60, -100), (60, 60, 100))),
    ({"type": "cylinder", "radius": 60, "height": 200, "inner_radius": 55},
     ((-60, -60, -100), (60, 60, 100))),
    ({"type": "cone", "radius_bottom": 50, "radius_top": 0, "height": 300},
     ((-50, -50, -150), (50, 50, 150))),
    ({"type": "cone", "radius_bottom": 10, "radius_top": 80, "height": 40},
     ((-80, -80, -20), (80, 80, 20))),
    ({"type": "sphere", "radius": 30}, ((-30, -30, -30), (30, 30, 30))),
    ({"type": "torus", "major_radius": 100, "minor_radius": 10},
     ((-110, -110, -10), (110, 110, 10))),
], ids=["box", "cylinder", "tube", "sharp-cone", "cone-wide-top", "sphere", "torus"])
def test_local_bbox_of_primitives(d, expected):
    assert local_bbox(shape(d)) == expected


def _box_at(size, t):
    return {"type": "box", "size": size,
            "transform": {"translation": t, "rotation": ID}}


def test_boolean_union_is_hull_of_operands():
    s = shape({"type": "boolean", "op": "union",
               "left": {"type": "box", "size": [10, 10, 10]},
               "right": _box_at([10, 10, 10], [8, 0, 0])})
    assert local_bbox(s) == ((-5, -5, -5), (13, 5, 5))


def test_boolean_subtract_is_left_operand():
    s = shape({"type": "boolean", "op": "subtract",
               "left": {"type": "box", "size": [10, 10, 10]},
               "right": _box_at([4, 4, 40], [0, 0, 0])})
    assert local_bbox(s) == ((-5, -5, -5), (5, 5, 5))


def test_boolean_intersect_is_overlap_of_operands():
    s = shape({"type": "boolean", "op": "intersect",
               "left": {"type": "box", "size": [10, 10, 10]},
               "right": _box_at([10, 10, 10], [6, 0, 0])})
    assert local_bbox(s) == ((1, -5, -5), (5, 5, 5))


def test_rotated_operand():
    # цилиндр вдоль z, повёрнутый так, что его ось легла вдоль x
    s = shape({"type": "boolean", "op": "union",
               "left": {"type": "box", "size": [2, 2, 2]},
               "right": {"type": "cylinder", "radius": 1, "height": 40,
                         "transform": {"translation": [0, 0, 0],
                                       "rotation": {"convention": "euler_xyz_extrinsic_deg",
                                                    "angles": [0, 90, 0]}}}})
    assert local_bbox(s) == ((-20, -1, -1), (20, 1, 1))


def test_mesh_has_no_bbox_without_stl():
    s = shape({"type": "mesh", "uri": "meshes/x.stl", "encoding": "stl-binary",
               "sha256": "0" * 64, "n_facets": 4, "fallback_reason": "USER_FORCED"})
    assert local_bbox(s) is None


# --- формулы против verification.bbox в примерах контракта и ручных сценах ---
SCENES = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + sorted(TEST_SCENES.glob("*.json"))


def _cases():
    for path in SCENES:
        with open(path, encoding="utf-8") as f:
            scene = Scene.model_validate(json.load(f))
        for b in scene.bodies:
            if b.verification.bbox is None or b.shape.type == "mesh":
                continue
            if not is_axis_permutation(to_matrix(b.transform.rotation)):
                continue      # у наклонных круглых фигур коробка по углам шире настоящей
            yield pytest.param(b, id="%s:%s" % (scene_id(path), b.id))


@pytest.mark.parametrize("body", list(_cases()))
def test_bbox_from_shape_matches_freecad(body):
    ours = body_bbox_from_shape(body)
    ref = body.verification.bbox
    for i in range(2):
        for k in range(3):
            assert abs(ours[i][k] - ref[i][k]) < 1e-3, (ours, ref)
