# Пошаговый план реализации выходного модуля

*Ваня • 11 октября 2026 • дополнение к «Плану выходного модуля v2»*

Это рабочая инструкция: что делать по порядку, какие файлы создавать, как проверять и когда этап считается законченным. Архитектура и обоснования — в плане v2, здесь их не повторяю.

> Код в этом файле — наброски для ориентира, здесь они не компилировались и не запускались. Сигнатуры Geant4 взяты из документации 11.x; если что-то не собирается, правьте по заголовкам вашей версии.

## Сводка

| Этап | Даты | Готово, когда | Образец от Никиты |
|---|---|---|---|
| 0. Каркас | 12–18 окт | Geant4 стоит; `mcscene validate` даёт тот же результат, что `validate.py` | куб 50 мм (уже есть) |
| 1. Сквозная коробка | 19 окт – 1 ноя | куб и коробка 20×40×70 из FreeCAD видны в Geant4 | `Part::Box` 20×40×70, сдвинутый по трём осям |
| 2. Повороты и примитивы | 2–15 ноя | цилиндр, конус, сфера, тор, вложенность, ловушка поворотов | повёрнутая коробка; повёрнутый цилиндр; труба с вакуумом |
| 3. Материалы и булевы | 16–29 ноя | Cut из FreeCAD в Geant4, свои составы | `Part::Cut`; два тела с назначенными материалами |
| 4. Меши и отчёт | 30 ноя – 13 дек | деталь со скруглением доходит до Geant4 | деталь с Fillet → STL |
| 5. MVP | 14–20 дек | реальная модель целиком, демо, материал для отчёта | сцена из нескольких тел, лучше реальная деталь отдела |
| 6. Вторая цель | с января | Region IR + OpenMC или FLUKA | — |

## Общие правила на весь проект

**Ветки.** Одна ветка на этап или на заметную задачу (`stage1-box`, `stage2-rotations`), слияние через pull request. Никита смотрит PR, если затронуто что-то в `contracts/`.

**Образцы Никиты.** Каждый образец кладётся в `tests/fixtures/freecad/NN_имя/`:

```
tests/fixtures/freecad/02_box_20x40x70/
  model.FCStd        # исходник из FreeCAD
  scene.json         # его экспорт
  meshes/            # если есть
  README.md          # что это, какие ожидаются размеры/центр/материал
```

На каждый образец действуете одинаково:

1. `python contracts/scene/v0.1/validate.py --strict scene.json` — если падает, файл возвращается Никите с текстом ошибки.
2. `mcscene generate` → сборка → `check_geometry` → визуализация.
3. Отвечаете Никите в Telegram: «принято» или что не сходится. Если не сходится, сначала решаете вдвоём: это ошибка экспорта, ошибка генератора или неудачное правило контракта. Правило контракта меняется только новой версией.
4. Принятый образец остаётся тестом навсегда.

**Ритм недели.** В начале недели — список задач из этого файла (`- [ ]` можно отмечать прямо в GitHub). В конце недели — коммит и две-три строки в Telegram: что сделано, что мешает. Перед встречей с руководителем — прогон всех фикстур (`tools/e2e.sh`).

---

## Этап 0. Каркас (12–18 октября)

**Цель:** рабочее окружение и пакет `mcscene`, который читает и проверяет сцену так же, как `validate.py`.

### 0.1 Окружение Geant4

Если ноутбук на Windows — всё делать в WSL2 (Ubuntu 24.04). Geant4, CMake и генератор живут в Linux.

Вариант А (быстрее) — conda-forge через micromamba:

```bash
micromamba create -n g4 -c conda-forge geant4 cmake make cxx-compiler python=3.11
micromamba activate g4
geant4-config --version             # ожидается 11.4.x
geant4-config --has-feature qt      # есть ли Qt-интерфейс
```

Вариант Б — сборка из исходников, если в conda нет Qt или нужна та же сборка, что в отделе:

```bash
cmake -S geant4-v11.4.x -B build -DCMAKE_INSTALL_PREFIX=$HOME/geant4 \
      -DGEANT4_INSTALL_DATA=ON -DGEANT4_USE_QT=ON -DGEANT4_USE_OPENGL_X11=ON
cmake --build build -j$(nproc) && cmake --install build
source $HOME/geant4/bin/geant4.sh
```

`GEANT4_INSTALL_DATA` по умолчанию выключен, а без наборов данных не запустится физика (для проверки одной геометрии они не нужны, для демо-приложения нужны).

- [ ] Geant4 установлен, `geant4-config --version` работает
- [ ] Пример `examples/basic/B1` (из исходников той же версии) собран и открывает окно визуализации
- [ ] Записать в `docs/setup.md`, какие команды сработали — пригодится Никите и руководителю

### 0.2 Репозиторий

Если руководитель уже создал репозиторий — работаете в нём, иначе создаёте `jinr-converter` сами и добавляете Никиту и руководителя.

```
jinr-converter/
├─ contracts/scene/v0.1/    # содержимое jinr-mc-scene-v0.1.zip как есть
├─ python/mcscene/
├─ cpp/g4scene/
├─ tests/
├─ tools/
├─ docs/
├─ pyproject.toml
├─ README.md
└─ .gitignore               # build/, out/, .venv/, __pycache__/
```

- [ ] Контракт лежит в `contracts/scene/v0.1/`, и его больше нигде не копируете руками
- [ ] Никита перенёс аддон в `inputs/freecad/JINRScene/` (это его задача, но договоритесь в первую неделю)

### 0.3 Пакет Python

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "mcscene"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pydantic>=2.6", "jsonschema>=4.18"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
mcscene = "mcscene.cli:main"

[tool.setuptools.packages.find]
where = ["python"]
```

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
mcscene --help
```

До MVP ставите пакет **только в режиме `-e`** (редактируемый). Тогда `mcscene` находит схему, `validate.py` и исходники `g4scene` прямо в репозитории. Упаковка в wheel — после MVP.

`python/mcscene/paths.py` — одно место, где знают про расположение файлов:

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRACT_V0_1 = REPO / "contracts" / "scene" / "v0.1"
SCHEMA_V0_1 = CONTRACT_V0_1 / "scene.schema.json"
G4SCENE_SRC = REPO / "cpp" / "g4scene"
```

### 0.4 Чтение и проверка: используем `validate.py`, а не переписываем

Самый надёжный способ получить «тот же результат, что `validate.py`» — **вызвать сам `validate.py`**. Правила тогда существуют в одном экземпляре, и расходиться им не с чем.

`mcscene validate scene.json` делает по порядку:

1. Загружает JSON (ошибка чтения → код `E001`, как в `validate.py`).
2. Проверяет по `scene.schema.json` стандартным `jsonschema.Draft202012Validator`.
3. Вызывает семантику из `validate.py`: `validate.validate_document(doc, base_dir, rep, schema)`.
4. Если ошибок нет — разбирает документ в pydantic-модели (Scene IR).

```python
# python/mcscene/io/contract.py
import importlib.util
from ..paths import CONTRACT_V0_1

