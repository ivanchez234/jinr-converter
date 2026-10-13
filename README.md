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
```

Подробнее, включая установку Geant4, — в `docs/setup.md`.

## Кто что делает

- Иван — выходной модуль: `mcscene`, генерация и проверка в Geant4.
- Никита — входной модуль: аддон FreeCAD и экспорт `scene.json`.

## Статус

Этап 0 (каркас), октябрь 2026. План по этапам — `docs/output-module-step-plan.md`, установка окружения — `docs/setup.md`.
