"""Таблица возможностей Geant4 и mcscene check."""
import json

import pytest

from mcscene.backends.base import Action
from mcscene.backends.geant4.capabilities import SHAPES, check
from mcscene.cli import main, plural
from mcscene.model import Scene
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES, TEST_SCENES

BOX02 = FREECAD_FIXTURES / "02_box_20x40x70" / "scene.json"
HALL = CONTRACT_V0_1 / "examples" / "05_hall_all_types.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return Scene.model_validate(json.load(f))


def test_stage1_supports_only_box():
    assert [t for t, c in SHAPES.items() if c.action is Action.LEGAL] == ["box"]
    assert set(SHAPES) == {"box", "cylinder", "cone", "sphere", "torus", "boolean", "mesh"}


def test_box_scene_is_legal():
    rows, diags = check(load(BOX02))
    assert [(r.body_id, r.shape_type, r.action) for r in rows] == [("Box", "box", Action.LEGAL)]
    assert diags == []


def test_unsupported_shapes_say_which_stage():
    rows, diags = check(load(HALL))
    got = {r.body_id: (r.action, r.note) for r in rows}
    assert got["pipe"][0] is Action.ERROR and "этап 2" in got["pipe"][1]
    assert "этап 3" in got["wall_b"][1]
    assert "этап 4" in got["magnet_yoke"][1]
    assert {d.code for d in diags} == {"E301"}
    assert all(d.target == "geant4" and d.body_id for d in diags)


def test_cli_check_box(capsys):
    assert main(["check", str(BOX02)]) == 0
    out = capsys.readouterr().out
    assert "Box  box  LEGAL" in out
    assert "итог: 1 тело, 0 ошибок, 0 предупреждений -> можно генерировать" in out


def test_cli_check_hall(capsys):
    assert main(["check", str(HALL)]) == 1
    out = capsys.readouterr().out
    assert "E301" in out and "E310" in out
    assert "итог: 5 тел, 6 ошибок, 0 предупреждений -> генерировать нельзя" in out


def test_cli_check_bad_contract_file(capsys):
    assert main(["check", str(CONTRACT_V0_1 / "bad" / "b01_half_sizes.json")]) == 1
    assert "E220" in capsys.readouterr().out


def test_cli_check_missing_file(tmp_path):
    assert main(["check", str(tmp_path / "nope.json")]) == 2


def test_cli_check_unknown_target():
    with pytest.raises(SystemExit) as e:
        main(["check", str(BOX02), "-t", "fluka"])
    assert e.value.code == 2


def test_cli_plan_is_json(capsys):
    assert main(["check", str(TEST_SCENES / "rotated_box.json"), "--plan"]) == 0
    out = capsys.readouterr().out
    plan = json.loads(out[out.index("{"):])
    assert plan["world"]["half_size"] == [352.0, 176.0, 126.5]
    assert plan["bodies"][0]["solid"]["cpp"] == 'new G4Box("box", 10*mm, 20*mm, 35*mm)'
    assert '"matrix": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]' in out


@pytest.mark.parametrize("n, word", [(0, "тел"), (1, "тело"), (2, "тела"), (4, "тела"), (5, "тел"),
                                     (11, "тел"), (12, "тел"), (21, "тело"), (22, "тела"), (111, "тел")])
def test_plural(n, word):
    assert plural(n, "тело", "тела", "тел") == word
