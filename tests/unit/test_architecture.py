"""Устройство кода: объекты, а не россыпь функций (просьба руководителя, шаг 2.7).

Публичная функция на уровне модуля (def без «_» в начале, вне класса) разрешена
только там, где она перечислена ниже, — с причиной. Всё остальное — методы объектов.
Новая такая функция уронит тест: значит, её место в каком-то классе, или её нужно
осознанно добавить в этот список.
"""
import ast
from fnmatch import fnmatch

from mcscene.paths import REPO

PACKAGE = REPO / "python" / "mcscene"

ALLOWED = {
    "__init__.py": {"__getattr__": "ленивый импорт: from mcscene import Converter"},
    "api.py": {"validate": "вход для программ: проверить сцену без выбора цели"},
    "backends/__init__.py": {"targets": "реестр целей", "get_backend": "реестр целей"},
    "backends/base.py": {"check_shapes": "чистая функция: таблица возможностей -> строки и E301"},
    "backends/geant4/filters.py": {"*": "фильтры Jinja2 — функции по своей природе (как записать число)"},
    "backends/geant4/plan.py": {"scene_name": "имя сцены из имени файла"},
    "cli.py": {"*": "командная строка — слой печати, как UI-элементы"},
    "diagnostics/__init__.py": {"has_errors": "проверка списка", "print_diagnostics": "печать"},
    "io/contract.py": {"load_*": "загрузка файлов контракта с кешем"},
    "io/load.py": {"load_and_validate": "короткая запись SceneLoader(...).load()",
                   "drop_fields": "чистая функция над JSON"},
    "paths.py": {"*": "поиск файлов репозитория и тестовых сцен"},
}


def public_functions():
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(PACKAGE).as_posix()
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and not (node.name.startswith("_") and node.name != "__getattr__"):
                yield rel, node.name


def test_no_loose_functions_outside_the_list():
    loose = ["%s: %s()" % (rel, name) for rel, name in public_functions()
             if not any(fnmatch(name, pattern) for pattern in ALLOWED.get(rel, {}))]
    assert loose == [], "функции вне объектов (переложить в класс или добавить в ALLOWED с причиной):\n" + "\n".join(loose)


def test_core_modules_are_objects_only():
    # геометрия, модель, проходы, шаблоны и запись — только классы
    core = ("geometry/", "model/", "passes/", "templating/", "backends/writer.py", "backends/geant4/solids.py",
            "backends/geant4/naming.py", "backends/geant4/backend.py")
    assert [f for f in public_functions() if f[0].startswith(core)] == []
