"""Golden-тесты: сгенерированный проект сравнивается с эталонными файлами.

Эталоны лежат в tests/golden/<сцена>/geant4/ — ровно то, что пишет
mcscene generate, кроме копии g4scene/ (её проверяет свой тест и её тесты в C++).

Любое изменение генератора, которое меняет вывод, уронит этот тест. Если
изменение намеренное, обновите эталоны и посмотрите разницу глазами:

    UPDATE_GOLDEN=1 pytest tests/golden
    git diff tests/golden          # прочитать перед коммитом!
"""
import difflib
import os
from pathlib import Path

import pytest

from mcscene.cli import main
from mcscene.paths import FREECAD_FIXTURES, TEST_SCENES

GOLDEN = Path(__file__).resolve().parent
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

SCENES = {
    "box_in_world": TEST_SCENES / "box_in_world.json",
    "nested_boxes": TEST_SCENES / "nested_boxes.json",
    "rotated_box": TEST_SCENES / "rotated_box.json",
    "01_kub": FREECAD_FIXTURES / "01_kub" / "scene.json",
    "02_box_20x40x70": FREECAD_FIXTURES / "02_box_20x40x70" / "scene.json",
}


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.relative_to(root).as_posix().startswith(("g4scene/", "build/"))}


@pytest.mark.parametrize("name", sorted(SCENES))
def test_generated_project_matches_golden(name, tmp_path):
    out = tmp_path / name
    assert main(["generate", str(SCENES[name]), "-o", str(out)]) == 0
    got = _files(out)
    golden_dir = GOLDEN / name / "geant4"

    if UPDATE:
        if golden_dir.exists():
            for old in sorted(golden_dir.rglob("*"), reverse=True):
                old.unlink() if old.is_file() else old.rmdir()
        for rel, data in got.items():
            (golden_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (golden_dir / rel).write_bytes(data)
        pytest.skip("эталоны %s обновлены — посмотрите git diff tests/golden" % name)

    assert golden_dir.is_dir(), "нет эталонов для %s: запустите UPDATE_GOLDEN=1 pytest tests/golden" % name
    want = _files(golden_dir)
    assert sorted(got) == sorted(want), "набор файлов отличается от эталона"

    for rel in sorted(want):
        if got[rel] != want[rel]:
            diff = difflib.unified_diff(
                want[rel].decode("utf-8").splitlines(), got[rel].decode("utf-8").splitlines(),
                "эталон/" + rel, "сейчас/" + rel, lineterm="", n=2)
            pytest.fail("%s отличается от эталона:\n%s\n\nЕсли изменение намеренное: "
                        "UPDATE_GOLDEN=1 pytest tests/golden и проверить git diff"
                        % (rel, "\n".join(list(diff)[:60])))
