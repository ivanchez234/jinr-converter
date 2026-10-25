"""Печать файлов из шаблонов Jinja2 (решение 001, docs/decisions/001-template-engine.md).

Настройки одни для всех пакетов целей:
  StrictUndefined        — опечатка в имени переменной даёт ошибку, а не пустое место в файле;
  trim_blocks,
  lstrip_blocks          — строки с {% for %} и {% if %} не оставляют следов в выводе;
  keep_trailing_newline  — перевод строки в конце шаблона сохраняется;
  autoescape=False       — это не HTML: ничего не экранируется.

Шаблон только печатает готовые значения. Всё, что нужно посчитать (половины размеров,
матрицы, цвета, порядок тел), считает Python до вызова render().
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import jinja2


class TemplateError(Exception):
    """Ошибка в шаблоне: нет файла, опечатка в имени, синтаксис. Текст указывает шаблон и строку."""


class TemplateRenderer:
    """Jinja2 с общими настройками и фильтрами пакета.

    search_path — папки, где искать шаблоны, по порядку: первая найденная версия
    файла побеждает (так можно подложить свой шаблон вместо встроенного).
    filters — как в этой цели пишутся значения: {"mm": ..., "cpp_str": ...}.
    """

    def __init__(self, search_path: Sequence[str | Path],
                 filters: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self.search_path = tuple(Path(p) for p in search_path)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader([str(p) for p in self.search_path], encoding="utf-8"),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )
        self.env.filters.update(filters or {})

    def render(self, name: str, data: Mapping[str, Any]) -> str:
        """Текст файла по шаблону name (путь внутри пакета, например "app/vis.mac.j2")."""
        try:
            return self.env.get_template(name).render(data)
        except jinja2.TemplateNotFound as e:
            raise TemplateError("нет шаблона %s (искали в: %s)" % (
                e.name, ", ".join(str(p) for p in self.search_path))) from e
        except jinja2.TemplateSyntaxError as e:
            raise TemplateError("%s, строка %s: ошибка в записи шаблона: %s" % (
                e.name or name, e.lineno, e.message)) from e
        except jinja2.UndefinedError as e:
            raise TemplateError("%s: %s" % (self._where(e, name), e.message)) from e

    def _where(self, exc: BaseException, default: str) -> str:
        """Шаблон и строка, где случилась ошибка (Jinja2 кладёт их в traceback)."""
        where = default
        tb = exc.__traceback__
        while tb is not None:
            path = Path(tb.tb_frame.f_code.co_filename)
            if path.suffix == ".j2":
                where = "%s, строка %d" % (self._short(path), tb.tb_lineno)
            tb = tb.tb_next
        return where

    def _short(self, path: Path) -> str:
        for root in self.search_path:
            try:
                return path.relative_to(root).as_posix()
            except ValueError:
                continue
        return path.name
