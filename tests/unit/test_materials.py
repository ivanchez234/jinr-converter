"""Материалы (проход MaterialPass): какие попадают в код и что пока не поддерживается."""
import json

from mcscene.diagnostics import Diagnostics
from mcscene.model import Scene
from mcscene.passes import MaterialPass
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES

STEEL = {"id": "steel", "density": 7.93, "state": "solid",
         "composition": {"basis": "mass", "components": [{"element": "Fe", "fraction": 0.7},
                                                         {"element": "Cr", "fraction": 0.3}]}}


def run(p, scene):
    """Проход над сценой -> (результат, сообщения)."""
    diags = Diagnostics()
    return p.run(scene, diags), diags


def load(path):
    with open(path, encoding="utf-8") as f:
        return Scene.model_validate(json.load(f))


def test_fixture_02_nist_only():
    plans, diags = run(MaterialPass(), load(FREECAD_FIXTURES / "02_box_20x40x70" / "etalon.json"))
    assert diags == []
    assert [(p.id, p.nist, p.used_by) for p in plans] == [
        ("air", "G4_AIR", ("world",)),
        ("iron", "G4_Fe", ("Box",)),
    ]


def test_unused_material_is_skipped(scene, box):
    mats = [{"id": "air", "nist": "G4_AIR"}, {"id": "lead", "nist": "G4_Pb"},
            {"id": "iron", "nist": "G4_Fe"}]
    plans, diags = run(MaterialPass(), scene(box("b", (1, 1, 1)), materials=mats))
    assert [p.id for p in plans] == ["air", "iron"]             # порядок как в файле
    assert [(d.code, d.where) for d in diags] == [("I402", "materials/lead")]


def test_custom_composition_is_stage_4(scene, box):
    s = scene(box("b", (1, 1, 1), material="steel"),
              materials=[{"id": "air", "nist": "G4_AIR"}, STEEL])
    _, diags = run(MaterialPass(), s)
    assert [(d.level, d.code, d.where) for d in diags] == [("ERROR", "E310", "materials/steel")]

    plans, diags = run(MaterialPass(allow_custom=True), s)          # с этапа 4
    assert diags == []
    assert plans[1].nist is None and plans[1].density == 7.93


def test_nist_wins_over_composition(scene, box):
    both = dict(STEEL, nist="G4_STAINLESS-STEEL")
    plans, diags = run(MaterialPass(), scene(box("b", (1, 1, 1), material="steel"),
                                        materials=[{"id": "air", "nist": "G4_AIR"}, both]))
    assert plans[1].nist == "G4_STAINLESS-STEEL"
    assert [d.code for d in diags] == ["I410"]


def test_material_used_by_world_and_bodies(scene, box):
    plans, _ = run(MaterialPass(), scene(box("a", (1, 1, 1), material="air"),
                                    box("b", (1, 1, 1), (5, 0, 0))))
    assert {p.id: p.used_by for p in plans} == {"air": ("world", "a"), "iron": ("b",)}


def test_example_with_steel_needs_stage_4():
    _, diags = run(MaterialPass(), load(CONTRACT_V0_1 / "examples" / "02_nested_pipe.json"))
    assert [(d.code, d.where) for d in diags if d.level == "ERROR"] == [("E310", "materials/steel_304")]
