"""Зависимости mcscene во время работы (шаг 2.8).

Чтобы конвертер можно было положить в аддон FreeCAD папкой, без pip, во время работы
ему нужны только пакеты на чистом Python — сейчас это одна Jinja2 (с MarkupSafe).
pydantic (со скомпилированной частью pydantic-core) заменён своими классами
(model/record.py), jsonschema (с rpds-py) остался только в тестах:
tests/contract/test_schema_crosscheck.py.

Проверка — в отдельном процессе: в этом процессе pytest jsonschema уже мог загрузить
другой тест.
"""
import json
import subprocess
import sys

from mcscene.paths import TEST_SCENES

NOT_AT_RUNTIME = ["jsonschema", "pydantic", "pydantic_core"]


def test_generate_does_not_import_test_only_packages(tmp_path):
    code = (
        "import json, sys\n"
        "from mcscene import Converter\n"
        "r = Converter('geant4').generate(sys.argv[1], sys.argv[2])\n"
        "print(json.dumps({'status': str(r.status), 'loaded': sorted(m for m in %r if m in sys.modules)}))\n"
        % (NOT_AT_RUNTIME,)
    )
    out = subprocess.run([sys.executable, "-c", code, str(TEST_SCENES / "rotation_trap.json"),
                          str(tmp_path / "trap")], capture_output=True, text=True, check=True)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert (tmp_path / "trap" / "generated" / "GeneratedDetectorConstruction.cc").exists(), result
    assert result["loaded"] == [], "во время работы загружены пакеты, нужные только тестам"
