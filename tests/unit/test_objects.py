"""Объекты этапа 2.7: сборщик сообщений, фигуры, загрузчик сцены, планировщик."""
import pytest

from mcscene.backends.base import Action
from mcscene.backends.geant4.capabilities import PLANNED, SHAPES
from mcscene.backends.geant4.solids import SOLIDS, BoxSolid, SolidEmitter
from mcscene.diagnostics import Diagnostic, Diagnostics
from mcscene.io.load import SceneLoader, load_and_validate
from mcscene.model import Box, Cylinder
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES


# --- Diagnostics -------------------------------------------------------------------
def test_diagnostics_collects_messages():
    d = Diagnostics()
    d.info("I402", "materials/lead", "не используется")
    assert not d.has_errors
    d.error("E330", "bodies/yoke/verification/bbox", "нет bbox", body_id="yoke")
    d.warn("W100", "/x", "неизвестное поле")
    assert d.has_errors and [x.level for x in d] == ["INFO", "ERROR", "WARN"]
    assert d[1] == Diagnostic("ERROR", "E330", "bodies/yoke/verification/bbox", "нет bbox", body_id="yoke")
    assert Diagnostics() == []                                # это обычный список


# --- фигуры: геометрия у формы, запись у цели ------------------------------------------
def test_box_knows_its_geometry():
    box = Box(type="box", size=(20, 40, 70))
    assert box.local_bbox().as_tuple() == ((-10, -20, -35), (10, 20, 35))
    pts = box.probe_points()
    assert len(pts) == 9 and pts[0] == (0.0, 0.0, 0.0)
    assert all(abs(p[i]) <= 0.4 * box.size[i] for p in pts for i in range(3))   # все внутри


def test_other_shapes_get_probe_points_on_stage_3():
    assert Cylinder(type="cylinder", radius=40, height=200).probe_points() == []


def test_every_solid_class_is_legal_in_the_table():
    # добавили класс фигуры в SOLIDS -> строка таблицы возможностей сама стала LEGAL
    assert set(SOLIDS) == {t for t, c in SHAPES.items() if c.action is Action.LEGAL}
    assert list(SHAPES) == list(PLANNED)                      # порядок строк — как в плане
    assert all(isinstance(e, SolidEmitter) and e.shape_type == t for t, e in SOLIDS.items())


def test_box_solid_gives_numbers_not_cpp():
    s = BoxSolid().solid(Box(type="box", size=(20, 40, 70)), "Body")
    assert (s.kind, s.name, s.size, s.half) == ("box", "Body", (20, 40, 70), (10, 20, 35))
    assert BoxSolid.volume_tol == 1e-6


# --- SceneLoader -------------------------------------------------------------------
@pytest.mark.parametrize("path", [TEST_SCENES / "nested_boxes.json", CONTRACT_V0_1 / "bad" / "b01_half_sizes.json"],
                         ids=["good", "bad"])
def test_loader_object_and_short_form_agree(path):
    a, da = SceneLoader().load(path)
    b, db = load_and_validate(path)
    assert a == b and da == db


def test_loader_options():
    overlap = TEST_SCENES.parent / "debug" / "overlap_debug.json"
    assert SceneLoader().load(overlap)[0] is None                       # E251 — ошибка
    scene, diags = SceneLoader(unsafe_skip_checks=True).load(overlap)  # отладка: предупреждение
    assert scene is not None and any(d.code == "E251" and d.level == "WARN" for d in diags)
