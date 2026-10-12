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
