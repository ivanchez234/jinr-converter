"""Converter — вход в генератор для аддона и CLI (этап 2, шаги 2.5–2.6), реестр целей.

Главное: Converter ничего не печатает и не завершает программу, а возвращает результат;
новая цель подключается одной строкой в реестре, без правки общего кода.
"""
import json

import pytest

import mcscene
from mcscene import Converter, Status, targets, validate
from mcscene.backends import TARGETS, UnknownTarget
from mcscene.backends.base import Action, Backend, Capability, PlanResult
from mcscene.cli import main
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES, TEST_SCENES

BOX02 = FREECAD_FIXTURES / "02_box_20x40x70" / "etalon.json"
HALL = CONTRACT_V0_1 / "examples" / "05_hall_all_types.json"
BAD = CONTRACT_V0_1 / "bad" / "b01_half_sizes.json"


# --- Converter -------------------------------------------------------------------
def test_generate_returns_result_and_prints_nothing(tmp_path, capsys):
    r = Converter("geant4").generate(BOX02, tmp_path / "box")
    assert r.ok and r.status is Status.OK
    assert "generated/GeneratedDetectorConstruction.cc" in r.files
    assert r.user_created == ["user/DetectorConstruction.hh"] and r.user_kept == []
    assert [row.body_id for row in r.rows] == ["Box"]
    assert any("cmake" in line for line in r.next_steps)
    assert capsys.readouterr() == ("", "")                    # ни строчки в терминал


@pytest.mark.parametrize("scene, status, code", [
    (BAD, Status.INVALID, "E220"),                                          # нарушает контракт
    (CONTRACT_V0_1 / "examples" / "02_nested_pipe.json", Status.UNSUPPORTED, "E301"),  # цилиндры — этап 3
], ids=["invalid", "unsupported"])
def test_problems_come_back_as_status_not_exceptions(tmp_path, capsys, scene, status, code):
    r = Converter("geant4").generate(scene, tmp_path / "out")
    assert not r.ok and r.status is status
    assert code in {d.code for d in r.diagnostics if d.level == "ERROR"}
    assert not (tmp_path / "out").exists()                    # ничего не записано
    assert capsys.readouterr() == ("", "")


def test_missing_file_is_unreadable(tmp_path):
    r = Converter("geant4").generate(tmp_path / "nope.json", tmp_path / "out")
    assert r.status is Status.UNREADABLE and r.diagnostics[0].code == "E001"


def test_busy_folder_is_write_failed(tmp_path):
    conv = Converter("geant4")
    assert conv.generate(BOX02, tmp_path / "box").ok
    r = conv.generate(BOX02, tmp_path / "box")
    assert r.status is Status.WRITE_FAILED and "--force" in r.error
    r = conv.generate(BOX02, tmp_path / "box", force=True)
    assert r.ok and r.user_kept == ["user/DetectorConstruction.hh"]


def test_check_writes_nothing(tmp_path):
    ok = Converter("geant4").check(BOX02)
    assert ok.ok and ok.plan is not None and [r.action for r in ok.rows] == [Action.LEGAL]
    hall = Converter("geant4").check(HALL)
    assert hall.status is Status.UNSUPPORTED and hall.plan is None
    assert {"E301", "E310"} <= {d.code for d in hall.diagnostics}


def test_validate_without_target():
    assert validate(BOX02).ok
    assert validate(BAD).status is Status.INVALID


def test_top_level_import_and_targets():
    assert mcscene.Converter is Converter and "geant4" in targets()
    with pytest.raises(UnknownTarget, match="geant4"):
        Converter("fluka")                                    # в ошибке — список целей


def test_cli_and_converter_give_the_same_files(tmp_path):
    assert main(["generate", str(BOX02), "-o", str(tmp_path / "cli")]) == 0
    assert Converter("geant4").generate(BOX02, tmp_path / "api").ok
    read = lambda root: {p.relative_to(root).as_posix(): p.read_bytes()
                         for p in root.rglob("*") if p.is_file()}
    assert read(tmp_path / "cli") == read(tmp_path / "api")


# --- новая цель без правки общего кода -----------------------------------------------
@pytest.fixture
def demo_target(tmp_path, monkeypatch):
    """Цель-«игрушка»: список тел в текстовом файле. Только свой класс и свой пакет шаблонов."""
    pack = tmp_path / "demo_pack"
    (pack / "notes").mkdir(parents=True)
    (pack / "pack.json").write_text(json.dumps({
        "target": "demo", "generated": ["bodies.txt.j2"], "user": ["notes/README.txt.j2"]}), encoding="utf-8")
    (pack / "bodies.txt.j2").write_text(
        "сцена {{ name }}\n{% for b in bodies %}\n{{ b.id }}: {{ b.shape.type }}\n{% endfor %}\n", encoding="utf-8")
    (pack / "notes" / "README.txt.j2").write_text("мои заметки\n", encoding="utf-8")

    class DemoBackend(Backend):
        name = "demo"
        description = "список тел (проверка реестра)"
        capabilities = {"box": Capability(Action.LEGAL)}
        templates_dir = pack

        def plan(self, scene, source, unsafe=False):
            rows, diags = self.check(scene)
            ok = not any(d.level == "ERROR" for d in diags)
            return PlanResult({"name": source.stem, "bodies": scene.bodies} if ok else None, rows, diags)

        def context(self, plan):
            return plan

    monkeypatch.setitem(TARGETS, "demo", DemoBackend)       # та самая «одна строка в реестре»
    return DemoBackend


def test_new_target_needs_only_its_class_and_templates(demo_target, tmp_path):
    out = tmp_path / "out"
    r = Converter("demo").generate(TEST_SCENES / "nested_boxes.json", out)
    assert r.ok
    assert (out / "bodies.txt").read_text("utf-8") == "сцена nested_boxes\nouter: box\ninner: box\n"
    assert (out / "notes/README.txt").read_text("utf-8") == "мои заметки\n"
    assert "bodies.txt" in (out / ".mcscene").read_text("utf-8")
    # чего цель не умеет — та же общая проверка, с её именем
    bad = Converter("demo").check(HALL)
    assert bad.status is Status.UNSUPPORTED
    assert {d.target for d in bad.diagnostics if d.code == "E301"} == {"demo"}


def test_new_target_is_available_in_cli(demo_target, tmp_path, capsys):
    assert main(["targets"]) == 0
    assert "demo" in capsys.readouterr().out
    assert main(["generate", str(TEST_SCENES / "nested_boxes.json"), "-t", "demo", "-o", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "bodies.txt").exists()
