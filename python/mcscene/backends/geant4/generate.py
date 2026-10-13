"""Запись сгенерированного проекта Geant4 на диск (mcscene generate).

out/<сцена>/
  CMakeLists.txt
  generated/   GeneratedDetectorConstruction.hh/.cc, ExpectedChecks.hh
  harness/     check_geometry.cc
  g4scene/     копия cpp/g4scene (include/, src/)
  user/        DetectorConstruction.hh — создаётся один раз, дальше ваш
  report.json
  .mcscene     метка «эту папку сделал mcscene»

С --force перезаписывается всё, кроме user/ и build/ (папки сборки).
Папку без метки .mcscene генератор не трогает никогда: так случайный -o ~
не сотрёт ничего лишнего.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ...diagnostics import Diagnostic
from ...paths import G4SCENE_SRC
from .plan import G4Plan
from .printer import USER_HH, render, render_user_header

MARKER = ".mcscene"
OWNED_DIRS = ("generated", "harness", "g4scene")       # пересоздаются целиком
MARKER_TEXT = ("Эту папку создал mcscene. При mcscene generate --force перезаписываются\n"
               "generated/, harness/, g4scene/, CMakeLists.txt и report.json;\n"
               "user/ и build/ не трогаются никогда.\n")


class GenerateError(Exception):
    """Ошибка вызова: папка занята, нужен --force и т.п. (код выхода 2)."""


def write_project(plan: G4Plan, diagnostics: list[Diagnostic], out_dir: str | Path,
                  force: bool = False) -> tuple[list[str], bool]:
    """Пишет проект. Возвращает (записанные файлы, создан ли user/DetectorConstruction.hh)."""
    out = Path(out_dir)
    _prepare(out, force)

    files = render(plan, diagnostics)
    files[MARKER] = MARKER_TEXT
    for rel in sorted(files):
        _write(out / rel, files[rel])

    written = sorted(files)
    for src in sorted(p for d in ("include", "src") for p in (G4SCENE_SRC / d).rglob("*")
                      if p.is_file() and p.suffix in (".hh", ".cc")):
        rel = Path("g4scene") / src.relative_to(G4SCENE_SRC)
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out / rel)
        written.append(rel.as_posix())

    user_created = not (out / USER_HH).exists()
    if user_created:
        _write(out / USER_HH, render_user_header())
        written.append(USER_HH)
    return written, user_created


def _prepare(out: Path, force: bool) -> None:
    if out.exists() and not out.is_dir():
        raise GenerateError("%s — это файл, а не папка" % out)
    if not out.exists() or not any(out.iterdir()):
        out.mkdir(parents=True, exist_ok=True)
        return
    if not (out / MARKER).is_file():
        raise GenerateError("папка %s не пуста и не похожа на результат mcscene (нет файла %s): "
                            "выберите другую папку" % (out, MARKER))
    if not force:
        raise GenerateError("в %s уже есть сгенерированный проект; чтобы перезаписать, добавьте "
                            "--force (user/ и build/ не трогаются)" % out)
    for name in OWNED_DIRS:
        p = out / name
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
