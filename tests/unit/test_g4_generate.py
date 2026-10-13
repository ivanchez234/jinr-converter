"""mcscene generate: какие файлы пишутся, что в них, детерминизм, --force и user/."""
import json

import pytest

from mcscene.cli import main
from mcscene.io.load import load_and_validate
from mcscene.paths import CONTRACT_V0_1, FREECAD_FIXTURES, G4SCENE_SRC, TEST_SCENES

BOX02 = FREECAD_FIXTURES / "02_box_20x40x70" / "scene.json"

EXPECTED_FILES = {
    ".mcscene",
    "CMakeLists.txt",
    "report.json",
    "generated/GeneratedDetectorConstruction.hh",
    "generated/GeneratedDetectorConstruction.cc",
    "generated/ExpectedChecks.hh",
    "harness/check_geometry.cc",
    "app/main.cc",
    "app/vis.mac",
    "app/batch.mac",
    "user/DetectorConstruction.hh",
    "g4scene/include/g4scene/Transform.hh",
    "g4scene/include/g4scene/Registry.hh",
    "g4scene/include/g4scene/Materials.hh",
    "g4scene/src/Transform.cc",
    "g4scene/src/Registry.cc",
    "g4scene/src/Materials.cc",
}


def gen(scene, out, *extra):
    return main(["generate", str(scene), "-o", str(out), *extra])


