# Отладочные сцены

Сцены, которые **нарушают** контракт нарочно. Они нужны, чтобы доказать, что стенд `check_geometry` действительно ловит ошибки, а не всегда говорит OK.

`validate.py` такие сцены отвергает, поэтому генерировать их можно только с флагом `--unsafe-skip-checks` (он пропускает геометрические ошибки E220, E240, E250, E251 и помечает это в шапке каждого файла и в `report.json`).

| Файл | Что нарушено | Что должен сказать стенд |
|---|---|---|
| `overlap_debug.json` | свинцовый куб B заходит в железный куб A на 40 мм (E251) | `CheckOverlaps` находит перекрытие, `check_geometry` возвращает 1 |

`tools/e2e.sh` (без аргументов) прогоняет их сам и считает успехом именно падение стенда.

Вручную:

```bash
mcscene generate tests/debug/overlap_debug.json -o out/overlap --unsafe-skip-checks
cmake -S out/overlap -B out/overlap/build && cmake --build out/overlap/build -j$(nproc)
out/overlap/build/check_geometry; echo "код $?"      # ожидается FAILED и код 1
```
