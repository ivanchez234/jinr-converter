"""Повороты (объект Rotation, жёсткое преобразование Rigid): соглашения контракта и совпадение с validate.py."""
import json
import math

import pytest

from mcscene.io.contract import load_contract_validator
from mcscene.model import RotEuler, RotIdentity, RotMatrix, Scene
from mcscene.geometry import IDENTITY, Rigid, Rotation
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES, all_test_scenes, scene_id

GOOD = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()


def euler(a, b, c):
    return Rotation.from_contract(RotEuler(convention="euler_xyz_extrinsic_deg", angles=(a, b, c)))


def from_json(rot):
    return Rotation.from_contract(rot).matrix


def close(u, v, tol=1e-12):
    return all(abs(x - y) <= tol for x, y in zip(u, v))


def test_identity():
    assert from_json(RotIdentity(convention="identity")) == IDENTITY
    assert from_json(None) == IDENTITY
    assert Rotation().is_identity and not euler(0, 0, 90).is_identity


def test_euler_z90_turns_x_into_y():
    m = euler(0, 0, 90)
    assert m.matrix == ((0, -1, 0), (1, 0, 0), (0, 0, 1))
    assert m.apply((1, 0, 0)) == (0, 1, 0)


def test_euler_x90_turns_y_into_z():
    assert euler(90, 0, 0).apply((0, 1, 0)) == (0, 0, 1)


def test_euler_order_is_x_then_y_then_z():
    # R = Rz·Ry·Rx: сначала X на 90°, потом Z на 90°.
    # x -> (Rx) x -> (Rz) y;   y -> (Rx) z -> (Rz) z.
    # При обратном порядке (Rx·Rz) x ушёл бы в z, и тест бы упал.
    m = euler(90, 0, 90)
    assert m.matrix == ((0, 0, 1), (1, 0, 0), (0, 1, 0))
    assert m.apply((1, 0, 0)) == (0, 1, 0)
    assert m.apply((0, 1, 0)) == (0, 0, 1)


def test_composition_applies_right_first():
    # (A @ B).apply(p) == A.apply(B.apply(p)): сначала B, потом A
    a, b, p = euler(0, 0, 90), euler(90, 0, 0), (1, 2, 3)
    assert close((a @ b).apply(p), a.apply(b.apply(p)))
    assert (a @ b).matrix == euler(90, 0, 90).matrix          # Rz·Rx — то же, что углы (90, 0, 90)


def test_operations_return_new_objects():
    r = euler(30, -45, 70)
    before = r.matrix
    r.transposed(), r.orthonormalized(), r.snapped(), r @ r
    assert r.matrix == before                                 # объект-значение не меняется


def test_snap_leaves_no_noise():
    for angles in [(0, 0, 90), (90, 0, 0), (0, 180, 0), (90, 90, 90), (0, 0, -90)]:
        for x in sum(euler(*angles).matrix, ()):
            assert x in (-1.0, 0.0, 1.0), (angles, x)
            assert math.copysign(1.0, x) == 1.0 or x != 0.0      # нет -0.0


def test_matrix_active_is_taken_as_is_but_snapped():
    m = from_json(RotMatrix(convention="matrix_active",
                            matrix=((0, 0, 0.9999999999999998), (0, 1, 0), (-1, 2e-16, 0))))
    assert m == ((0, 0, 1), (0, 1, 0), (-1, 0, 0))


def test_arbitrary_angles_give_proper_rotation():
    m = euler(30, -45, 70)
    assert close(sum((m @ m.transposed()).matrix, ()), sum(IDENTITY, ()), 1e-12)
    assert abs(m.det - 1) < 1e-12
    assert not m.is_axis_permutation
    assert euler(90, 0, 90).is_axis_permutation


def test_rounded_matrix_is_made_exactly_orthonormal():
    # Rz(30°), записанная с 7 знаками: validate.py это пропустит (отклонение < 1e-6),
    # а g4scene требует 1e-9 — генератор должен довести матрицу сам.
    c, s = 0.8660254, 0.5
    rough = ((c, -s, 0), (s, c, 0), (0, 0, 1))
    assert 1e-9 < Rotation.of(rough).deviation < 1e-6
    m = Rotation.from_contract(RotMatrix(convention="matrix_active", matrix=rough))
    assert m.deviation < 1e-15
    assert close(sum(m.matrix, ()), sum(rough, ()), 1e-7)        # почти не сдвинулась
    assert abs(m.det - 1) < 1e-15


def test_orthonormalize_keeps_exact_matrices():
    for m in [Rotation(), Rotation.of(((0, -1, 0), (1, 0, 0), (0, 0, 1))), euler(30, -45, 70)]:
        assert close(sum(m.orthonormalized().matrix, ()), sum(m.matrix, ()), 1e-15)


@pytest.mark.parametrize("path", GOOD, ids=scene_id)
def test_every_matrix_passes_g4scene_check(path):
    # g4scene::RotationProblem в C++ требует отклонение не больше 1e-9
    for where, _, tf in _all_transforms(path):
        m = Rotation.from_contract(tf.rotation)
        assert m.deviation < 1e-12 and m.det > 0, where


def test_rotated_box_scene_matrix():
    with open(TEST_SCENES / "rotated_box.json", encoding="utf-8") as f:
        scene = Scene.model_validate(json.load(f))
    assert from_json(scene.bodies[0].transform.rotation) == ((0, -1, 0), (1, 0, 0), (0, 0, 1))


def test_rigid_child_inside_rotated_parent():
    parent = Rigid(euler(0, 0, 90), (100, 0, 0))
    child = Rigid(Rotation(), (10, 0, 0))
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
        ours = from_json(tf.rotation)
        assert close(sum(ours, ()), [x for row in ref for x in row], 1e-12), where
        n += 1
    assert n >= 1