def load_contract_validator():
    spec = importlib.util.spec_from_file_location(
        "jinr_contract_v0_1", CONTRACT_V0_1 / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

`validate.py` возвращает объекты `Issue(level, code, where, msg)`. Оберните их в свой `Diagnostic`, чтобы дальше в генераторе был один тип:

```python
# python/mcscene/diagnostics/__init__.py
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class Diagnostic:
    level: Literal["ERROR", "WARN", "INFO"]
    code: str            # E202, W241, E301 ...
    where: str           # bodies/Body/material
    message: str
    body_id: str | None = None
    target: str | None = None
```

Коды `validate.py` (`E0xx`, `E1xx`, `E2xx`, `W1xx`, `W2xx`, `I0xx`, `I2xx`) оставляете как есть. Свои коды генератора: `E3xx` — цель не умеет, `W4xx`/`I4xx` — смена представления и имён, `W5xx` — проверка не сошлась, `E6xx` — сборка или стенд упали.

### 0.5 Модели Scene IR (сразу для всех фигур)

Моделей для всех семи фигур — на полсотни строк, поэтому пишите их сразу. Генерировать будете по одной фигуре за этап, а неподдерживаемые пока фигуры дадут понятную ошибку на шаге `check`.

```python
# python/mcscene/model/scene.py
from __future__ import annotations
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

Vec3 = tuple[float, float, float]

# --- поворот и размещение ---
class RotIdentity(Strict):
    convention: Literal["identity"]

class RotMatrix(Strict):
    convention: Literal["matrix_active"]
    matrix: tuple[Vec3, Vec3, Vec3]          # по строкам

class RotEuler(Strict):
    convention: Literal["euler_xyz_extrinsic_deg"]
    angles: Vec3                              # R = Rz·Ry·Rx

Rotation = Annotated[Union[RotIdentity, RotMatrix, RotEuler],
                     Field(discriminator="convention")]

class Transform(Strict):
    translation: Vec3
    rotation: Rotation

# --- формы ---
class Box(Strict):
    type: Literal["box"]
    size: Vec3
    transform: Optional[Transform] = None    # только у операнда булевой операции

class Cylinder(Strict):
    type: Literal["cylinder"]
    radius: float
    height: float
    inner_radius: float = 0.0
    transform: Optional[Transform] = None

class Cone(Strict):
    type: Literal["cone"]
    radius_bottom: float
    radius_top: float
    height: float
    inner_radius_bottom: float = 0.0
    inner_radius_top: float = 0.0
    transform: Optional[Transform] = None

class Sphere(Strict):
    type: Literal["sphere"]
    radius: float
    inner_radius: float = 0.0
    transform: Optional[Transform] = None

class Torus(Strict):
    type: Literal["torus"]
    major_radius: float
    minor_radius: float
    transform: Optional[Transform] = None

class Boolean(Strict):
    type: Literal["boolean"]
    op: Literal["union", "subtract", "intersect"]
    left: "Operand"
    right: "Operand"
    transform: Optional[Transform] = None

class Mesh(Strict):
    type: Literal["mesh"]
    uri: str
    encoding: Literal["stl-binary", "stl-ascii"]
    sha256: str
    n_facets: int
    fallback_reason: Literal["SPLINE_SURFACE", "PRIMITIVE_FIT_FAILED",
                             "BOOLEAN_TOO_COMPLEX", "USER_FORCED"]
    tessellation: Optional[dict] = None
    note: Optional[str] = None

Operand = Annotated[Union[Box, Cylinder, Cone, Sphere, Torus, Boolean],
                    Field(discriminator="type")]
Shape = Annotated[Union[Box, Cylinder, Cone, Sphere, Torus, Boolean, Mesh],
                  Field(discriminator="type")]
Boolean.model_rebuild()

# --- материалы, тела, сцена ---
class Component(Strict):
    element: str
    fraction: float

class Composition(Strict):
    basis: Literal["mass", "atom"]
    components: list[Component]

class Material(Strict):
    id: str
    name: Optional[str] = None
    nist: Optional[str] = None
    density: Optional[float] = None          # g/cm3
    state: Optional[Literal["solid", "liquid", "gas"]] = None
    composition: Optional[Composition] = None
    provenance: Optional[str] = None
    extensions: Optional[dict] = None
    extras: Optional[dict] = None

class Verification(Strict):
    cad_volume: float
    cad_area: Optional[float] = None
    bbox: Optional[tuple[Vec3, Vec3]] = None

class Body(Strict):
    id: str
    name: Optional[str] = None
    parent: Optional[str]
    material: str
    transform: Transform
    shape: Shape
    verification: Verification
    extensions: Optional[dict] = None
    extras: Optional[dict] = None

class World(Strict):
    material: str
    margin_percent: float = 10.0

class Scene(Strict):
    format: Literal["jinr-mc-scene"]
    format_version: str
    min_reader_version: Optional[str] = None
    source: Optional[dict] = None
    units: dict
    extensions_used: list[str] = []
    extensions_required: list[str] = []
    world: World
    materials: list[Material]
    bodies: list[Body]
    extensions: Optional[dict] = None
    extras: Optional[dict] = None
```

`extra="forbid"` повторяет `additionalProperties: false` из схемы. Если модель и схема в чём-то разойдутся, это покажет тест эквивалентности (шаг 0.7).

### 0.6 Командная строка

На старте только `validate`, остальные команды добавятся на этапах 1 и 4:

```python
# python/mcscene/cli.py
import argparse, sys

def main(argv=None):
    p = argparse.ArgumentParser(prog="mcscene")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="проверить сцену")
    v.add_argument("scene"); v.add_argument("--strict", action="store_true")
    v.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "validate":
        from .io.load import load_and_validate
        scene, diags = load_and_validate(args.scene, strict=args.strict)
        print_diagnostics(diags, verbose=args.verbose)
        return 1 if any(d.level == "ERROR" for d in diags) else 0

if __name__ == "__main__":
    sys.exit(main())
```

Коды выхода: 0 — успех, 1 — ошибки сцены, 2 — неверный вызов или файл не читается.

### 0.7 Тесты и фикстуры

```
tests/
  scenes/
    kub.json                 # первый образец Никиты, как есть
    box_in_world.json        # коробка 100×50×20 в (10, 20, 30)
    nested_boxes.json        # коробка в коробке, без поворотов
    rotated_box.json         # коробка 20×40×70, поворот 90° вокруг z
  contract/test_equivalence.py
  unit/test_models.py
```

Главный тест этапа — эквивалентность:

```python
# tests/contract/test_equivalence.py
import pytest
from pathlib import Path
from mcscene.paths import CONTRACT_V0_1
from mcscene.io.load import load_and_validate
from mcscene.io.contract import load_contract_validator

V = load_contract_validator()
FILES = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + \
        sorted((CONTRACT_V0_1 / "bad").glob("*.json")) + \
        sorted(Path("tests/scenes").glob("*.json"))

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_same_verdict_as_validate_py(path):
    ref = V.validate_file(str(path), strict=True)
    _, ours = load_and_validate(path, strict=True)
    ref_err = {i.code for i in ref if i.level == "ERROR"}
    our_err = {d.code for d in ours if d.level == "ERROR"}
    assert bool(ref_err) == bool(our_err)
    assert ref_err <= our_err          # все коды validate.py есть и у нас

@pytest.mark.parametrize("path", sorted((CONTRACT_V0_1 / "examples").glob("*.json")))
def test_good_examples_parse_into_models(path):
    scene, diags = load_and_validate(path, strict=True)
    assert scene is not None
```

- [ ] `pytest` зелёный
- [ ] `mcscene validate tests/scenes/kub.json --strict` → OK, код 0
- [ ] `mcscene validate contracts/scene/v0.1/bad/b01_half_sizes.json` → ошибка `E220`, код 1

### Этап 0 готов, когда

- Geant4 стоит, B1 запускается с визуализацией.
- `mcscene validate` выносит тот же вердикт, что `validate.py`, на всех 5 хороших, 8 плохих примерах и на кубе Никиты (тест эквивалентности зелёный).
- Все хорошие примеры разбираются в pydantic-модели.

**От Никиты:** куб (уже есть); перенос аддона в общий репозиторий.

**Типичные ошибки:** ставить pydantic в Python FreeCAD (не нужно, у `mcscene` своё окружение); переписывать правила `validate.py` вручную вместо вызова.

---

## Этап 1. Сквозная коробка (19 октября – 1 ноября)

**Цель:** `scene.json` с коробками → C++ проект → компиляция → геометрия видна в Geant4 и проверена стендом.

### 1.1 Общие проходы над Scene IR

Создайте `python/mcscene/passes/` и пишите каждую функцию с юнит-тестом.

**Поворот → матрица** (`passes/rotations.py`):

```python
import math

def to_matrix(rot) -> tuple[tuple[float, ...], ...]:
    if rot.convention == "identity":
        return ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    if rot.convention == "matrix_active":
        return snap(rot.matrix)
    a, b, c = (math.radians(x) for x in rot.angles)      # R = Rz(c)·Ry(b)·Rx(a)
    return snap(mul(rz(c), mul(ry(b), rx(a))))

def snap(m, eps=1e-12):
    """Убирает шум вида 2.2e-16 и -0.0 — для читаемого кода."""
    return tuple(tuple(0.0 if abs(x) < eps else
                       (1.0 if abs(x - 1) < eps else (-1.0 if abs(x + 1) < eps else x))
                       for x in row) for row in m)
```

Тесты: `euler [0,0,90]` переводит (1, 0, 0) в (0, 1, 0); `euler [90,0,0]` переводит (0, 1, 0) в (0, 0, 1); матрица из `rotated_box.json` совпадает с ожидаемой.

**Мир** (`passes/world.py`). Мир в Geant4 — коробка с центром в начале координат. Её полуразмер по каждой оси = наибольшее |координата| среди всех корневых тел × (1 + `margin_percent`/100).

- bbox корневого тела берите из `verification.bbox`, если он есть.
- Иначе считайте: локальный bbox формы (у коробки ±size/2, у цилиндра ±R, ±R, ±H/2 и т.д.) → 8 углов → поворот и сдвиг → min/max.
- Для `parent != null` мир не трогается.

Для куба Никиты: bbox [-25, -25, 0]..[25, 25, 50] → полуразмеры 27.5 × 27.5 × 55 мм. Это хороший первый юнит-тест.

**Имена** (`passes/naming.py`). `id` из JSON (`^[A-Za-z_][A-Za-z0-9_-]*$`) годится как имя объёма Geant4 как есть. Для C++ функций (`BuildBody_<id>`) замените `-` на `_`. Если два `id` после замены совпали, добавьте `_2` и выдайте `I401`. `world` — зарезервированное имя: тело с `id == "world"` получает `world_body` + `I401`.

**Материалы** (`passes/materials.py`). На этапе 1 — только NIST: у материала есть `nist` → в коде `scene::Nist("G4_Fe")`. Материал без `nist` → `E310 «свои составы появятся на этапе 3»`.

### 1.2 План генерации (TargetPlan)

Принтер не должен видеть сырой JSON и даже Scene IR целиком: ему передаётся уже подготовленный «план». Так шаблоны не ломаются, когда меняется схема.

```python
# python/mcscene/backends/geant4/plan.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SolidPlan:          # что напечатать для формы
    cpp: str              # 'new G4Box("Body", 25*mm, 25*mm, 25*mm)'
    comment: str          # 'коробка 50 × 50 × 50 мм'

@dataclass(frozen=True)
class BodyPlan:
    id: str
    func: str             # BuildBody_Body
    title: str            # 'Тело "Body" — «Тело», Железо (NIST)'
    solid: SolidPlan
    material_id: str
    mother_id: str        # 'world' или id родителя
    matrix: tuple         # 3×3, уже нормализованная
    translation: tuple    # мм
    cad_volume: float
    probes: list          # пробные точки, см. 1.6

@dataclass(frozen=True)
class G4Plan:
    scene_name: str
    input_sha256: str
    materials: list       # [(id, cpp-выражение)]
    world: tuple          # полуразмеры, материал
    bodies: list[BodyPlan]  # родители раньше детей
```

### 1.3 Таблица возможностей и `check`

```python
# python/mcscene/backends/base.py
from enum import Enum
class Action(str, Enum):
    LEGAL = "legal"; LOWER = "lower"; APPROXIMATE = "approximate"; ERROR = "error"
```

У Geant4 на этапе 1: `box → LEGAL`, всё остальное → `ERROR` с кодом `E301 «фигура ещё не реализована в генераторе»`. На каждом следующем этапе меняете одну строчку в таблице. `mcscene check scene.json -t geant4` печатает по строке на тело: `id, тип, действие, причина`.

### 1.4 Библиотека `g4scene` (C++)

```
cpp/g4scene/
  include/g4scene/Transform.hh
  include/g4scene/Registry.hh
  include/g4scene/Materials.hh
  src/Transform.cc  src/Registry.cc  src/Materials.cc
  tests/test_transform.cc
```

```cpp
// include/g4scene/Transform.hh
#pragma once
#include <array>
#include "G4Transform3D.hh"
#include "G4LogicalVolume.hh"
#include "G4VPhysicalVolume.hh"

namespace scene {
using Mat3 = std::array<std::array<double, 3>, 3>;   // по строкам, как в JSON
inline constexpr Mat3 kIdentity{{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}};

// Активное преобразование «тело → родитель». Бросает G4Exception, если
// матрица не ортонормированная или det != +1.
G4Transform3D Transform(const Mat3& m, const G4ThreeVector& t);

// Размещение через G4Transform3D (а не через G4RotationMatrix*, который
// Geant4 трактует как обратный поворот).
G4VPhysicalVolume* Place(G4LogicalVolume* lv, G4LogicalVolume* mother,
                         const G4String& name, const G4Transform3D& t);
}
```

```cpp
// src/Transform.cc
#include "g4scene/Transform.hh"
#include "G4PVPlacement.hh"
#include "G4Exception.hh"

namespace scene {
G4Transform3D Transform(const Mat3& m, const G4ThreeVector& t) {
  CheckRotation(m);                       // ортонормированность и det = +1, допуск 1e-9
  // столбцы матрицы = оси тела в системе родителя
  G4ThreeVector ex(m[0][0], m[1][0], m[2][0]);
  G4ThreeVector ey(m[0][1], m[1][1], m[2][1]);
  G4ThreeVector ez(m[0][2], m[1][2], m[2][2]);
  G4RotationMatrix r;
  r.rotateAxes(ex, ey, ez);
  return G4Transform3D(r, t);
}

G4VPhysicalVolume* Place(G4LogicalVolume* lv, G4LogicalVolume* mother,
                         const G4String& name, const G4Transform3D& t) {
  return new G4PVPlacement(t, lv, name, mother, false, 0, false);
}
}
```

**Обязательный юнит-тест** `tests/test_transform.cc` (без него этап 2 опасен):

- поворот на 90° вокруг z: `Transform(Rz90, 0) * Point3D(1, 0, 0) == (0, 1, 0)`;
- поворот + сдвиг: точка сначала поворачивается, потом сдвигается;
- `r(i, j) == m[i][j]` для произвольной ортонормированной матрицы;
- матрица с det = −1 бросает исключение.

`Registry` — словари `id → G4Material*` и `id → G4LogicalVolume*` с понятной ошибкой «материал 'steel' не найден». `Materials.cc` — пока одна функция `Nist(name)`, которая вызывает `G4NistManager::Instance()->FindOrBuildMaterial(name)` и бросает исключение, если вернулся `nullptr`.

### 1.5 Что генерируется

```
out/geant4/
  CMakeLists.txt
  generated/
    GeneratedDetectorConstruction.hh
    GeneratedDetectorConstruction.cc
    ExpectedChecks.hh            # объёмы и пробные точки для стенда
  user/
    DetectorConstruction.hh      # пишется, только если его ещё нет
  app/                           # профиль standalone
    main.cc  ActionInitialization.hh/.cc  PrimaryGeneratorAction.hh/.cc
    vis.mac
  harness/check_geometry.cc
  g4scene/                       # копия cpp/g4scene
  report.json
```

Пример для куба Никиты — так должен выглядеть результат:

```cpp
// GENERATED by mcscene 0.1.0 from kub.json (format 0.1, sha256 1f3c…) — DO NOT EDIT
#include "GeneratedDetectorConstruction.hh"
#include "G4Box.hh"
#include "G4SystemOfUnits.hh"

G4VPhysicalVolume* GeneratedDetectorConstruction::Construct() {
  BuildMaterials();
  ConfigureMaterials();                 // хук для user/
  auto* world = BuildWorld();
  BuildBody_Body();
  PostConstruct(LV("world"));           // хук для user/
  return world;
}

void GeneratedDetectorConstruction::BuildMaterials() {
  fReg.AddMaterial("air",  scene::Nist("G4_AIR"));
  fReg.AddMaterial("iron", scene::Nist("G4_Fe"));
}

G4VPhysicalVolume* GeneratedDetectorConstruction::BuildWorld() {
  // тела занимают [-25, -25, 0]..[25, 25, 50] мм, запас 10 %
  auto* solid = new G4Box("world", 27.5*mm, 27.5*mm, 55*mm);
  auto* lv    = new G4LogicalVolume(solid, Mat("air"), "world");
  fReg.AddVolume("world", lv);
  return new G4PVPlacement(nullptr, G4ThreeVector(), lv, "world", nullptr, false, 0);
}

// Тело "Body" — «Тело», Железо (NIST)
void GeneratedDetectorConstruction::BuildBody_Body() {
  // коробка 50 × 50 × 50 мм (G4Box берёт половины)
  auto* solid = new G4Box("Body", 25*mm, 25*mm, 25*mm);
  auto* lv    = new G4LogicalVolume(solid, Mat("iron"), "Body");
  scene::Place(lv, LV("world"), "Body",
               scene::Transform(scene::kIdentity, G4ThreeVector(0*mm, 0*mm, 25*mm)));
  fReg.AddVolume("Body", lv);
}
```

**Правила печати** (`backends/geant4/printer.py`):

- числа: целое значение → `25`, иначе `repr(x)` (кратчайшее точное), `-0.0` → `0`;
- единицы всегда явные: `*mm`, `*deg`;
- тела в порядке массива `bodies`, но родитель всегда раньше ребёнка (топологическая сортировка, при равенстве — порядок в файле);
- комментарий над каждым телом: `id`, `name`, материал, размеры, как в JSON;
- никаких дат и абсолютных путей; в шапке версия генератора, `format_version`, sha256 входа.

Для неизменного каркаса (CMakeLists, `main.cc`, шапки файлов) хватит `string.Template` из стандартной библиотеки, шаблоны в `backends/geant4/templates/`. Тела печатайте из Python-кода, а не шаблонами.

`user/DetectorConstruction.hh` генератор создаёт **только если файла нет**: наследник `GeneratedDetectorConstruction` с пустыми хуками. Дальше это файл пользователя.

### 1.6 Стенд проверки и пробные точки

Стенд — отдельная программа `check_geometry` в том же CMake-проекте. Она строит геометрию без запуска физики и возвращает 0 или 1.

Генератор пишет `ExpectedChecks.hh`:

```cpp
namespace expected {
struct Volume { const char* name; double cad_volume; double rel_tol; };
struct Probe  { double x, y, z; const char* volume; const char* material; };
inline const Volume kVolumes[] = { {"Body", 125000.0, 1e-6} };
inline const Probe  kProbes[]  = { {0, 0, 25, "Body", "G4_Fe"},
                                   {10, 10, 35, "Body", "G4_Fe"}, /* ... */ };
}
```

**Пробные точки** — главная автоматическая проверка поворотов, нужна уже на этапе 1. Генератор считает их в Python для каждого тела **без детей**:

- коробка: центр и 8 точек в локальных (±0.4·sx, ±0.4·sy, ±0.4·sz);
- (этап 2) сплошной цилиндр: центр, точки на оси при ±0.4·H, точки на 0.5·R по x и y;
- (этап 2) сфера: центр и 6 точек на 0.5·R по осям.

Локальная точка p переводится в мировые координаты через цепочку родителей: p_мир = R₁·(R₂·p + t₂) + t₁ … Ожидается, что Geant4 найдёт в этой точке именно это тело и его материал. Если перепутана матрица или ось, у несимметричной коробки 20×40×70 угловые точки окажутся снаружи, и тест упадёт.

```cpp
// harness/check_geometry.cc
#include "GeneratedDetectorConstruction.hh"
#include "ExpectedChecks.hh"
#include "G4PhysicalVolumeStore.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4Navigator.hh"

int main() {
  GeneratedDetectorConstruction dc;
  G4VPhysicalVolume* world = dc.Construct();
  int bad = 0;

  for (auto* pv : *G4PhysicalVolumeStore::GetInstance())          // 1. перекрытия
    if (pv != world && pv->CheckOverlaps(100000, 0., true, 1)) ++bad;

  for (const auto& e : expected::kVolumes) {                       // 2. объёмы
    auto* lv = G4LogicalVolumeStore::GetInstance()->GetVolume(e.name, false);
    double v = lv->GetSolid()->GetCubicVolume();
    if (std::abs(v - e.cad_volume) > e.rel_tol * e.cad_volume) {
      G4cerr << "VOLUME " << e.name << ": " << v << " vs " << e.cad_volume << G4endl; ++bad;
    }
  }

  G4Navigator nav;                                                 // 3. пробные точки
  nav.SetWorldVolume(world);
  for (const auto& p : expected::kProbes) {
    auto* pv = nav.LocateGlobalPointAndSetup(G4ThreeVector(p.x, p.y, p.z), nullptr, false, true);
    const auto vol = pv ? pv->GetName() : G4String("<outside>");
    const auto mat = pv ? pv->GetLogicalVolume()->GetMaterial()->GetName() : G4String("-");
    if (vol != p.volume || mat != p.material) {
      G4cerr << "PROBE (" << p.x << "," << p.y << "," << p.z << "): " << vol << "/" << mat
             << ", expected " << p.volume << "/" << p.material << G4endl; ++bad;
    }
  }
  G4cout << (bad ? "FAILED: " : "OK: ") << bad << " problems" << G4endl;
  return bad ? 1 : 0;
}
```

`CheckOverlaps` выборочный: «OK» не доказывает, что пересечений нет. Поэтому 100 000 точек и число точек пишется в отчёт.

### 1.7 Демо-приложение (профиль standalone)

Минимум из примера B1, упрощённый:

- `main.cc`: `G4RunManagerFactory::CreateRunManager()`, `DetectorConstruction` из `user/`, физический лист `QBBC`, `ActionInitialization`, `G4UIExecutive` + `G4VisExecutive`, выполнение `vis.mac`.
- `PrimaryGeneratorAction`: `G4ParticleGun` с geantino, вылетающим с края мира к центру.
- `vis.mac`: `/run/initialize`, `/vis/open`, `/vis/drawVolume`, `/vis/viewer/set/style surface`, `/vis/scene/add/axes`.

Цвета по материалам можно задать в генераторе через `G4VisAttributes` (цвет — хеш от `id` материала). Не обязательно, но на демо так нагляднее.

### 1.8 CMakeLists (генерируется)

```cmake
cmake_minimum_required(VERSION 3.16)
project(scene_kub CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})

add_library(scene_geometry STATIC
  generated/GeneratedDetectorConstruction.cc
  g4scene/src/Transform.cc g4scene/src/Registry.cc g4scene/src/Materials.cc)
target_include_directories(scene_geometry PUBLIC generated user g4scene/include)
target_link_libraries(scene_geometry PUBLIC ${Geant4_LIBRARIES})

add_executable(check_geometry harness/check_geometry.cc)
target_link_libraries(check_geometry scene_geometry)

add_executable(scene_app app/main.cc app/ActionInitialization.cc app/PrimaryGeneratorAction.cc)
target_link_libraries(scene_app scene_geometry)
configure_file(app/vis.mac ${CMAKE_BINARY_DIR}/vis.mac COPYONLY)

enable_testing()
add_test(NAME geometry COMMAND check_geometry)
```

Списки файлов пишите явно (генератор их знает), без `file(GLOB …)`.

### 1.9 Команда `generate` и сквозной скрипт

```
mcscene generate scene.json -t geant4 -o out/kub [--force]
```

Порядок: `load_and_validate` → проходы → `check` (любой ERROR → выход 1, файлы не пишутся) → план → принтер → копия `g4scene` → `report.json` (пока минимальный: вход, sha256, версии, список тел).

`--force` перезаписывает `generated/`, `harness/`, `app/`, `g4scene/`, но **никогда** `user/`.

```bash
# tools/e2e.sh — прогон всех сцен целиком
set -euo pipefail
for scene in tests/scenes/*.json tests/fixtures/freecad/*/scene.json; do
  name=$(basename "$(dirname "$scene")")_$(basename "$scene" .json)
  out=build/e2e/$name
  mcscene generate "$scene" -t geant4 -o "$out" --force
  cmake -S "$out" -B "$out/build" -DCMAKE_BUILD_TYPE=Release > /dev/null
  cmake --build "$out/build" -j > /dev/null
  (cd "$out/build" && ./check_geometry) && echo "OK   $name" || { echo "FAIL $name"; exit 1; }
done
```

### 1.10 Тесты этапа

- **Golden:** `tests/golden/<сцена>/geant4/…` — эталонные файлы. Тест генерирует во временную папку и сравнивает. Обновление эталонов — `UPDATE_GOLDEN=1 pytest`, а изменения в эталонах смотрите глазами в diff перед коммитом.
- **Детерминизм:** две генерации одной сцены дают одинаковые байты.
- **Стенд ловит ошибку:** сцена `tests/scenes/overlap_debug.json` с двумя пересекающимися коробками. `validate.py` её отвергнет, поэтому у `generate` есть отладочный флаг `--unsafe-skip-checks` (пишется в отчёт и шапку). Тест: с этим флагом сцена генерируется, а `check_geometry` возвращает 1.
- **Сквозной:** `tools/e2e.sh` (медленный, запускаете перед коммитом и перед встречей).

### Этап 1 готов, когда

- Куб Никиты и его коробка 20×40×70 проходят `tools/e2e.sh`: собираются, стенд = 0, пробные точки попадают куда надо.
- В визуализации `scene_app` видно тело с правильными размерами и положением.
- Две генерации совпадают байт в байт; сцена с перекрытием валит стенд.
- **Демо:** поменять размер в JSON → `mcscene generate --force` → `cmake --build` → изменение видно в окне Geant4.

**От Никиты:** `Part::Box` 20×40×70, сдвинутый по всем трём осям, например Placement (300, −150, 80), материал железо. Разные размеры по осям нужны, чтобы поймать перепутанные оси. **Заранее попросите** повёрнутую версию той же коробки (понадобится в начале этапа 2) — ему нужно время на распознавание по геометрии, а не по мировому bbox.

**Типичные ошибки:** передать в `G4Box` полные размеры; забыть, что FreeCAD ставит коробку от угла (это пересчитывает Никита, но проверяют пробные точки); размещать через `G4RotationMatrix*` вместо `G4Transform3D`.

---

## Этап 2. Повороты и примитивы (2–15 ноября)

**Цель:** все примитивы v0.1, вложенность через `parent` и тест, который ловит перепутанный поворот.

### 2.1 Примитивы → Geant4

| JSON | Geant4 | Параметры |
|---|---|---|
| `cylinder` | `G4Tubs` | `(name, inner_radius, radius, height/2, 0*deg, 360*deg)` |
| `cone` | `G4Cons` | `(name, inner_radius_bottom, radius_bottom, inner_radius_top, radius_top, height/2, 0*deg, 360*deg)`; bottom — при z = −h/2 |
| `sphere` без `inner_radius` | `G4Orb` | `(name, radius)` |
| `sphere` с `inner_radius` | `G4Sphere` | `(name, inner_radius, radius, 0*deg, 360*deg, 0*deg, 180*deg)` |
| `torus` | `G4Torus` | `(name, 0, minor_radius, major_radius, 0*deg, 360*deg)` |

Половинки — только у `G4Box` и высот (`height/2`); радиусы передаются как есть. Для каждого — фикстура в `tests/scenes/`, golden и проверка объёма с допуском 1e-6: для этих тел Geant4 считает объём точно.

Пробные точки: сплошной цилиндр и сфера — как в 1.6; полый цилиндр, полая сфера, конус, тор — точки в «толще стенки» (например, у тора — на окружности радиуса `major_radius` в плоскости z = 0).

Отдельно проверьте **острый конус** (`radius_top = 0`): соберите и убедитесь, что Geant4 его принимает.

### 2.2 Вложенность

- Мать тела = `LV(parent)` или `LV("world")`.
- Тела печатаются так, что родитель раньше ребёнка (топологическая сортировка уже есть с этапа 1).
- `transform` ребёнка — относительно родителя, цепочка уже учитывается в пробных точках.
- Пробные точки ставятся только в тела без детей. В теле-родителе ставьте точку там, где детей точно нет (например, у трубы с вакуумом — в стенке между R = 55 и R = 60).

### 2.3 Тест-ловушка поворотов

Сцена `tests/scenes/rotation_trap.json`:

```
world
└─ A  коробка 300×200×100, поворот R1 = Rx(90°) затем Rz(90°), сдвиг (100, 50, 0)
   └─ B  коробка 120×60×30, поворот R2 = Ry(90°), сдвиг (60, 0, 20) в системе A
      └─ M  «маркер» коробка 10×10×10, без поворота, сдвиг (40, 15, 0) в системе B
```

Все размеры разные, все сдвиги несимметричные — любая перестановка осей или замена матрицы на обратную сдвинет маркер. Пробные точки генерируются автоматически (1.6). Дополнительно:

- [ ] Вручную (на бумаге или в Python-тесте) посчитайте мировой центр M: p = R1·(R2·(40, 15, 0) + (60, 0, 20)) + (100, 50, 0) и сравните с тем, что генератор положил в `ExpectedChecks.hh`. Это проверяет сам Python-расчёт.
- [ ] Один раз нарочно сломайте `scene::Transform` (передайте транспонированную матрицу) и убедитесь, что `check_geometry` падает. Запишите результат в `docs/notes.md` — это доказательство, что тест работает (пригодится в отчёте).

### 2.4 Повороты из FreeCAD

Когда придёт повёрнутая коробка Никиты, проверьте три вещи:

1. `validate.py` проходит (bbox и объём сходятся).
2. Пробные точки сходятся в Geant4.
3. В визуализации коробка выглядит так же, как во FreeCAD (сделайте два скриншота с одного ракурса — пригодится для отчёта).

### Этап 2 готов, когда

- У каждого примитива есть фикстура, golden и точное совпадение объёма.
- `rotation_trap.json` проходит, а с нарочно сломанной матрицей — падает.
- Повёрнутая коробка, повёрнутый цилиндр и труба с вакуумом от Никиты проходят `tools/e2e.sh`.
- `mcscene check` показывает LEGAL для всех примитивов.

**От Никиты:**

1. Повёрнутая коробка 20×40×70 (поворот вокруг двух осей, например 30° вокруг X и 45° вокруг Z).
2. `Part::Cylinder` R = 40, H = 200, повёрнутый на 90° вокруг Y и сдвинутый.
3. Труба с вакуумом: **сплошной** стальной цилиндр R = 60, H = 1000 и ребёнок — цилиндр R = 55, H = 990 из `G4_Galactic` с `parent`. Не полый цилиндр с `inner_radius` + вакуум: вакуум в отверстии полой трубы лежит вне её формы.
4. По возможности: `Part::Cone`, `Part::Sphere`, `Part::Torus` по одному.

**Типичные ошибки:** перепутать порядок Эйлера (по контракту R = Rz·Ry·Rx); у `G4Cons` перепутать низ и верх; полуширина у радиусов.

---

## Этап 3. Материалы и булевы операции (16–29 ноября)

**Цель:** свои материалы с составом и булевы деревья.

### 3.1 Свои материалы

`g4scene::MaterialFactory`:

```cpp
// basis = mass: AddElement(element, fractionmass)
// basis = atom: перевести атомные доли в массовые: w_i = x_i·A_i / Σ x_j·A_j,
//               A_i брать из G4Element::GetA() — так нет своей таблицы масс
G4Material* Custom(const G4String& id, double density_g_cm3, G4State state,
                   const std::vector<Component>& comps, bool atomBasis);
```

Генератор печатает:

```cpp
fReg.AddMaterial("steel_304", scene::Custom("steel_304", 7.93, kStateSolid, {
    {"Fe", 0.695}, {"Cr", 0.190}, {"Ni", 0.095}, {"Mn", 0.020}}, /*atomBasis=*/false));
```

Проверки в генераторе (Python):

- сумма долей = 1 с допуском 1e-3, иначе `W501` (Geant4 сам нормирует доли, но расхождение почти всегда ошибка ввода);
- `nist` — существующее имя Geant4, иначе `E311`. Список имён один раз выгрузите маленькой утилитой `cpp/tools/g4nist_names.cc` (`G4NistManager::Instance()->GetNistMaterialNames()`) в `python/mcscene/materials/g4_nist_names.txt` и закоммитьте;
- если у материала есть и `nist`, и `composition`, для Geant4 используйте `nist`, а в отчёт — пометку `I410`.

### 3.2 Булевы деревья

Правило из контракта: `transform` операндов задан в системе тела. В Geant4 `G4SubtractionSolid(name, A, B, T)` ставит B с преобразованием T в систему A. Поэтому:

1. Каждый операнд строится рекурсивно как отдельный solid в своей системе.
2. Если у **левого** операнда есть `transform` (не единичный), заверните его в `G4DisplacedSolid(name, solid, T_left)` — тогда A уже в системе тела.
3. Правый операнд передаётся с `T_right` как `G4Transform3D`.
4. Имена подтел: `<id>__l`, `<id>__r`, `<id>__l_r` и т.д. — стабильные и уникальные.

```cpp
// пример: стена минус отверстие (03_boolean_wall)
auto* wall_l = new G4Box("wall_b__l", 250*mm, 1500*mm, 1000*mm);
auto* wall_r = new G4Tubs("wall_b__r", 0*mm, 100*mm, 300*mm, 0*deg, 360*deg);
auto* solid  = new G4SubtractionSolid("wall_b", wall_l, wall_r,
                 scene::Transform({{{0, 0, 1}, {0, 1, 0}, {-1, 0, 0}}}, G4ThreeVector()));
```

Объём булевых тел Geant4 оценивает методом Монте-Карло, поэтому допуск в стенде ~1e-2. Пробные точки для булевых тел на этом этапе можно не ставить или ставить только в заведомо целые места (центр левого операнда, если он не вырезан).

Фикстуры: `subtract` (стена с отверстием), `union` (две коробки внахлёст), `intersect` (коробка ∩ сфера), вложенная операция (A − B − C), левый операнд с `transform`.

### 3.3 Материалы в контрольных точках

Пробные точки уже проверяют материал (1.6). Для сцены «стальная труба + вакуум» убедитесь, что в стенке — `steel_304`, в канале — `G4_Galactic`, снаружи — `G4_AIR`.

### Этап 3 готов, когда

- `Part::Cut` из FreeCAD доходит до Geant4, объём в пределах 1 %.
- Сцена со своими материалами даёт правильные материалы во всех пробных точках.
- Все булевы фикстуры проходят `tools/e2e.sh`.

**От Никиты:**

1. `Part::Cut`: блок минус цилиндр; цилиндр длиннее блока, чтобы грани не совпадали.
2. Два тела в одном файле с разными материалами, назначенными через свойство объекта (например, `JINR_Material`), касающиеся, но не пересекающиеся.
3. По возможности: `Part::Fuse` и `Part::Common`.

**Попросите** описать в двух строчках, как во FreeCAD назначается материал, и добавьте это в `docs/`.

**Типичные ошибки:** перепутать, в чьей системе задан `transform` правого операнда; забыть `G4DisplacedSolid` для левого; ждать точный объём от булевого тела.

---

## Этап 4. Меши и отчёт (30 ноября – 13 декабря)

**Цель:** тело-меш доходит до Geant4; у каждого прогона есть отчёт.

### 4.1 Проверка STL до генерации (Python)

`validate.py` уже проверяет замкнутость, sha256 и число граней. Генератор добавляет:

- объём по STL (сумма знаковых объёмов тетраэдров от начала координат) против `cad_volume`, допуск по умолчанию 2 % → `W510`;
- знак объёма > 0 (нормали наружу), иначе `E320`;
- вырожденные треугольники (площадь ≈ 0) → `W511`.

STL копируется в `out/geant4/meshes/<id>.stl` под стабильным именем.

### 4.2 Загрузчик в `g4scene`

Свой читатель без внешних библиотек:

- двоичный STL: 80 байт заголовка, `uint32` число треугольников, по 50 байт на треугольник (нормаль 12 байт, 3 вершины по 12 байт, 2 байта атрибута), little-endian;
- текстовый: `facet normal … outer loop vertex x y z ×3 endloop endfacet`.
- Формат брать из поля `encoding`, а не угадывать.

```cpp
G4TessellatedSolid* LoadStl(const G4String& name, const std::string& path, bool binary) {
  auto* s = new G4TessellatedSolid(name);
  for (const auto& t : ReadTriangles(path, binary))            // мм
    s->AddFacet(new G4TriangularFacet(t[0]*mm, t[1]*mm, t[2]*mm, ABSOLUTE));
  s->SetSolidClosed(true);
  return s;
}
```

Порядок вершин в STL — против часовой стрелки при взгляде снаружи; Geant4 ждёт того же. Путь к мешам: CMake копирует `meshes/` в папку сборки, а в код передаётся `target_compile_definitions(scene_geometry PRIVATE MCSCENE_MESH_DIR="${CMAKE_BINARY_DIR}/meshes")`. Меш читается при запуске, поэтому замена STL не требует перекомпиляции.

Объём `G4TessellatedSolid` Geant4 считает по граням; допуск в стенде — как в 4.1.

### 4.3 Отчёт

`report.json` (для машин) и `report.md` (для людей и для отчёта по практике):

- вход: файл, sha256, `format_version`, экспортёр и его версия;
- генератор: версия, цель, профиль, флаги;
- таблица тел: `id`, имя, тип формы, представление (примитив / булево / меш), материал, имя в Geant4, `cad_volume`;
- таблица мешей: тело, причина (`fallback_reason`), число граней, объём STL против `cad_volume`;
- материалы: `id`, NIST или состав, плотность;
- все диагностики;
- раздел «Проверка в Geant4» заполняется после стенда.

Команда `mcscene verify out/geant4` — обёртка над `cmake` + сборка + `check_geometry`, которая дописывает результат стенда в `report.md`/`report.json` (число точек `CheckOverlaps`, объёмы, пробные точки). По сути это `tools/e2e.sh` для одной сцены.

### 4.4 `mcscene check` в полном виде

```
$ mcscene check scene.json -t geant4
id           тип       действие  примечание
wall_b       boolean   LEGAL
pipe         cylinder  LEGAL
pipe_bore    cylinder  LEGAL
magnet_yoke  mesh      LEGAL     STL 18432 граней, причина SPLINE_SURFACE
итог: 4 тела, 0 ошибок
```

На встречах это удобная таблица прогресса.

### Этап 4 готов, когда

- Деталь со скруглением от Никиты доходит до Geant4, стенд = 0, объём в допуске.
- Битый STL (из `bad/`) даёт понятную ошибку до генерации.
- После `mcscene verify` у каждой сцены есть `report.md` с итогом стенда.

**От Никиты:** деталь со скруглением (`Part::Fillet` или PartDesign Fillet) → двоичный STL с `sha256`, `n_facets`, `tessellation`, `fallback_reason`. По возможности — деталь, импортированная из STEP.

**Если не успеваете:** урезайте отчёт до `report.json` и таблицы тел, а `verify` замените скриптом. Загрузчик STL урезать нельзя.

**Типичные ошибки:** STL в мировых координатах вместо локальных (по контракту — локальные, до `transform` тела); забыть `SetSolidClosed(true)`; абсолютный путь к мешу в коде.

---

## Этап 5. MVP (14–20 декабря)

**Цель:** реальная модель проходит весь путь, есть демо и материал для отчёта.

- [ ] **Реальная сцена.** Никита выгружает модель из нескольких тел: вложенность, разные материалы, хотя бы одно булево тело и один меш. Лучше всего — реальная деталь отдела (попросите у руководителя заранее, на этапе 3).
- [ ] **Профиль `library`.** `mcscene generate … --profile library` пишет только `generated/`, `g4scene/` и CMake-цель `scene_geometry` без `app/`. В README — три строчки, как подключить эту цель к существующему приложению.
- [ ] **CI** (GitHub Actions, два задания):
  - `python`: `pip install -e .[dev]` → `pytest` (юнит, контракт, golden, детерминизм);
  - `geant4`: micromamba + conda-forge `geant4` → `tools/e2e.sh`.
  Если задание с Geant4 не получится за день — оставьте только первое, а `e2e.sh` запускайте локально перед каждым слиянием.
- [ ] **README** для пользователя: установка, три команды (`validate`, `generate`, `verify`), как открыть визуализацию.
- [ ] **Демо-сценарий** (5 минут): модель во FreeCAD → экспорт → `mcscene check` → `generate` → сборка → окно Geant4 с моделью и пролётом частиц → `report.md`.
- [ ] **Материал для отчёта по практике:** архитектура (схема из плана v2), контракт, что реализовано, таблица фикстур (сколько, каких типов), скриншоты FreeCAD и Geant4 с одного ракурса, пример `report.md`, доказательство работы ловушки поворотов.

### Этап 5 готов, когда

- Реальная модель Никиты проходит `tools/e2e.sh` без ручных правок.
- Демо показано руководителю.
- Текст для отчёта по практике собран в `docs/practice-report.md`.

**От Никиты:** сцена из нескольких тел (желательно реальная деталь отдела); по желанию — кнопка во FreeCAD, которая после экспорта запускает `mcscene generate` отдельным процессом (путь к `mcscene` в настройках аддона).

---

## Этап 6. Вторая цель (с января, около 6 недель)

**Начать с решения.** До января получите от руководителя ответ: какой FLUKA используется в отделе и есть ли установка для проверки; нужен ли MCNP. Если доступа к FLUKA нет — вторая цель OpenMC.

Дальше — по плану v1 (раздел про Region IR), коротко:

| Неделя | Что делаете | Проверка |
|---|---|---|
| 1 | **Уплощение:** мировые преобразования R_мир = R_род·R_реб, t_мир = R_род·t_реб + t_род; `inside(тело, точка)` на Scene IR для всех фигур (это оракул) | юнит-тесты `inside` против пробных точек Geant4 на тех же сценах |
| 2 | **Region IR:** нейтральные тела в мировых координатах (RPP, RCC, TRC, SPH, плоскость; тор по осям — для OpenMC), зоны и регионы; понижение примитивов (повёрнутая коробка → 6 плоскостей, цилиндр → опорная точка V = C − H/2) | оракул: точка внутри тела ⇔ внутри понижённого выражения |
| 3 | **Регионы:** «родитель минус дети» через конверты, регион мира, внешняя граница (OpenMC: `boundary_type="vacuum"`; FLUKA: BLCKHOLE) | оракул: каждая случайная точка ровно в одном регионе с правильным материалом |
| 4 | **Принтер:** OpenMC — `model.py` на Python API (`openmc.Material`, поверхности, `openmc.Cell`, `export_to_model_xml`) или FLUKA — `model.inp` (COMBNAME, см, имена ≤ 8 символов) | разбор напечатанного текста + оракул по нему, а не по Region IR в памяти |
| 5 | **Материалы для цели:** раскрыть NIST-материалы в составы по таблицам Geant4 (утилита `g4nist_dump`), карты материалов цели | массы материалов совпадают с Geant4 |
| 6 | **Сверка и запас** | все фикстуры без мешей проходят; торы и меши дают понятный ERROR |

Для диплома дальше: физическая сверка Geant4 и второй программы на одной простой задаче защиты (доза за бетонной плитой от точечного источника) из одного JSON.

---

## Что нужно от Никиты: сводная таблица

| Когда нужно | Образец | Что проверяет | Где ляжет |
|---|---|---|---|
| есть | куб 50 мм (`PartDesign::Body`) | центр из угла, единицы | `tests/scenes/kub.json` |
| до 19 окт | `Part::Box` 20×40×70, Placement (300, −150, 80) | полные размеры, оси не перепутаны | `fixtures/freecad/02_box_20x40x70/` |
| до 2 ноя | та же коробка, повёрнутая вокруг двух осей | распознавание по геометрии, матрица | `fixtures/freecad/03_box_rotated/` |
| до 9 ноя | `Part::Cylinder` R 40, H 200, поворот 90° вокруг Y | ось цилиндра, центр основания → центр | `fixtures/freecad/04_cylinder_rotated/` |
| до 9 ноя | сплошная стальная труба R 60 + вакуум R 55 (`parent`) | иерархия, transform относительно родителя | `fixtures/freecad/05_pipe_vacuum/` |
| до 15 ноя (по возможности) | `Part::Cone`, `Part::Sphere`, `Part::Torus` | параметры остальных примитивов | `fixtures/freecad/06_…/` |
| до 16 ноя | `Part::Cut`: блок − цилиндр длиннее блока | булево дерево | `fixtures/freecad/07_cut/` |
| до 23 ноя | два тела с разными материалами через свойство объекта | назначение материалов | `fixtures/freecad/08_two_materials/` |
| до 30 ноя | деталь с Fillet → двоичный STL | меш, sha256, причина | `fixtures/freecad/09_fillet_mesh/` |
| до 14 дек | реальная сцена из нескольких тел | всё вместе | `fixtures/freecad/10_real_scene/` |

Каждый образец: `.FCStd` + `scene.json` (+ `meshes/`), проходит `validate.py --strict` до отправки.

## Что спросить у руководителя и когда

| До | Вопрос |
|---|---|
| этапа 1 | Какая версия Geant4 на машинах отдела? |
| этапа 3 | Реальные составы бетонов и сталей ОИЯИ; можно ли получить реальную деталь для этапа 5? |
| этапа 5 | Встраивать сгенерированный код в существующее приложение (профиль `library`) или отдельное приложение? Что входит в отчёт по практике? |
| января | Какой FLUKA в отделе, есть ли установка; нужен ли MCNP или достаточно OpenMC? |
