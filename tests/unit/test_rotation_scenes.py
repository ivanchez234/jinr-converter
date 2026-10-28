"""Сцены с поворотами (неделя 26–29.10): ловушка поворотов и коробка 30°/45°.

Все ожидаемые числа считаются здесь своими формулами (cos, sin, умножение матриц),
а не функциями mcscene. Если бы тест брал Rotation из mcscene, ошибка в ней
повторилась бы и в ожидании, и тест бы её не заметил.

Последний блок отвечает на вопрос «а поймает ли стенд?». В Python повторяется то, что
tools/break_matrix.sh делает в C++ (матрица транспонирована, то есть строки и столбцы
перепутаны), и проверяется, что пробные точки этих сцен вылетают из своих тел.
А на повороте ровно на 90° (rotated_box) не вылетают: поэтому и нужны эти сцены.
"""
import json
import math
from itertools import product

import pytest

from mcscene.backends.geant4.plan import Geant4Planner
from mcscene.cli import main
from mcscene.model import Scene
from mcscene.paths import TEST_SCENES

TRAP = TEST_SCENES / "rotation_trap.json"
BOX_EULER = TEST_SCENES / "box_rot30x_45z.json"
BOX_MATRIX = TEST_SCENES / "box_rot30x_45z_matrix.json"
ROTATED_90 = TEST_SCENES / "rotated_box.json"

I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


