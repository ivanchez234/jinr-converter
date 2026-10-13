"""Повороты: соглашения контракта и совпадение с validate.py."""
import json
import math

import pytest

from mcscene.io.contract import load_contract_validator
from mcscene.model import RotEuler, RotIdentity, RotMatrix, Scene
from mcscene.passes.rotations import (IDENTITY, Rigid, apply, det, deviation, is_axis_permutation,
                                      mul, orthonormalize, to_matrix, transpose)
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES, all_test_scenes, scene_id

GOOD = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()


def euler(a, b, c):
    return to_matrix(RotEuler(convention="euler_xyz_extrinsic_deg", angles=(a, b, c)))


def close(u, v, tol=1e-12):
    return all(abs(x - y) <= tol for x, y in zip(u, v))


def test_identity():
    assert to_matrix(RotIdentity(convention="identity")) == IDENTITY
    assert to_matrix(None) == IDENTITY


def test_euler_z90_turns_x_into_y():
    m = euler(0, 0, 90)
    assert m == ((0, -1, 0), (1, 0, 0), (0, 0, 1))
    assert apply(m, (1, 0, 0)) == (0, 1, 0)


def test_euler_x90_turns_y_into_z():
    assert apply(euler(90, 0, 0), (0, 1, 0)) == (0, 0, 1)


def test_euler_order_is_x_then_y_then_z():
    # R = Rz·Ry·Rx: сначала X на 90°, потом Z на 90°.
    # x -> (Rx) x -> (Rz) y;   y -> (Rx) z -> (Rz) z.
    # При обратном порядке (Rx·Rz) x ушёл бы в z, и тест бы упал.
    m = euler(90, 0, 90)
    assert m == ((0, 0, 1), (1, 0, 0), (0, 1, 0))
    assert apply(m, (1, 0, 0)) == (0, 1, 0)
    assert apply(m, (0, 1, 0)) == (0, 0, 1)


def test_snap_leaves_no_noise():
    for angles in [(0, 0, 90), (90, 0, 0), (0, 180, 0), (90, 90, 90), (0, 0, -90)]:
        for x in sum(euler(*angles), ()):
            assert x in (-1.0, 0.0, 1.0), (angles, x)
            assert math.copysign(1.0, x) == 1.0 or x != 0.0      # нет -0.0


def test_matrix_active_is_taken_as_is_but_snapped():
    m = to_matrix(RotMatrix(convention="matrix_active",
                            matrix=((0, 0, 0.9999999999999998), (0, 1, 0), (-1, 2e-16, 0))))
    assert m == ((0, 0, 1), (0, 1, 0), (-1, 0, 0))


def test_arbitrary_angles_give_proper_rotation():
    m = euler(30, -45, 70)
    assert close(sum(mul(m, transpose(m)), ()), sum(IDENTITY, ()), 1e-12)
    assert abs(det(m) - 1) < 1e-12
    assert not is_axis_permutation(m)
    assert is_axis_permutation(euler(90, 0, 90))


def test_rounded_matrix_is_made_exactly_orthonormal():
    # Rz(30°), записанная с 7 знаками: validate.py это пропустит (отклонение < 1e-6),
    # а g4scene требует 1e-9 — генератор должен довести матрицу сам.
    c, s = 0.8660254, 0.5
    rough = ((c, -s, 0), (s, c, 0), (0, 0, 1))
    assert 1e-9 < deviation(rough) < 1e-6
    m = to_matrix(RotMatrix(convention="matrix_active", matrix=rough))
    assert deviation(m) < 1e-15
    assert close(sum(m, ()), sum(rough, ()), 1e-7)               # почти не сдвинулась
    assert abs(det(m) - 1) < 1e-15


def test_orthonormalize_keeps_exact_matrices():
    for m in [IDENTITY, ((0, -1, 0), (1, 0, 0), (0, 0, 1)), euler(30, -45, 70)]:
        assert close(sum(orthonormalize(m), ()), sum(m, ()), 1e-15)


@pytest.mark.parametrize("path", GOOD, ids=scene_id)
def test_every_matrix_passes_g4scene_check(path):
    # g4scene::RotationProblem в C++ требует отклонение не больше 1e-9
    for where, _, tf in _all_transforms(path):
        m = to_matrix(tf.rotation)
        assert deviation(m) < 1e-12 and det(m) > 0, where


def test_rotated_box_scene_matrix():
    with open(TEST_SCENES / "rotated_box.json", encoding="utf-8") as f:
        scene = Scene.model_validate(json.load(f))
    assert to_matrix(scene.bodies[0].transform.rotation) == ((0, -1, 0), (1, 0, 0), (0, 0, 1))


def test_rigid_child_inside_rotated_parent():
    parent = Rigid(euler(0, 0, 90), (100, 0, 0))
    child = Rigid(IDENTITY, (10, 0, 0))
    world = parent.then_child(child)
    assert world.apply((0, 0, 0)) == (100, 10, 0)            # сдвиг ребёнка тоже повёрнут
    p = (1, 2, 3)
    assert close(world.apply(p), parent.apply(child.apply(p)))


# --- сверка с validate.py на всех поворотах во всех хороших сценах ---
def _pairs(raw_tf, tf, where):
    yield where, raw_tf, tf


def _shape_pairs(raw, shape, where):
    if raw.get("transform") is not None:
        yield where + "/transform", raw["transform"], shape.transform
    if raw["type"] == "boolean":
        yield from _shape_pairs(raw["left"], shape.left, where + "/left")
        yield from _shape_pairs(raw["right"], shape.right, where + "/right")


def _all_transforms(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    scene = Scene.model_validate(doc)
    for raw_b, b in zip(doc["bodies"], scene.bodies):
        yield "%s/transform" % b.id, raw_b["transform"], b.transform
        yield from _shape_pairs(raw_b["shape"], b.shape, "%s/shape" % b.id)


@pytest.mark.parametrize("path", GOOD, ids=scene_id)
def test_same_matrices_as_validate_py(path):
    V = load_contract_validator()
    n = 0
    for where, raw_tf, tf in _all_transforms(path):
        ref = V.rotation_matrix(raw_tf["rotation"])
        ours = to_matrix(tf.rotation)
        assert close(sum(ours, ()), [x for row in ref for x in row], 1e-12), where
        n += 1
    assert n >= 1