def files_of(out):
    return {p.relative_to(out).as_posix(): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


def test_box02_project(tmp_path, capsys):
    out = tmp_path / "box"
    assert gen(BOX02, out) == 0
    assert set(files_of(out)) == EXPECTED_FILES
    assert "cmake -S %s -B %s/build" % (out, out) in capsys.readouterr().out

    cc = (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")
    assert 'new G4Box("Box", 10*mm, 20*mm, 35*mm)' in cc
    assert 'new G4Box("world", 352*mm, 165*mm, 165*mm)' in cc
    assert "G4ThreeVector(310*mm, -130*mm, 115*mm)" in cc
    assert 'fReg.AddMaterial("iron", scene::Nist("G4_Fe"));' in cc
    assert "scene::kIdentity" in cc                         # единичная матрица -> kIdentity
    assert "BuildBody_Box();" in cc

    hh = (out / "generated/GeneratedDetectorConstruction.hh").read_text("utf-8")
    assert "  void BuildBody_Box();" in hh

    checks = (out / "generated/ExpectedChecks.hh").read_text("utf-8")
    assert '{"Box", 56000, 1e-06},' in checks
    assert checks.count('"Box", "G4_Fe"},') == 9
    assert '{310, -130, 115, "Box", "G4_Fe"},' in checks
    assert '{302, -146, 87, "Box", "G4_Fe"},' in checks      # угол: центр − (8, 16, 28)

    cmake = (out / "CMakeLists.txt").read_text("utf-8")
    assert "project(scene_02_box_20x40x70 CXX)" in cmake
    assert "add_executable(check_geometry harness/check_geometry.cc)" in cmake

    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["input"]["file"] == "scene.json" and len(report["input"]["sha256"]) == 64
    assert report["bodies"][0]["probes"] == 9


def test_rotation_is_printed_as_matrix(tmp_path):
    out = tmp_path / "rot"
    assert gen(TEST_SCENES / "rotated_box.json", out) == 0
    cc = (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")
    assert "углы X, Y, Z = 0°, 0°, 90°" in cc
    assert "const scene::Mat3 rotation{{{0, -1, 0}," in cc
    assert "scene::Transform(rotation, G4ThreeVector(300*mm, -150*mm, 80*mm))" in cc


def test_child_is_placed_in_parent(tmp_path):
    out = tmp_path / "nested"
    assert gen(TEST_SCENES / "nested_boxes.json", out) == 0
    cc = (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")
    assert cc.index("BuildBody_outer();") < cc.index("BuildBody_inner();")
    assert 'scene::Place(lv, LV("outer"), "inner",' in cc


def test_app_and_vis_macro(tmp_path):
    out = tmp_path / "nested"
    assert gen(TEST_SCENES / "nested_boxes.json", out) == 0
    main_cc = (out / "app/main.cc").read_text("utf-8")
    assert '#include "DetectorConstruction.hh"' in main_cc        # приложение берёт user/
    assert "new QBBC(0)" in main_cc
    assert "PrimaryGenerator" not in main_cc                       # частиц пока нет

    vis = (out / "app/vis.mac").read_text("utf-8").splitlines()
    assert vis.index("/run/initialize") < vis.index("/vis/open") < vis.index("/vis/drawVolume")
    assert "/vis/geometry/set/visibility world 0 false" in vis
    assert "/vis/geometry/set/colour outer 0 0.12 0.47 0.71 0.3" in vis   # родитель прозрачный
    assert "/vis/geometry/set/colour inner 0 1 0.5 0.05 1" in vis         # лист непрозрачный
    assert all("#" not in line for line in vis if line.startswith("/"))   # комментарии — отдельными строками

    cmake = (out / "CMakeLists.txt").read_text("utf-8")
    assert "find_package(Geant4 REQUIRED ui_all vis_all)" in cmake
    assert "add_executable(scene_app app/main.cc)" in cmake
    assert "configure_file(app/vis.mac ${CMAKE_BINARY_DIR}/vis.mac COPYONLY)" in cmake


def test_same_material_same_colour(scene, box, tmp_path):
    s = scene(box("a", (1, 1, 1), (-5, 0, 0)), box("b", (1, 1, 1), (5, 0, 0)))
    path = tmp_path / "two.json"
    path.write_text(s.model_dump_json(exclude_unset=True), encoding="utf-8")
    assert gen(path, tmp_path / "out") == 0
    vis = (tmp_path / "out/app/vis.mac").read_text("utf-8")
    assert "/vis/geometry/set/colour a 0 0.12 0.47 0.71 1" in vis
    assert "/vis/geometry/set/colour b 0 0.12 0.47 0.71 1" in vis


def test_g4scene_is_copied_as_is(tmp_path):
    out = tmp_path / "box"
    assert gen(BOX02, out) == 0
    for rel in ["include/g4scene/Transform.hh", "src/Transform.cc", "src/Registry.cc"]:
        assert (out / "g4scene" / rel).read_bytes() == (G4SCENE_SRC / rel).read_bytes()


def test_deterministic_and_no_absolute_paths(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert gen(BOX02, a) == 0 and gen(BOX02, b) == 0
    fa, fb = files_of(a), files_of(b)
    assert fa == fb                                          # байт в байт
    for content in fa.values():
        assert str(tmp_path).encode() not in content
        assert str(BOX02.parent).encode() not in content


def test_second_run_needs_force(tmp_path, capsys):
    out = tmp_path / "box"
    assert gen(BOX02, out) == 0
    capsys.readouterr()
    assert gen(BOX02, out) == 2
    assert "--force" in capsys.readouterr().out


def test_force_keeps_user_and_build(tmp_path):
    out = tmp_path / "box"
    assert gen(BOX02, out) == 0
    user = out / "user/DetectorConstruction.hh"
    user.write_text("// моя правка\n", encoding="utf-8")
    (out / "build").mkdir()
    (out / "build/CMakeCache.txt").write_text("x", encoding="utf-8")
    (out / "generated/stale.cc").write_text("старый файл", encoding="utf-8")
    (out / "app/old.mac").write_text("старый файл", encoding="utf-8")

    assert gen(BOX02, out, "--force") == 0
    assert user.read_text("utf-8") == "// моя правка\n"          # user/ не тронут
    assert (out / "build/CMakeCache.txt").exists()                # build/ не тронут
    assert not (out / "generated/stale.cc").exists()              # generated/ пересоздан
    assert not (out / "app/old.mac").exists()                     # app/ тоже


def test_refuses_foreign_folder_even_with_force(tmp_path, capsys):
    out = tmp_path / "docs"
    out.mkdir()
    (out / "важное.txt").write_text("не трогать", encoding="utf-8")
    assert gen(BOX02, out, "--force") == 2
    assert "не похожа на результат mcscene" in capsys.readouterr().out
    assert [p.name for p in out.iterdir()] == ["важное.txt"]


def test_unsupported_scene_writes_nothing(tmp_path, capsys):
    out = tmp_path / "pipe"
    assert gen(CONTRACT_V0_1 / "examples" / "02_nested_pipe.json", out) == 1
    assert not out.exists()
    text = capsys.readouterr().out
    assert "E301" in text and "файлы не записаны" in text


def test_invalid_scene_writes_nothing(tmp_path):
    out = tmp_path / "bad"
    assert gen(CONTRACT_V0_1 / "bad" / "b01_half_sizes.json", out) == 1
    assert not out.exists()


def test_empty_existing_folder_is_fine(tmp_path):
    out = tmp_path / "empty"
    out.mkdir()
    assert gen(BOX02, out) == 0


@pytest.mark.parametrize("scene", sorted(TEST_SCENES.glob("*.json")), ids=lambda p: p.stem)
def test_all_hand_scenes_generate(tmp_path, scene):
    assert gen(scene, tmp_path / scene.stem) == 0


# --- --unsafe-skip-checks и отладочные сцены ---------------------------------------
DEBUG = TEST_SCENES.parent / "debug"
OVERLAP = DEBUG / "overlap_debug.json"


@pytest.mark.parametrize("scene", sorted(DEBUG.glob("*.json")), ids=lambda p: p.stem)
def test_debug_scenes_really_break_the_contract(scene):
    # если кто-то «починит» отладочную сцену, стенду нечего будет ловить
    _, diags = load_and_validate(scene)
    assert any(d.level == "ERROR" for d in diags)


def test_overlap_needs_unsafe_flag(tmp_path, capsys):
    assert gen(OVERLAP, tmp_path / "a") == 1
    assert not (tmp_path / "a").exists()
    assert "E251" in capsys.readouterr().out


def test_unsafe_flag_generates_and_marks_everything(tmp_path, capsys):
    out = tmp_path / "overlap"
    assert gen(OVERLAP, out, "--unsafe-skip-checks") == 0
    text = capsys.readouterr().out
    assert "ВНИМАНИЕ" in text and "WARN  E251" in text
    for rel in ["generated/GeneratedDetectorConstruction.cc", "generated/ExpectedChecks.hh",
                "harness/check_geometry.cc", "app/main.cc", "CMakeLists.txt", "app/vis.mac"]:
        assert "--unsafe-skip-checks" in (out / rel).read_text("utf-8"), rel
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert report["flags"]["unsafe_skip_checks"] is True
    assert {(d["level"], d["code"]) for d in report["diagnostics"]} >= {("WARN", "E251")}


def test_normal_projects_have_no_unsafe_mark(tmp_path):
    out = tmp_path / "box"
    assert gen(BOX02, out) == 0
    assert "unsafe" not in (out / "generated/GeneratedDetectorConstruction.cc").read_text("utf-8")
    assert json.loads((out / "report.json").read_text("utf-8"))["flags"]["unsafe_skip_checks"] is False


@pytest.mark.parametrize("bad", ["b04_bad_references", "b07_schema_typos", "b06_mesh_broken"])
def test_unsafe_flag_does_not_skip_other_errors(tmp_path, bad):
    # битые ссылки, структура, меши — генератор с ними работать не может даже для отладки
    assert gen(CONTRACT_V0_1 / "bad" / (bad + ".json"), tmp_path / bad, "--unsafe-skip-checks") == 1
    assert not (tmp_path / bad).exists()


@pytest.mark.parametrize("mutate, code", [
    (lambda d: d["bodies"][0].update(material="steel2"), "E202"),          # нет такого материала
    (lambda d: d["bodies"][0].update(parent="nope"), "E203"),              # нет такого родителя
    (lambda d: d["world"].update(material="vacuum"), "E204"),              # нет материала мира
], ids=["material", "parent", "world-material"])
def test_unsafe_flag_does_not_skip_broken_references(tmp_path, mutate, code):
    # сцена только из коробок: отказ может быть только из-за ссылки, а не из-за формы
    doc = json.loads(BOX02.read_text("utf-8"))
    mutate(doc)
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    _, diags = load_and_validate(path, unsafe_skip_checks=True)
    assert code in {d.code for d in diags if d.level == "ERROR"}
    assert gen(path, tmp_path / "out", "--unsafe-skip-checks") == 1
    assert not (tmp_path / "out").exists()


def test_unsafe_flag_does_not_skip_unsupported_shapes(tmp_path):
    assert gen(CONTRACT_V0_1 / "examples" / "02_nested_pipe.json", tmp_path / "p",
               "--unsafe-skip-checks") == 1
