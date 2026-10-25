"""Общее для всех целей: что цель делает с каждым телом и общий порядок генерации.

Цель (Geant4, позже OpenMC, FLUKA, MCNP) — это класс-наследник Backend. Он говорит:
  capabilities   — какие фигуры умеет (таблица);
  plan()         — как из сцены получить данные для своих шаблонов (числа, имена, порядок);
  context()      — что именно видят шаблоны;
  templates_dir  — где лежит его пакет шаблонов (pack.json + *.j2);
  filters        — как в его языке пишутся значения (25*mm, поля FLUKA по 10 колонок...).

Порядок шагов один для всех и написан здесь один раз (generate — «шаблонный метод»):
  plan (внутри — check) -> render (шаблоны пакета) -> write (ProjectWriter).
Новая цель пишет только свои шаги; общий код при этом не меняется.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, ClassVar, Mapping

from ..diagnostics import Diagnostic
from ..templating import TemplatePack, TemplateRenderer
from .writer import GenerateError, ProjectWriter, WriteResult


class Action(str, Enum):
    LEGAL = "LEGAL"              # цель умеет это напрямую
    LOWER = "LOWER"              # точно, но другим способом (например, тор -> плоскости)
    APPROXIMATE = "APPROXIMATE"  # приближённо (например, меш)
    ERROR = "ERROR"              # не умеет

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Capability:
    action: Action
    code: str | None = None      # код диагностики для ERROR / LOWER / APPROXIMATE
    reason: str = ""


@dataclass(frozen=True)
class CheckRow:
    """Одна строка вывода mcscene check."""
    body_id: str
    shape_type: str
    action: Action
    note: str = ""


@dataclass(frozen=True)
class PlanResult:
    """Что получилось на шаге plan: данные для шаблонов или ошибки."""
    plan: Any                     # план цели (G4Plan у Geant4); None, если есть ошибки
    rows: list[CheckRow]          # по строке на тело: что цель с ним сделает
    diagnostics: list[Diagnostic]


@dataclass
class BackendRun:
    """Итог generate у цели."""
    planned: PlanResult
    written: WriteResult | None = None    # None — не записано (ошибки в сцене или папка занята)
    error: str = ""                       # почему не записано, если сцена в порядке


def check_shapes(scene, table: Mapping[str, Capability], target: str
                 ) -> tuple[list[CheckRow], list[Diagnostic]]:
    """По таблице возможностей цели: строка на тело и E301 для того, что цель не умеет."""
    rows: list[CheckRow] = []
    diags: list[Diagnostic] = []
    for b in scene.bodies:
        cap = table.get(b.shape.type, Capability(Action.ERROR, "E301", "неизвестный тип формы"))
        rows.append(CheckRow(b.id, b.shape.type, cap.action, cap.reason))
        if cap.action is Action.ERROR:
            diags.append(Diagnostic("ERROR", cap.code or "E301", "bodies/%s/shape" % b.id,
                                    "%s: %s" % (b.shape.type, cap.reason),
                                    body_id=b.id, target=target))
    return rows, diags


class Backend(ABC):
    """Цель генерации. Наследник задаёт поля и шаги ниже, порядок шагов — общий."""

    name: ClassVar[str]                                # "geant4" — так цель зовут в -t
    description: ClassVar[str] = ""
    capabilities: ClassVar[Mapping[str, Capability]]   # тип формы из JSON -> что цель с ней делает
    templates_dir: ClassVar[Path]                      # папка пакета шаблонов
    filters: ClassVar[Mapping[str, Callable[..., Any]]] = {}

    # --- шаги, которые пишет каждая цель ---------------------------------------
    @abstractmethod
    def plan(self, scene, source: Path, unsafe: bool = False) -> PlanResult:
        """Сцена -> данные для шаблонов. Ошибки — в diagnostics, plan = None."""

    @abstractmethod
    def context(self, plan) -> dict[str, Any]:
        """Что видят шаблоны пакета."""

    def extra_files(self, plan, diagnostics: list[Diagnostic]) -> dict[str, str]:
        """Файлы, которые пишутся не шаблонами (например report.json)."""
        return {}

    def resources(self) -> dict[str, Path]:
        """Где лежит то, что пакет копирует как есть (copy в pack.json)."""
        return {}

    def next_steps(self, out_dir: str) -> list[str]:
        """Что делать с результатом дальше — подсказка для терминала."""
        return []

    # --- общее для всех целей ----------------------------------------------------
    def check(self, scene) -> tuple[list[CheckRow], list[Diagnostic]]:
        return check_shapes(scene, self.capabilities, self.name)

    @cached_property
    def pack(self) -> TemplatePack:
        return TemplatePack(self.templates_dir)

    @cached_property
    def renderer(self) -> TemplateRenderer:
        return TemplateRenderer([self.templates_dir], self.filters)

    def render(self, plan, diagnostics: list[Diagnostic]) -> tuple[dict[str, str], dict[str, str]]:
        """(перезаписываемые файлы, файлы пользователя): путь -> текст."""
        data = self.context(plan)
        generated = {f.output: self.renderer.render(f.template, data) for f in self.pack.generated}
        generated.update(self.extra_files(plan, diagnostics))
        user = {f.output: self.renderer.render(f.template, data) for f in self.pack.user}
        return generated, user

    def generate(self, scene, source: Path, out_dir: str | Path, *, force: bool = False,
                 unsafe: bool = False, known: list[Diagnostic] | None = None) -> BackendRun:
        """Весь путь: план -> шаблоны -> запись. known — диагностика, собранная до цели."""
        planned = self.plan(scene, source, unsafe=unsafe)
        if planned.plan is None:
            return BackendRun(planned)
        generated, user = self.render(planned.plan, list(known or []) + planned.diagnostics)
        try:
            written = ProjectWriter(self.pack, self.resources()).write(out_dir, generated, user, force=force)
        except GenerateError as e:
            return BackendRun(planned, error=str(e))
        return BackendRun(planned, written)
