"""Единственное место, где известно расположение файлов в репозитории.

Пакет ставится только в редактируемом режиме (pip install -e), поэтому
файлы контракта и исходники g4scene берутся прямо из репозитория.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CONTRACT_V0_1 = REPO / "contracts" / "scene" / "v0.1"
SCHEMA_V0_1 = CONTRACT_V0_1 / "schema" / "scene.schema.json"
VALIDATE_V0_1 = CONTRACT_V0_1 / "validate.py"

G4SCENE_SRC = REPO / "cpp" / "g4scene"
TEST_SCENES = REPO / "tests" / "scenes"
FREECAD_FIXTURES = REPO / "tests" / "fixtures" / "freecad"


def all_test_scenes() -> list[Path]:
    """Все сцены, которые должны проходить проверку: ручные и образцы Никиты."""
    return sorted(TEST_SCENES.glob("*.json")) + sorted(FREECAD_FIXTURES.glob("*/scene.json"))


def scene_id(p: Path) -> str:
    """Имя для отчёта pytest: у образцов файл всегда scene.json, поэтому берём папку."""
    return p.parent.name if p.name == "scene.json" else p.name
