"""Команда mcscene validate: коды выхода и вывод."""
import json

import pytest

from mcscene.cli import main
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES


def test_good_scene_exit_0(capsys):
    assert main(["validate", "--strict", str(TEST_SCENES / "box_in_world.json")]) == 0
    assert "-> OK" in capsys.readouterr().out


def test_bad_scene_exit_1(capsys):
    assert main(["validate", str(CONTRACT_V0_1 / "bad" / "b01_half_sizes.json")]) == 1
    out = capsys.readouterr().out
    assert "E220" in out and "НЕ ПРОШЁЛ" in out


def test_missing_file_exit_2(tmp_path):
    assert main(["validate", str(tmp_path / "nope.json")]) == 2


def test_not_json_exit_2(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ это не json", encoding="utf-8")
    assert main(["validate", str(p)]) == 2


def test_several_files_worst_code_wins():
    good = str(TEST_SCENES / "box_in_world.json")
    bad = str(CONTRACT_V0_1 / "bad" / "b01_half_sizes.json")
    assert main(["validate", good, bad]) == 1


def test_unknown_field_is_warning_without_strict(tmp_path, capsys):
    doc = json.loads((TEST_SCENES / "box_in_world.json").read_text(encoding="utf-8"))
    doc["bodies"][0]["shape"]["colour"] = "red"
    p = tmp_path / "scene.json"
    p.write_text(json.dumps(doc), encoding="utf-8")

    assert main(["validate", str(p)]) == 0              # предупреждение W100, но сцена читается
    assert "W100" in capsys.readouterr().out
    assert main(["validate", "--strict", str(p)]) == 1  # в строгом режиме это ошибка


def test_bad_call_exit_2():
    with pytest.raises(SystemExit) as e:
        main(["frobnicate"])
    assert e.value.code == 2
