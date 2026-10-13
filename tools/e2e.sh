#!/usr/bin/env bash
# Сквозной прогон: для каждой сцены mcscene generate -> cmake -> сборка -> check_geometry
# -> scene_app batch.mac (приложение строит геометрию без окна).
# Запускать из корня репозитория перед коммитом и перед встречей с руководителем:
#
#   source .venv/bin/activate
#   tools/e2e.sh                 # все сцены + проверка, что стенд ловит ошибки
#   tools/e2e.sh tests/scenes/kub.json      # только указанные
#
# Две части:
#   1. Хорошие сцены (tests/scenes, tests/fixtures/freecad): всё должно пройти.
#   2. Отладочные сцены с нарочными ошибками (tests/debug, только при запуске без
#      аргументов): генерируются с --unsafe-skip-checks, и стенд ОБЯЗАН упасть.
#      Если стенд сказал OK на сцене с перекрытием — это FAIL: стенд ничего не ловит.
#
# Geant4 подключается сам: если geant4-config не найден, берётся
# $G4_SETUP (по умолчанию $HOME/geant4/install/bin/geant4.sh).
# Результаты сборки — в build/e2e/<сцена>/ (папка build/ в git не попадает),
# лог каждой сцены — build/e2e/<сцена>.log.

set -eo pipefail
cd "$(dirname "$0")/.."

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

if [ $# -gt 0 ]; then
  scenes=("$@")
  debug_scenes=()
else
  scenes=(tests/scenes/*.json tests/fixtures/freecad/*/scene.json)
  debug_scenes=(tests/debug/*.json)
fi

mkdir -p build/e2e
jobs="$(nproc 2>/dev/null || echo 2)"
ok=0
failed=()

scene_name() {
  if [ "$(basename "$1")" = "scene.json" ]; then
    basename "$(dirname "$1")"
  else
    basename "$1" .json
  fi
}

# generate + cmake + сборка; при ошибке печатает FAIL и возвращает 1
build_scene() {
  local scene="$1" out="$2" log="$3"
  shift 3
  if ! mcscene generate "$scene" -o "$out" --force "$@" >>"$log" 2>&1; then
    echo "FAIL  generate   (см. $log)"; return 1
  fi
  if ! cmake -S "$out" -B "$out/build" -DCMAKE_BUILD_TYPE=Release >>"$log" 2>&1; then
    echo "FAIL  cmake      (см. $log)"; return 1
  fi
  if ! cmake --build "$out/build" -j"$jobs" >>"$log" 2>&1; then
    echo "FAIL  сборка     (см. $log)"; return 1
  fi
}

for scene in "${scenes[@]}"; do
  [ -f "$scene" ] || continue
  name="$(scene_name "$scene")"
  out="build/e2e/$name"
  log="build/e2e/$name.log"
  : > "$log"
  printf '%-28s ' "$name"

  build_scene "$scene" "$out" "$log" || { failed+=("$name"); continue; }
  if ! (cd "$out/build" && ./check_geometry) >>"$log" 2>&1; then
    echo "FAIL  стенд      (см. $log)"; failed+=("$name"); continue
  fi
  if ! (cd "$out/build" && ./scene_app batch.mac) >>"$log" 2>&1; then
    echo "FAIL  scene_app  (см. $log)"; failed+=("$name"); continue
  fi
  echo "OK"
  ok=$((ok + 1))
done

if [ ${#debug_scenes[@]} -gt 0 ] && [ -f "${debug_scenes[0]}" ]; then
  echo
  echo "Сцены с нарочными ошибками (стенд должен упасть):"
  for scene in "${debug_scenes[@]}"; do
    name="debug_$(scene_name "$scene")"
    out="build/e2e/$name"
    log="build/e2e/$name.log"
    : > "$log"
    printf '%-28s ' "$name"

    build_scene "$scene" "$out" "$log" --unsafe-skip-checks || { failed+=("$name"); continue; }
    if (cd "$out/build" && ./check_geometry) >>"$log" 2>&1; then
      echo "FAIL  стенд НЕ поймал ошибку (см. $log)"; failed+=("$name"); continue
    fi
    echo "OK    стенд поймал ошибку"
    ok=$((ok + 1))
  done
fi

echo
echo "итог: OK ${ok}, FAIL ${#failed[@]}"
[ ${#failed[@]} -eq 0 ]
