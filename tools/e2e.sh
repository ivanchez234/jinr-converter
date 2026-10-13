#!/usr/bin/env bash
# Сквозной прогон: для каждой сцены mcscene generate -> cmake -> сборка -> check_geometry.
# Запускать из корня репозитория перед коммитом и перед встречей с руководителем:
#
#   source .venv/bin/activate
#   tools/e2e.sh                 # все сцены
#   tools/e2e.sh tests/scenes/kub.json      # только указанные
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
else
  scenes=(tests/scenes/*.json tests/fixtures/freecad/*/scene.json)
fi

mkdir -p build/e2e
jobs="$(nproc 2>/dev/null || echo 2)"
ok=0
failed=()

for scene in "${scenes[@]}"; do
  [ -f "$scene" ] || continue
  if [ "$(basename "$scene")" = "scene.json" ]; then
    name="$(basename "$(dirname "$scene")")"
  else
    name="$(basename "$scene" .json)"
  fi
  out="build/e2e/$name"
  log="build/e2e/$name.log"
  : > "$log"
  printf '%-28s ' "$name"

  if ! mcscene generate "$scene" -o "$out" --force >>"$log" 2>&1; then
    echo "FAIL  generate   (см. $log)"; failed+=("$name"); continue
  fi
  if ! cmake -S "$out" -B "$out/build" -DCMAKE_BUILD_TYPE=Release >>"$log" 2>&1; then
    echo "FAIL  cmake      (см. $log)"; failed+=("$name"); continue
  fi
  if ! cmake --build "$out/build" -j"$jobs" >>"$log" 2>&1; then
    echo "FAIL  сборка     (см. $log)"; failed+=("$name"); continue
  fi
  if ! (cd "$out/build" && ./check_geometry) >>"$log" 2>&1; then
    echo "FAIL  стенд      (см. $log)"; failed+=("$name"); continue
  fi
  echo "OK"
  ok=$((ok + 1))
done

echo
echo "итог: OK ${ok}, FAIL ${#failed[@]}"
[ ${#failed[@]} -eq 0 ]
