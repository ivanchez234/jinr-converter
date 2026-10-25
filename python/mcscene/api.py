"""Вход в генератор для программ: аддона FreeCAD, командной строки, тестов.

    from mcscene import Converter

    result = Converter("geant4").generate("scene.json", "out/model")
    if result.ok:
        print("готово:", result.out_dir)
    else:
        for d in result.diagnostics:
            print(d.level, d.code, d.where, d.message)

Converter ничего не печатает и не завершает программу (никаких print и sys.exit):
он только возвращает результат. Что показать человеку, решает тот, кто вызвал, —
окно аддона или командная строка (cli.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .backends import get_backend, targets
from .backends.base import CheckRow
from .diagnostics import Diagnostic
from .io.load import SceneLoader

__all__ = ["CheckReport", "Converter", "GenerateResult", "Status", "ValidationReport",
           "targets", "validate"]


class Status(str, Enum):
    OK = "ok"
    UNREADABLE = "unreadable"        # файл не читается или это не JSON (E001)
    INVALID = "invalid"              # сцена нарушает контракт
    UNSUPPORTED = "unsupported"      # цель пока не умеет какие-то тела или материалы
    WRITE_FAILED = "write_failed"    # не записано: папка занята, нужен --force и т.п.

    def __str__(self) -> str:
        return self.value


@dataclass
class ValidationReport:
    """Итог проверки сцены по контракту."""
    scene: str
    status: Status
    diagnostics: list[Diagnostic]
    model: Any = None                # Scene IR, если сцена прошла проверку

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


@dataclass
class CheckReport:
    """Итог Converter.check: что цель сделает с каждым телом. Ничего не записано."""
    target: str
    scene: str
    status: Status
    rows: list[CheckRow] = field(default_factory=list)     # по строке на тело
    diagnostics: list[Diagnostic] = field(default_factory=list)
    plan: Any = None                                       # данные для шаблонов, если всё в порядке

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


@dataclass
class GenerateResult(CheckReport):
    """Итог Converter.generate."""
    out_dir: str = ""
    files: list[str] = field(default_factory=list)          # что записано
    user_created: list[str] = field(default_factory=list)   # файлы пользователя, созданные сейчас
    user_kept: list[str] = field(default_factory=list)      # уже были — не тронуты
    error: str = ""                                         # почему не записано (WRITE_FAILED)
    next_steps: list[str] = field(default_factory=list)     # что делать с результатом дальше


def validate(scene_path: str | os.PathLike, *, strict: bool = False,
             unsafe_skip_checks: bool = False) -> ValidationReport:
    """Проверить сцену по контракту (validate.py) и разобрать в Scene IR."""
    model, diags = SceneLoader(strict, unsafe_skip_checks).load(scene_path)
    if model is not None:
        status = Status.OK
    elif any(d.code == "E001" for d in diags):
        status = Status.UNREADABLE
    else:
        status = Status.INVALID
    return ValidationReport(str(scene_path), status, diags, model)


class Converter:
    """Генератор для одной цели: Converter("geant4"). Цели — mcscene.targets()."""

    def __init__(self, target: str = "geant4") -> None:
        self.target = target
        self.backend = get_backend(target)          # нет такой цели -> UnknownTarget

    def check(self, scene_path: str | os.PathLike, *, strict: bool = False) -> CheckReport:
        """Проверить сцену и сказать, что цель сделает с каждым телом. Ничего не пишет."""
        v = validate(scene_path, strict=strict)
        if not v.ok:
            return CheckReport(self.target, v.scene, v.status, diagnostics=v.diagnostics)
        planned = self.backend.plan(v.model, Path(scene_path))
        return CheckReport(self.target, v.scene,
                           Status.OK if planned.plan is not None else Status.UNSUPPORTED,
                           planned.rows, v.diagnostics + planned.diagnostics, planned.plan)

    def generate(self, scene_path: str | os.PathLike, out_dir: str | os.PathLike, *,
                 force: bool = False, strict: bool = False,
                 unsafe_skip_checks: bool = False) -> GenerateResult:
        """Проверить сцену и записать проект цели в out_dir.

        force — перезаписать уже сгенерированный проект (файлы пользователя не трогаются);
        unsafe_skip_checks — ОТЛАДКА: пропустить геометрические проверки контракта
        (E220, E240, E250, E251), чтобы убедиться, что стенд их поймает.
        """
        out = str(out_dir)
        v = validate(scene_path, strict=strict, unsafe_skip_checks=unsafe_skip_checks)
        if not v.ok:
            return GenerateResult(self.target, v.scene, v.status, diagnostics=v.diagnostics, out_dir=out)

        run = self.backend.generate(v.model, Path(scene_path), out_dir, force=force,
                                    unsafe=unsafe_skip_checks, known=v.diagnostics)
        p = run.planned
        result = GenerateResult(self.target, v.scene, Status.OK, p.rows, v.diagnostics + p.diagnostics,
                                p.plan, out_dir=out)
        if p.plan is None:
            result.status = Status.UNSUPPORTED
        elif run.written is None:
            result.status, result.error = Status.WRITE_FAILED, run.error
        else:
            result.files = run.written.written
            result.user_created = run.written.user_created
            result.user_kept = run.written.user_kept
            result.next_steps = self.backend.next_steps(out)
        return result
