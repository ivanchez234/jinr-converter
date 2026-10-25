"""Пакет шаблонов цели («пакет диалекта»): папка с шаблонами *.j2 и файлом pack.json.

    {
      "target": "geant4",
      "description": "что получается на выходе",
      "generated": ["CMakeLists.txt.j2", "generated/GeneratedDetectorConstruction.cc.j2", ...],
      "user":      ["user/DetectorConstruction.hh.j2"],
      "copy":      [{"from": "g4scene", "to": "g4scene", "dirs": ["include", "src"],
                     "suffixes": [".hh", ".cc"]}]
    }

generated — файлы, которые генератор перезаписывает (с --force);
user      — файлы пользователя: создаются один раз и больше никогда не трогаются;
copy      — что скопировать как есть. "from" — имя ресурса; где он лежит, знает цель.

Каждый шаблон даёт файл проекта с тем же путём без .j2. Файлы, имя которых начинается
с "_", — общие куски (макросы): в проект они не выводятся, поэтому в списках их быть не может.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

KEYS = {"target", "description", "generated", "user", "copy"}
COPY_KEYS = {"from", "to", "dirs", "suffixes"}


class PackError(Exception):
    """pack.json не читается или описывает что-то невозможное."""


@dataclass(frozen=True)
class PackFile:
    template: str        # путь шаблона внутри пакета: "app/vis.mac.j2"
    output: str          # путь в проекте: "app/vis.mac"


@dataclass(frozen=True)
class CopyRule:
    source: str                    # имя ресурса: "g4scene"
    to: str                        # папка в проекте
    dirs: tuple[str, ...]          # какие подпапки ресурса копировать
    suffixes: tuple[str, ...]      # какие файлы (пусто — все)


class TemplatePack:
    """Содержимое pack.json, проверенное до того, как что-то будет записано."""

    MANIFEST = "pack.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        path = self.root / self.MANIFEST
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PackError("не читается %s: %s" % (path, e)) from e
        if not isinstance(data, dict):
            raise PackError("%s: ожидался объект JSON" % path)
        unknown = set(data) - KEYS
        if unknown:
            raise PackError("%s: неизвестные поля %s" % (path, ", ".join(sorted(unknown))))

        self.target: str = data.get("target", "")
        self.description: str = data.get("description", "")
        self.generated = tuple(self._file(t) for t in data.get("generated", []))
        self.user = tuple(self._file(t) for t in data.get("user", []))
        self.copy = tuple(self._copy(c) for c in data.get("copy", []))
        self._check()

    # --- что пакет пишет ---------------------------------------------------------
    @property
    def files(self) -> tuple[PackFile, ...]:
        return self.generated + self.user

    @property
    def owned_dirs(self) -> tuple[str, ...]:
        """Папки проекта, которые при --force пересоздаются целиком (в порядке появления)."""
        dirs: list[str] = []
        for f in self.generated:
            parts = PurePosixPath(f.output).parts
            if len(parts) > 1 and parts[0] not in dirs:
                dirs.append(parts[0])
        for c in self.copy:
            if c.to not in dirs:
                dirs.append(c.to)
        return tuple(dirs)

    @property
    def top_files(self) -> tuple[str, ...]:
        """Перезаписываемые файлы в корне проекта (CMakeLists.txt и т.п.)."""
        return tuple(f.output for f in self.generated if len(PurePosixPath(f.output).parts) == 1)

    @property
    def user_dirs(self) -> tuple[str, ...]:
        dirs: list[str] = []
        for f in self.user:
            top = PurePosixPath(f.output).parts[0]
            if top not in dirs:
                dirs.append(top)
        return tuple(dirs)

    # --- разбор и проверка -------------------------------------------------------
    def _file(self, template: object) -> PackFile:
        if not isinstance(template, str) or not template.endswith(".j2"):
            raise PackError("%s: шаблон должен быть путём к файлу *.j2, а не %r" % (self.MANIFEST, template))
        p = PurePosixPath(template)
        if p.is_absolute() or ".." in p.parts:
            raise PackError("%s: путь %s должен быть внутри пакета" % (self.MANIFEST, template))
        if p.name.startswith("_"):
            raise PackError("%s: %s — общий кусок (имя с «_»), в проект он не выводится"
                            % (self.MANIFEST, template))
        if not (self.root / template).is_file():
            raise PackError("%s: нет шаблона %s в %s" % (self.MANIFEST, template, self.root))
        return PackFile(template, template[:-len(".j2")])

    def _copy(self, c: object) -> CopyRule:
        if not isinstance(c, dict) or not {"from", "to"} <= set(c) or set(c) - COPY_KEYS:
            raise PackError("%s: в copy нужны поля from и to (можно dirs, suffixes): %r" % (self.MANIFEST, c))
        to = PurePosixPath(c["to"])
        if to.is_absolute() or ".." in to.parts or len(to.parts) != 1:
            raise PackError("%s: copy.to должен быть одной папкой проекта: %r" % (self.MANIFEST, c["to"]))
        return CopyRule(c["from"], c["to"], tuple(c.get("dirs", ())), tuple(c.get("suffixes", ())))

    def _check(self) -> None:
        outputs = [f.output for f in self.files]
        dupes = sorted({o for o in outputs if outputs.count(o) > 1})
        if dupes:
            raise PackError("%s: один и тот же файл проекта дважды: %s" % (self.MANIFEST, ", ".join(dupes)))
        for f in self.user:
            if len(PurePosixPath(f.output).parts) < 2:
                raise PackError("%s: файл пользователя %s должен лежать в своей папке (например user/)"
                                % (self.MANIFEST, f.output))
        clash = set(self.user_dirs) & set(self.owned_dirs)
        if clash:
            raise PackError("%s: папка %s и перезаписывается генератором, и принадлежит пользователю — "
                            "с --force файлы пользователя пропали бы" % (self.MANIFEST, ", ".join(sorted(clash))))
