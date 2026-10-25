# jinr-converter

Конвертер геометрии из FreeCAD в программы Монте-Карло: сначала Geant4, затем OpenMC или FLUKA.

```
FreeCAD (аддон JINRScene) → scene.json + meshes/ (формат jinr-mc-scene v0.1) → mcscene → C++ проект Geant4
```

Геометрию рисуют во FreeCAD, аддон выгружает её в `scene.json` по контракту, а генератор `mcscene` печатает из него читаемый C++ код для Geant4, собирает его и проверяет.

## Структура

| Папка | Что там |
|---|---|
| `contracts/scene/v0.1/` | контракт формата: `КОНТРАКТ.md`, `scene.schema.json`, `validate.py`, примеры |
| `python/mcscene/` | генератор (Python) |
| `python/mcscene/backends/geant4/templates/` | шаблоны Jinja2: весь текст, который пишет генератор для Geant4 («пакет диалекта») |
| `cpp/g4scene/` | вспомогательная библиотека для сгенерированного кода (C++) |
| `inputs/freecad/` | аддон FreeCAD (появится позже) |
| `tests/` | тесты и образцы сцен |
| `tools/` | скрипты, например сквозной прогон `e2e.sh` |
| `docs/` | установка, план работ, заметки |

## Быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
mcscene validate --strict scene.json      # сцена соответствует контракту?
mcscene check scene.json                  # что генератор Geant4 сделает с каждым телом
mcscene check scene.json --plan           # + план генерации: мир, материалы, тела, пробные точки
mcscene generate scene.json -o out/hall   # записать C++ проект Geant4 (компиляция — отдельно)
tools/e2e.sh                              # все тестовые сцены: генерация -> сборка -> стенд
```

Подробнее, включая установку Geant4, — в `docs/setup.md`.

## Из Python (так генератор будет вызывать аддон FreeCAD)

```python
from mcscene import Converter

result = Converter("geant4").generate("scene.json", "out/model")
if result.ok:
    print("готово:", result.out_dir)
else:
    for d in result.diagnostics:          # ошибки — списком, ничего не печатается само
        print(d.level, d.code, d.where, d.message)
```

`mcscene` в терминале — обёртка над тем же `Converter`. Список целей — `mcscene targets`.

## Кто что делает

- Иван — выходной модуль: `mcscene`, генерация и проверка в Geant4.
- Никита — входной модуль: аддон FreeCAD и экспорт `scene.json`.

## Статус

Этапы 0–1 сделаны: коробки из FreeCAD доходят до Geant4 и проверяются стендом. Этап 2 (октябрь 2026): генерация через шаблоны Jinja2 и переход на классы. План — `docs/output-module-step-plan.md`, почему Jinja2 — `docs/decisions/001-template-engine.md`, установка окружения — `docs/setup.md`.
