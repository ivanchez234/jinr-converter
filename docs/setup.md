# Установка окружения

Проверено на машине Ивана, 12 октября 2026.

## Что стоит

| | Версия |
|---|---|
| ОС | Ubuntu 24.04.5 LTS |
| Geant4 | 11.4.2, собран из исходников, установлен в `~/geant4/install` |
| Qt-визуализация | есть (`geant4-config --has-feature qt` → yes) |
| OpenGL X11 | нет (не нужен: при Qt OpenGL идёт через Qt) |
| Наборы данных Geant4 | все 12 установлены (`~/geant4/install/share/Geant4/data`) |
| CMake | 3.28.3 |
| g++ | 13.3.0 |
| Python | 3.12.3, модуль `venv` работает |
| git | 2.43.0 |

## Geant4

Исходники: `~/geant4/geant4-v11.4.2`, установка: `~/geant4/install`.

<!-- TODO: дописать точные флаги cmake, с которыми собирался Geant4
     (если папка сборки сохранилась: grep GEANT4_ <папка сборки>/CMakeCache.txt) -->

### Подключение окружения

Перед любой сборкой с Geant4 нужно подключить его переменные:

```bash
source $HOME/geant4/install/bin/geant4.sh
```

Для удобства в `~/.bashrc` заведён алиас:

```bash
alias g4env='source $HOME/geant4/install/bin/geant4.sh'
```

Алиасы не работают внутри скриптов, поэтому скрипты (например, `tools/e2e.sh`) должны сами вызывать `source …/geant4.sh`.

### Проверка установки

```bash
g4env
geant4-config --version             # 11.4.2
geant4-config --has-feature qt      # yes
geant4-config --check-datasets      # все наборы INSTALLED
```

### Пример B1

```bash
g4env
mkdir -p ~/g4work
cp -r ~/geant4/install/share/Geant4/examples/basic/B1 ~/g4work/B1
cmake -S ~/g4work/B1 -B ~/g4work/B1/build
cmake --build ~/g4work/B1/build -j$(nproc)
cd ~/g4work/B1/build && ./exampleB1
```

Должно открыться Qt-окно с геометрией. Команда `/run/beamOn 10` в поле внизу окна рисует треки частиц, это заодно проверяет, что физика и наборы данных работают.

## Python для mcscene

У `mcscene` своё виртуальное окружение в папке репозитория (`.venv/`), Python FreeCAD для него не нужен, Geant4 для этой части тоже.

```bash
cd ~/jinr-converter
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mcscene --version
```

Пакет ставится только в редактируемом режиме (`-e`): тогда `mcscene` берёт контракт и `validate.py` прямо из `contracts/scene/v0.1/`, а правки в `python/mcscene/` действуют сразу, без переустановки. В новом терминале достаточно `source .venv/bin/activate`.

### Проверка

```bash
pytest                                                     # все тесты зелёные
mcscene validate --strict tests/scenes/*.json              # OK
mcscene validate contracts/scene/v0.1/bad/b01_half_sizes.json   # E220, код выхода 1
```

## Библиотека g4scene (C++)

`cpp/g4scene/` — маленькая библиотека, которой пользуется сгенерированный код: повороты и размещение (`Transform`, `Place`), реестр материалов и объёмов (`Registry`), материалы NIST (`Nist`). В сгенерированные проекты она копируется исходниками, а отдельно собирается только ради своих тестов:

```bash
g4env                                              # подключить Geant4
cd ~/jinr-converter
cmake -S cpp/g4scene -B build/g4scene
cmake --build build/g4scene -j$(nproc)
ctest --test-dir build/g4scene --output-on-failure
```

Тест должен напечатать `g4scene: OK, N проверок`. Главное, что он проверяет: Geant4 понимает наш поворот так же, как контракт (активный поворот «тело -> родитель»), и размещение через `G4Transform3D` ставит вложенное тело туда, куда нужно. Папка `build/` в git не попадает.
