#!/usr/bin/env bash
# Нарочно ломает то, как g4scene понимает матрицу поворота, и смотрит, поймает ли это стенд.
#
#   source .venv/bin/activate
#   tools/break_matrix.sh tests/scenes/rotation_trap.json    # стенд должен упасть
#   tools/break_matrix.sh tests/scenes/rotated_box.json      # поворот на 90°: стенд НЕ падает,
#                                                            # поэтому и нужна ловушка
#
# Что ломается. Проект генерируется в build/break/<сцена>/, и в его копии
# g4scene/src/Transform.cc функция ToRotation берёт СТРОКИ матрицы вместо столбцов.
# Geant4 получает транспонированную матрицу: это ровно ошибка «перепутали строки и
# столбцы» (или «перепутали поворот тела и поворот системы»). Исходники в cpp/g4scene
# и проекты из tools/e2e.sh (build/e2e/) не трогаются.
#
# Код выхода:
#   0 — стенд упал, то есть ошибку поймал (этого и ждём на ловушке и коробке 30°/45°);
#   1 — стенд прошёл, то есть ошибку НЕ заметил;
#   2 — сломалось что-то до стенда (генерация, правка файла, сборка): ответа нет.
# Подробности — в build/break/<сцена>.log. Вызывается из tools/e2e.sh.

set -eo pipefail
cd "$(dirname "$0")/.."

if [ $# -ne 1 ] || [ ! -f "$1" ]; then
  echo "использование: tools/break_matrix.sh сцена.json"
  exit 2
fi
scene="$1"

if ! command -v geant4-config >/dev/null 2>&1; then
  G4_SETUP="${G4_SETUP:-$HOME/geant4/install/bin/geant4.sh}"
  if [ ! -f "$G4_SETUP" ]; then
    echo "Geant4 не найден: нет geant4-config в PATH и нет $G4_SETUP (задайте G4_SETUP=/путь/к/geant4.sh)"
    exit 2
  fi
  # shellcheck disable=SC1090
  source "$G4_SETUP"
fi
if ! command -v mcscene >/dev/null 2>&1; then
  echo "mcscene не найден: сначала source .venv/bin/activate"
  exit 2
fi

if [ "$(basename "$scene")" = "scene.json" ]; then
  name="$(basename "$(dirname "$scene")")"
else
  name="$(basename "$scene" .json)"
fi
out="build/break/$name"
log="build/break/$name.log"
mkdir -p build/break
: > "$log"

if ! mcscene generate "$scene" -o "$out" --force >>"$log" 2>&1; then
  echo "generate не прошёл (см. $log)"; exit 2
fi

# Ломаем: столбцы m[*][j] -> строки m[j][*]
src="$out/g4scene/src/Transform.cc"
sed -i \
  -e 's/ex(m\[0\]\[0\], m\[1\]\[0\], m\[2\]\[0\])/ex(m[0][0], m[0][1], m[0][2])/' \
  -e 's/ey(m\[0\]\[1\], m\[1\]\[1\], m\[2\]\[1\])/ey(m[1][0], m[1][1], m[1][2])/' \
  -e 's/ez(m\[0\]\[2\], m\[1\]\[2\], m\[2\]\[2\])/ez(m[2][0], m[2][1], m[2][2])/' \
  "$src"
changed="$(grep -c -E 'e[xyz]\(m\[([012])\]\[0\], m\[\1\]\[1\], m\[\1\]\[2\]\)' "$src" || true)"
if [ "$changed" != "3" ]; then
  echo "правка $src не применилась (изменено строк: $changed из 3): ToRotation в cpp/g4scene переписали?"
  exit 2
fi
sed -i '1i // СЛОМАНО НАРОЧНО (tools/break_matrix.sh): ToRotation берёт строки матрицы вместо столбцов' "$src"
echo "== ToRotation после правки:" >>"$log"
grep -n 'G4ThreeVector e[xyz]' "$src" >>"$log"

jobs="$(nproc 2>/dev/null || echo 2)"
if ! cmake -S "$out" -B "$out/build" -DCMAKE_BUILD_TYPE=Release >>"$log" 2>&1; then
  echo "cmake не прошёл (см. $log)"; exit 2
fi
if ! cmake --build "$out/build" -j"$jobs" >>"$log" 2>&1; then
  echo "сборка не прошла (см. $log)"; exit 2
fi

echo "== check_geometry:" >>"$log"
if (cd "$out/build" && ./check_geometry) >>"$log" 2>&1; then
  echo "$name: стенд ПРОШЁЛ со сломанной матрицей — ошибку не заметил (см. $log)"
  exit 1
fi
echo "$name: стенд упал — перепутанную матрицу поймал. Что именно не сошлось:"
grep -E 'ОШИБКА|FAILED' "$log" | head -12 || true
exit 0