# --- своя маленькая математика (без mcscene) ---------------------------------------
def rx(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def rz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def transposed(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def close_m(a, b, tol):
    return all(close(ra, rb, tol) for ra, rb in zip(a, b))


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plan_of(path):
    r = Geant4Planner(Scene.model_validate(read(path)), path).build()
    assert r.plan is not None, [d for d in r.diagnostics if d.level == "ERROR"]
    return r.plan


def body_plan(plan, id):
    return next(b for b in plan.bodies if b.id == id)


# --- ловушка поворотов ---------------------------------------------------------------
# world
# └─ A  300×200×100, R1 = Rx(90°), затем Rz(90°), сдвиг (100, 50, 0)
#    └─ B  80×60×30, R2 = Ry(90°), сдвиг (60, 0, 5) в системе A
#       └─ M  10×10×10, без поворота, сдвиг (30, 15, 0) в системе B
R1 = mul(rz(90), rx(90))
R2 = ry(90)
M_CENTER = (75.0, 110.0, 15.0)


def test_trap_marker_center_by_hand():
    p = add(apply(R1, add(apply(R2, [30, 15, 0]), [60, 0, 5])), [100, 50, 0])
    assert close(p, M_CENTER, 1e-9)


def test_trap_marker_probes_in_plan():
    m = body_plan(plan_of(TRAP), "M")
    to_world = mul(R1, R2)                       # у M своего поворота нет
    want = [add(apply(to_world, [sx * 4, sy * 4, sz * 4]), list(M_CENTER))   # 0.4 · 10 мм
            for sx, sy, sz in product((-1, 1), repeat=3)]
    got = [p.point for p in m.probes]
    assert close(got[0], M_CENTER, 1e-9)         # первая точка — центр
    assert len(got) == 9
    for w in want:
        assert any(close(g, w, 1e-9) for g in got), w
    assert {(p.volume, p.material) for p in m.probes} == {("M", "G4_Pb")}


def test_trap_only_marker_has_probes():
    # точки ставятся только в тела без детей: в A и B их место заняли бы дети
    plan = plan_of(TRAP)
    assert [b.id for b in plan.bodies if b.probes] == ["M"]


def test_trap_marker_center_in_expected_checks(tmp_path):
    out = tmp_path / "trap"
    assert main(["generate", str(TRAP), "-o", str(out)]) == 0
    text = (out / "generated" / "ExpectedChecks.hh").read_text(encoding="utf-8")
    assert '{75, 110, 15, "M", "G4_Pb"},' in text


def test_trap_matrices_in_plan():
    plan = plan_of(TRAP)
    assert close_m(body_plan(plan, "A").matrix, R1, 1e-12)
    assert close_m(body_plan(plan, "B").matrix, R2, 1e-12)
    assert body_plan(plan, "M").matrix == tuple(tuple(r) for r in I3)


# --- коробка 20×40×70: 30° вокруг x, затем 45° вокруг z ------------------------------
R_BOX = mul(rz(45), rx(30))
BOX_CENTER = (150.0, -60.0, 40.0)
BOX_HALF = (10.0, 20.0, 35.0)


def test_box_matrix_by_hand():
    # те же числа, что в плане v3.1 (раздел 3), с 4 знаками
    rounded = [[0.7071, -0.6124, 0.3536], [0.7071, 0.6124, -0.3536], [0.0, 0.5, 0.8660]]
    assert close_m(R_BOX, rounded, 1e-4)
    for path in (BOX_EULER, BOX_MATRIX):
        assert close_m(body_plan(plan_of(path), "box").matrix, R_BOX, 1e-12), path.name


def test_box_euler_and_matrix_give_same_plan():
    a = body_plan(plan_of(BOX_EULER), "box")
    b = body_plan(plan_of(BOX_MATRIX), "box")
    assert close_m(a.matrix, b.matrix, 1e-9)
    assert a.translation == b.translation == BOX_CENTER
    assert len(a.probes) == len(b.probes) == 9
    for pa, pb in zip(a.probes, b.probes):
        assert close(pa.point, pb.point, 1e-9)


@pytest.mark.parametrize("path", [BOX_EULER, BOX_MATRIX], ids=lambda p: p.name)
def test_box_verification_by_hand(path):
    v = read(path)["bodies"][0]["verification"]
    assert v["cad_volume"] == 20 * 40 * 70 == 56000
    ext = [sum(abs(R_BOX[i][k]) * BOX_HALF[k] for k in range(3)) for i in range(3)]
    assert close(ext, (31.69, 31.69, 40.31), 0.01)
    lo = [c - e for c, e in zip(BOX_CENTER, ext)]
    hi = [c + e for c, e in zip(BOX_CENTER, ext)]
    assert close(v["bbox"][0], lo, 1e-6) and close(v["bbox"][1], hi, 1e-6)


# --- а поймает ли стенд перепутанную матрицу? ----------------------------------------
def _rotation(raw):
    if raw["convention"] == "identity":
        return I3
    if raw["convention"] == "euler_xyz_extrinsic_deg":
        a, b, c = raw["angles"]
        return mul(rz(c), mul(ry(b), rx(a)))
    return raw["matrix"]                          # matrix_active


def _world_placements(doc, broken):
    """id -> (R, t, половины размеров): где тело стоит в мире.

    broken=True — так, как его поставил бы g4scene с транспонированной матрицей.
    """
    bodies = {b["id"]: b for b in doc["bodies"]}
    out = {}

    def place(id):
        if id in out:
            return out[id]
        b = bodies[id]
        r = _rotation(b["transform"]["rotation"])
        if broken:
            r = transposed(r)
        t = list(b["transform"]["translation"])
        if b["parent"] is not None:
            pr, pt, _ = place(b["parent"])
            r, t = mul(pr, r), add(apply(pr, t), pt)
        out[id] = (r, t, [s / 2 for s in b["shape"]["size"]])
        return out[id]

    for id in bodies:
        place(id)
    return out


def _where(point, doc, placements):
    """Самое глубокое тело, внутри которого точка (как G4Navigator); иначе world."""
    depth = {}
    for b in doc["bodies"]:
        d, p = 0, b["parent"]
        while p is not None:
            d, p = d + 1, next(x["parent"] for x in doc["bodies"] if x["id"] == p)
        depth[b["id"]] = d
    found = "world"
    for id, (r, t, half) in placements.items():
        local = apply(transposed(r), [x - y for x, y in zip(point, t)])
        if all(abs(x) < h for x, h in zip(local, half)):
            if found == "world" or depth[id] > depth[found]:
                found = id
    return found


def misplaced_probes(path, broken):
    """Пробные точки из плана (их же проверяет стенд), которые не попали в своё тело."""
    doc = read(path)
    placements = _world_placements(doc, broken)
    return [(b.id, p.point, _where(p.point, doc, placements))
            for b in plan_of(path).bodies for p in b.probes
            if _where(p.point, doc, placements) != b.id]


@pytest.mark.parametrize("path", [TRAP, BOX_EULER, BOX_MATRIX, ROTATED_90], ids=lambda p: p.name)
def test_correct_matrix_puts_every_probe_in_place(path):
    assert misplaced_probes(path, broken=False) == []


@pytest.mark.parametrize("path", [TRAP, BOX_EULER, BOX_MATRIX], ids=lambda p: p.name)
def test_transposed_matrix_is_caught(path):
    assert misplaced_probes(path, broken=True), "перепутанная матрица не сдвинула ни одной точки"


def test_trap_transposed_marker_lands_outside_a():
    # сломанная сцена: точка (75, 110, 15) в системе A — это (15, -25, 60), а полувысота A — 50
    doc = read(TRAP)
    assert _where(M_CENTER, doc, _world_placements(doc, broken=True)) == "world"


def test_transposed_matrix_not_caught_at_90_degrees():
    # rotated_box: ровно 90° вокруг z. Транспонированная матрица — это −90°, и коробка
    # занимает то же место, так что все точки остаются в ней. Поэтому одних поворотов
    # на 90° мало, и нужны ловушка и коробка 30°/45°.
    assert misplaced_probes(ROTATED_90, broken=True) == []
