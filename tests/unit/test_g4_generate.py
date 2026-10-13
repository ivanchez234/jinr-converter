"""mcscene generate: какие файлы пишутся, что в них, детерминизм, --force и user/."""
import json

import pytest

from mcscene.cli import main
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

    assert gen(BOX02, out, "--force") == 0
    assert user.read_text("utf-8") == "// моя правка\n"          # user/ не тронут
    assert (out / "build/CMakeCache.txt").exists()                # build/ не тронут
    assert not (out / "generated/stale.cc").exists()              # generated/ пересоздан


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
