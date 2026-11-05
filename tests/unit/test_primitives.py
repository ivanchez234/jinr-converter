"""Примитивы этапа 3 в Geant4: геометрия формы (пробные точки), данные для шаблона, C++.

Ожидаемые числа — свои, не из mcscene. Здесь все примитивы: цилиндр и труба (G4Tubs),
шар (G4Orb), сферическая оболочка (G4Sphere), конус (G4Cons) и тор (G4Torus).
"""
import json
import math

import pytest

from mcscene.backends.geant4.solids import SOLIDS, ConeSolid, SphereSolid, TorusSolid, TubeSolid
from mcscene.cli import main
from mcscene.model import Cone, Cylinder, Sphere, Torus
from mcscene.paths import FREECAD_FIXTURES, TEST_SCENES


def gen(scene, out):
    assert main(["generate", str(scene), "-o", str(out)]) == 0
    return (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")


# --- цилиндр: пробные точки ------------------------------------------------------------
def _in_cylinder(p, radius, height, inner=0.0):
    r = math.hypot(p[0], p[1])
    return abs(p[2]) < height / 2 and r < radius and (inner == 0 or r > inner)


def test_solid_cylinder_probes():
    pts = Cylinder(type="cylinder", radius=40, height=200).probe_points()
    assert pts[0] == (0.0, 0.0, 0.0) and len(pts) == 7
    assert (0.0, 0.0, 80.0) in pts and (0.0, 0.0, -80.0) in pts          # ось, ±0,4·H
    assert (20.0, 0.0, 0.0) in pts and (0.0, -20.0, 0.0) in pts           # 0,5·R
    assert all(_in_cylinder(p, 40, 200) for p in pts)


def test_tube_probes_are_in_the_wall():
    # внутри трубы пусто (там будет ребёнок, например вакуум) — точки только в стенке
    pts = Cylinder(type="cylinder", radius=60, inner_radius=55, height=1000).probe_points()
    assert len(pts) == 6
    assert all(math.isclose(math.hypot(p[0], p[1]), 57.5) for p in pts)
    assert all(_in_cylinder(p, 60, 1000, inner=55) for p in pts)
    assert {p[2] for p in pts} == {0.0, 400.0, -400.0}


# --- цилиндр: данные для шаблона и C++ ------------------------------------------------
def test_tube_solid_gives_numbers_not_cpp():
    s = TubeSolid().solid(Cylinder(type="cylinder", radius=50, inner_radius=40, height=200), "tube")
    assert (s.kind, s.name, s.rmin, s.rmax, s.height, s.half_z) == ("tubs", "tube", 40, 50, 200, 100)
    assert TubeSolid.volume_tol == 1e-6                     # объём G4Tubs Geant4 считает точно
    assert isinstance(SOLIDS["cylinder"], TubeSolid)


def test_cylinder_in_cpp(tmp_path):
    cc = gen(TEST_SCENES / "cylinder_rot.json", tmp_path / "rod")
    assert '#include "G4Tubs.hh"' in cc
    assert '#include "G4Box.hh"' in cc                     # мир — G4Box, даже если коробок нет
    assert "  // цилиндр R 30, высота 120 мм (G4Tubs берёт половину высоты)\n" in cc
    assert '  auto* solid = new G4Tubs("rod", 0*mm, 30*mm, 60*mm, 0*deg, 360*deg);\n' in cc
    assert "углы X, Y, Z = 20°, 50°, 30°" in cc


def test_tube_in_cpp(tmp_path):
    cc = gen(TEST_SCENES / "tube.json", tmp_path / "tube")
    assert "  // труба R 50 / 40, высота 200 мм (G4Tubs берёт половину высоты)\n" in cc
    assert '  auto* solid = new G4Tubs("tube", 40*mm, 50*mm, 100*mm, 0*deg, 360*deg);\n' in cc
    assert "оси тела в системе родителя (столбцы матрицы): x -> -z, y -> +y, z -> +x" in cc


# --- цилиндр Никиты: R 40, H 200, ось вдоль +X ----------------------------------------
def test_nikita_cylinder_probes_in_world(tmp_path):
    out = tmp_path / "cyl"
    gen(FREECAD_FIXTURES / "04_cylinder_y90" / "scene.json", out)
    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    # центр (100, 0, 0); на оси при ±0,4·H = ±80 вдоль x; 0,5·R = 20 поперёк оси
    for p in ("{100, 0, 0,", "{180, 0, 0,", "{20, 0, 0,", "{100, 20, 0,", "{100, 0, -20,"):
        assert p + ' "Cylinder", "G4_Fe"},' in checks, p
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["bodies"][0]["cad_volume_mm3"] == pytest.approx(math.pi * 40 ** 2 * 200)


# --- а поймает ли стенд перепутанную матрицу у цилиндра? ---------------------------------
def _rot(angles):
    a, b, c = (math.radians(x) for x in angles)
    rx = [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
    ry = [[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]]
    rz = [[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]]
    mul = lambda p, q: [[sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(rz, mul(ry, rx))


def test_transposed_matrix_moves_cylinder_probes():
    # стержень cylinder_rot.json, поставленный с Rᵀ вместо R: точки на оси уходят из него
    doc = json.loads((TEST_SCENES / "cylinder_rot.json").read_text("utf-8"))
    b = doc["bodies"][0]
    r = _rot(b["transform"]["rotation"]["angles"])
    c = b["transform"]["translation"]
    shape = Cylinder.from_dict(b["shape"])
    world = [[sum(r[i][k] * p[k] for k in range(3)) + c[i] for i in range(3)] for p in shape.probe_points()]
    # где эти точки в системе цилиндра, поставленного с Rᵀ: local = (Rᵀ)ᵀ·(q − c) = R·(q − c)
    local = [[sum(r[i][k] * (q[k] - c[k]) for k in range(3)) for i in range(3)] for q in world]
    outside = [p for p in local if not _in_cylinder(p, shape.radius, shape.height)]
    assert len(outside) >= 2


# --- сфера: пробные точки ---------------------------------------------------------------
def _in_sphere(p, radius, inner=0.0):
    r = math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
    return r < radius and (inner == 0 or r > inner)


def test_solid_sphere_probes():
    pts = Sphere(type="sphere", radius=50).probe_points()
    assert pts[0] == (0.0, 0.0, 0.0) and len(pts) == 7
    assert {(25.0, 0.0, 0.0), (-25.0, 0.0, 0.0), (0.0, 25.0, 0.0), (0.0, 0.0, -25.0)} <= set(pts)
    assert all(_in_sphere(p, 50) for p in pts)


def test_hollow_sphere_probes_are_in_the_wall():
    # центр оболочки пустой — точки только в стенке, на r = (40 + 50) / 2 = 45
    pts = Sphere(type="sphere", radius=50, inner_radius=40).probe_points()
    assert len(pts) == 6 and (0.0, 0.0, 0.0) not in pts
    assert all(math.isclose(math.sqrt(sum(c * c for c in p)), 45) for p in pts)
    assert all(_in_sphere(p, 50, inner=40) for p in pts)


# --- сфера: данные для шаблона и C++ ----------------------------------------------------
def test_sphere_solid_picks_orb_or_sphere():
    ball = SphereSolid().solid(Sphere(type="sphere", radius=25), "ball")
    assert (ball.kind, ball.name, ball.radius) == ("orb", "ball", 25)
    shell = SphereSolid().solid(Sphere(type="sphere", radius=50, inner_radius=40), "shell")
    assert (shell.kind, shell.name, shell.rmin, shell.rmax) == ("sphere", "shell", 40, 50)
    assert isinstance(SOLIDS["sphere"], SphereSolid)


def test_spheres_in_cpp(tmp_path):
    cc = gen(TEST_SCENES / "spheres.json", tmp_path / "spheres")
    assert '#include "G4Orb.hh"' in cc and '#include "G4Sphere.hh"' in cc and '#include "G4Box.hh"' in cc
    assert "  // шар R 25 мм (G4Orb)\n" in cc
    assert '  auto* solid = new G4Orb("ball", 25*mm);\n' in cc
    assert "  // полый шар R 50 / 40 мм (G4Sphere, полный по обоим углам)\n" in cc
    assert '  auto* solid = new G4Sphere("shell", 40*mm, 50*mm, 0*deg, 360*deg, 0*deg, 180*deg);\n' in cc
    assert "G4Tubs" not in cc


def test_only_needed_headers(tmp_path):
    # у сцены только с шаром нет ни G4Tubs, ни G4Sphere
    cc = gen(FREECAD_FIXTURES / "05_sphere" / "scene.json", tmp_path / "ball")
    solids = {'#include "G4Orb.hh"', '#include "G4Sphere.hh"', '#include "G4Tubs.hh"'}
    assert [line for line in cc.splitlines() if line in solids] == ['#include "G4Orb.hh"']


# --- сфера Никиты: R 50 в начале координат -----------------------------------------------
def test_nikita_sphere(tmp_path):
    out = tmp_path / "sphere"
    cc = gen(FREECAD_FIXTURES / "05_sphere" / "scene.json", out)
    assert '  auto* solid = new G4Orb("Sphere", 50*mm);\n' in cc
    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    for p in ("{0, 0, 0,", "{25, 0, 0,", "{0, -25, 0,", "{0, 0, 25,"):
        assert p + ' "Sphere", "G4_Fe"},' in checks, p
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["bodies"][0]["cad_volume_mm3"] == pytest.approx(4 / 3 * math.pi * 50 ** 3)


# --- конус: пробные точки ---------------------------------------------------------------
def _in_cone(p, rb, rt, h, ib=0.0, it=0.0):
    """Точка внутри конуса: низ (rb, ib) при z = -h/2, верх (rt, it) при z = +h/2."""
    f = p[2] / h + 0.5
    r = math.hypot(p[0], p[1])
    return (abs(p[2]) < h / 2 and r < rb + (rt - rb) * f
            and (ib == it == 0 or r > ib + (it - ib) * f))


def test_sharp_cone_probes():
    # конус Никиты: низ R 40, верх 0, H 100; радиус на высоте z = 20 − 0,4·z
    pts = Cone(type="cone", radius_bottom=40, radius_top=0, height=100).probe_points()
    assert len(pts) == 9 and pts[0] == (0.0, 0.0, 0.0)
    assert (0.0, 0.0, 40.0) in pts and (0.0, 0.0, -40.0) in pts          # ось, ±0,4·H — и у острия
    assert (10.0, 0.0, 0.0) in pts and (0.0, -10.0, 0.0) in pts           # 0,5·R(0) = 0,5·20
    assert (27.0, 0.0, -40.0) in pts                                      # у низа: 0,75·R(−40) = 0,75·36
    assert any(math.isclose(p[1], 3.0) and p[2] == 40.0 for p in pts)    # у острия: 0,75·R(40) = 0,75·4
    assert all(_in_cone(p, 40, 0, 100) for p in pts)


def test_hollow_cone_probes_are_in_the_wall():
    # воронка: низ R 60 / 50, верх R 30 / 20, H 100; при z = 0 стенка от 35 до 45, середина — 40
    cone = Cone(type="cone", radius_bottom=60, radius_top=30, height=100,
                inner_radius_bottom=50, inner_radius_top=20)
    pts = cone.probe_points()
    assert len(pts) == 6 and (0.0, 0.0, 0.0) not in pts
    assert (40.0, 0.0, 0.0) in pts and (0.0, -40.0, 0.0) in pts
    assert any(math.isclose(p[0], 52.0) and p[2] == -40.0 for p in pts)   # у низа: (47 + 57) / 2
    assert any(math.isclose(p[0], -28.0) and p[2] == 40.0 for p in pts)   # у верха: (23 + 33) / 2
    assert all(_in_cone(p, 60, 30, 100, ib=50, it=20) for p in pts)


@pytest.mark.parametrize("rb, rt, h, ib, it", [(40, 0, 100, 0, 0),       # конус Никиты, острый
                                               (50, 20, 120, 0, 0),      # усечённый, cones.json
                                               (60, 30, 100, 50, 20)])   # воронка, cones.json
def test_swapped_bottom_and_top_moves_probes_out(rb, rt, h, ib, it):
    # «перепутать у G4Cons низ и верх»: Geant4 построит конус с rb <-> rt — часть точек окажется снаружи
    pts = Cone(type="cone", radius_bottom=rb, radius_top=rt, height=h,
               inner_radius_bottom=ib, inner_radius_top=it).probe_points()
    assert all(_in_cone(p, rb, rt, h, ib, it) for p in pts)
    assert any(not _in_cone(p, rt, rb, h, it, ib) for p in pts)


# --- конус: данные для шаблона и C++ ----------------------------------------------------
def test_cone_solid_keeps_bottom_and_top():
    s = ConeSolid().solid(Cone(type="cone", radius_bottom=60, radius_top=30, height=100,
                               inner_radius_bottom=50, inner_radius_top=20), "funnel")
    assert (s.kind, s.name) == ("cons", "funnel")
    assert (s.rmin_bottom, s.rmax_bottom, s.rmin_top, s.rmax_top) == (50, 60, 20, 30)
    assert (s.height, s.half_z) == (100, 50)
    assert isinstance(SOLIDS["cone"], ConeSolid)


def test_cones_in_cpp(tmp_path):
    cc = gen(TEST_SCENES / "cones.json", tmp_path / "cones")
    assert '#include "G4Cons.hh"' in cc
    assert ("  // конус: низ R 50, верх R 20, высота 120 мм"
            " (G4Cons: сначала низ при z = −H/2, берёт половину высоты)\n") in cc
    assert '  auto* solid = new G4Cons("frustum", 0*mm, 50*mm, 0*mm, 20*mm, 60*mm, 0*deg, 360*deg);\n' in cc
    assert "  // полый конус: низ R 60 / 50, верх R 30 / 20, высота 100 мм" in cc
    assert '  auto* solid = new G4Cons("funnel", 50*mm, 60*mm, 20*mm, 30*mm, 50*mm, 0*deg, 360*deg);\n' in cc


# --- конус Никиты: острый, R 40 -> 0, H 100, 20° вокруг X и 35° вокруг Z ---------------------
def test_nikita_cone(tmp_path):
    out = tmp_path / "cone"
    cc = gen(FREECAD_FIXTURES / "06_cone" / "scene.json", out)
    assert '  auto* solid = new G4Cons("Cone", 0*mm, 40*mm, 0*mm, 0*mm, 50*mm, 0*deg, 360*deg);\n' in cc
    doc = json.loads((FREECAD_FIXTURES / "06_cone" / "scene.json").read_text("utf-8"))
    t = doc["bodies"][0]["transform"]
    m, c = t["rotation"]["matrix"], t["translation"]
    assert max(abs(m[i][j] - _rot((20, 0, 35))[i][j]) for i in range(3) for j in range(3)) < 1e-12
    # точка на оси у острия: центр + 40 мм вдоль оси конуса (третий столбец матрицы)
    tip = [c[i] + 40 * m[i][2] for i in range(3)]
    plan = json.loads((out / "report.json").read_text("utf-8"))
    assert plan["bodies"][0]["probes"] == 9
    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    row = [line for line in checks.splitlines() if line.strip().startswith("{") and '"G4_Fe"' in line]
    got = [[float(x) for x in line.strip()[1:].split(",")[:3]] for line in row]
    assert any(max(abs(g[i] - tip[i]) for i in range(3)) < 1e-6 for g in got), (tip, got)
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["bodies"][0]["cad_volume_mm3"] == pytest.approx(math.pi * 100 / 3 * 40 ** 2)


# --- тор: пробные точки -----------------------------------------------------------------
def _in_torus(p, big, small):
    return math.hypot(math.hypot(p[0], p[1]) - big, p[2]) < small


def test_torus_probes_are_in_the_tube():
    pts = Torus(type="torus", major_radius=100, minor_radius=20).probe_points()
    assert len(pts) == 8 and (0.0, 0.0, 0.0) not in pts                  # центр тора — дырка
    assert {(100.0, 0.0, 0.0), (-100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, -100.0, 0.0)} <= set(pts)
    assert {(110.0, 0.0, 0.0), (0.0, 90.0, 0.0), (-100.0, 0.0, 10.0), (0.0, -100.0, -10.0)} <= set(pts)
    assert all(_in_torus(p, 100, 20) for p in pts)


# --- тор: данные для шаблона и C++ ------------------------------------------------------
def test_torus_solid_gives_numbers_not_cpp():
    s = TorusSolid().solid(Torus(type="torus", major_radius=100, minor_radius=20), "ring")
    assert (s.kind, s.name, s.rmin, s.rmax, s.rtor) == ("torus", "ring", 0, 20, 100)
    assert isinstance(SOLIDS["torus"], TorusSolid)


def test_torus_in_cpp(tmp_path):
    cc = gen(TEST_SCENES / "torus_ball.json", tmp_path / "torus")
    assert '#include "G4Torus.hh"' in cc and '#include "G4Orb.hh"' in cc
    assert "  // тор R 100, трубка r 20 мм (G4Torus: сначала радиусы трубки, потом R)\n" in cc
    assert '  auto* solid = new G4Torus("ring", 0*mm, 20*mm, 100*mm, 0*deg, 360*deg);\n' in cc


# --- тор Никиты: R 100, r 20, 35° вокруг X и 15° вокруг Z ----------------------------------
def test_nikita_torus(tmp_path):
    out = tmp_path / "torus"
    cc = gen(FREECAD_FIXTURES / "07_torus" / "scene.json", out)
    assert '  auto* solid = new G4Torus("Torus", 0*mm, 20*mm, 100*mm, 0*deg, 360*deg);\n' in cc
    m = json.loads((FREECAD_FIXTURES / "07_torus" / "scene.json").read_text("utf-8")
                   )["bodies"][0]["transform"]["rotation"]["matrix"]
    assert max(abs(m[i][j] - _rot((35, 0, 15))[i][j]) for i in range(3) for j in range(3)) < 1e-12
    # точка (100, 0, 0) на осевой окружности трубки -> в мире 100 · (первый столбец матрицы)
    want = [100 * m[i][0] for i in range(3)]
    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    rows = [line for line in checks.splitlines() if line.strip().startswith("{") and '"G4_Fe"' in line]
    got = [[float(x) for x in line.strip()[1:].split(",")[:3]] for line in rows]
    assert len(got) == 8
    assert any(max(abs(g[i] - want[i]) for i in range(3)) < 1e-6 for g in got), (want, got)
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["bodies"][0]["cad_volume_mm3"] == pytest.approx(2 * math.pi ** 2 * 100 * 20 ** 2)


def test_transposed_matrix_moves_torus_probes():
    # тор Никиты, поставленный с Rᵀ вместо R: плоскость трубки наклоняется, точки выходят из неё
    b = json.loads((FREECAD_FIXTURES / "07_torus" / "scene.json").read_text("utf-8"))["bodies"][0]
    r, c = b["transform"]["rotation"]["matrix"], b["transform"]["translation"]
    shape = Torus.from_dict(b["shape"])
    world = [[sum(r[i][k] * p[k] for k in range(3)) + c[i] for i in range(3)] for p in shape.probe_points()]
    local = [[sum(r[i][k] * (q[k] - c[k]) for k in range(3)) for i in range(3)] for q in world]
    outside = [p for p in local if not _in_torus(p, shape.major_radius, shape.minor_radius)]
    assert len(outside) >= 2
