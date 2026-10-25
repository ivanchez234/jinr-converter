"""Запись сгенерированного проекта на диск — одна для всех целей.

Что перезаписывается, а что принадлежит пользователю, говорит пакет шаблонов
(pack.json), а не этот код:

  generated — перезаписывается; папки этих файлов и папки из copy при --force
              пересоздаются целиком (лишние старые файлы в них исчезают);
  user      — создаётся один раз и больше не трогается никогда, даже с --force;
  build/    — папку сборки генератор не трогает никогда.

В корне проекта лежит метка .mcscene: «эту папку сделал mcscene». Папку без метки
генератор не трогает никогда — так случайный -o ~ не сотрёт ничего лишнего.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..templating import TemplatePack

MARKER = ".mcscene"


class GenerateError(Exception):
    """Ошибка вызова: папка занята, нужен --force и т.п. (код выхода 2)."""


@dataclass
class WriteResult:
    written: list[str] = field(default_factory=list)       # что записано, пути в проекте
    user_created: list[str] = field(default_factory=list)  # файлы пользователя, созданные сейчас
    user_kept: list[str] = field(default_factory=list)     # уже были — не тронуты


class ProjectWriter:
    """Пишет проект цели по её пакету шаблонов.

    resources — где лежит то, что пакет просит скопировать как есть:
    {"g4scene": путь к cpp/g4scene}.
    """

    def __init__(self, pack: TemplatePack, resources: Mapping[str, Path] | None = None) -> None:
        self.pack = pack
        self.resources = {k: Path(v) for k, v in (resources or {}).items()}
        missing = [c.source for c in pack.copy if c.source not in self.resources]
        if missing:
            raise GenerateError("не указано, где лежит %s (copy в pack.json)" % ", ".join(missing))

    def write(self, out_dir: str | Path, generated: Mapping[str, str], user: Mapping[str, str],
              force: bool = False) -> WriteResult:
        """generated: путь -> текст перезаписываемых файлов; user: путь -> текст файлов пользователя."""
        out = Path(out_dir)
        self._prepare(out, force)
        result = WriteResult()

        files = dict(generated)
        files[MARKER] = self.marker_text(generated)
        for rel in sorted(files):
            _write(out / rel, files[rel])
        result.written = sorted(files)

        for rule in self.pack.copy:
            src_root = self.resources[rule.source]
            sources = sorted(p for d in rule.dirs for p in (src_root / d).rglob("*")
                             if p.is_file() and (not rule.suffixes or p.suffix in rule.suffixes))
            for src in sources:
                rel = Path(rule.to) / src.relative_to(src_root)
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, out / rel)
                result.written.append(rel.as_posix())

        for rel in sorted(user):
            if (out / rel).exists():
                result.user_kept.append(rel)
            else:
                _write(out / rel, user[rel])
                result.user_created.append(rel)
                result.written.append(rel)
        return result

    def marker_text(self, generated: Mapping[str, str]) -> str:
        """Текст метки .mcscene: что здесь перезаписывается, а что нет."""
        top_files = [rel for rel in generated if "/" not in rel]
        owned = [d + "/" for d in self.pack.owned_dirs] + top_files
        kept = [d + "/" for d in self.pack.user_dirs] + ["build/"]
        return ("Эту папку создал mcscene. При mcscene generate --force перезаписываются\n"
                "%s;\n%s не трогаются никогда.\n" % (_and_join(owned), _and_join(kept)))

    def _prepare(self, out: Path, force: bool) -> None:
        if out.exists() and not out.is_dir():
            raise GenerateError("%s — это файл, а не папка" % out)
        if not out.exists() or not any(out.iterdir()):
            out.mkdir(parents=True, exist_ok=True)
            return
        if not (out / MARKER).is_file():
            raise GenerateError("папка %s не пуста и не похожа на результат mcscene (нет файла %s): "
                                "выберите другую папку" % (out, MARKER))
        if not force:
            kept = " и ".join(d + "/" for d in self.pack.user_dirs + ("build",))
            raise GenerateError("в %s уже есть сгенерированный проект; чтобы перезаписать, добавьте "
                                "--force (%s не трогаются)" % (out, kept))
        for name in self.pack.owned_dirs:
            p = out / name
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)


def _and_join(items: list[str]) -> str:
    """["a", "b", "c"] -> "a, b и c"."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " и " + items[-1]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
