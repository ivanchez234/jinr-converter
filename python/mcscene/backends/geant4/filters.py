"""Фильтры пакета geant4: как значения выглядят в сгенерированном C++ и в макросах Geant4.

В шаблоне фильтр пишется через черту: {{ b.volume|cpp_str }}, {{ world.half_size|map("mm")|join(", ") }}.

Правила записи чисел: целое значение -> 25, иначе кратчайшая точная запись (repr),
-0.0 -> 0; единицы всегда явные: *mm.
"""
from __future__ import annotations

from typing import Sequence


def num(x: float) -> str:
    x = float(x)
    if x == 0:
        return "0"                       # и 0.0, и -0.0
    if x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def mm(x: float) -> str:
    return num(x) + "*mm"


def vec_mm(v: Sequence[float]) -> str:
    return "G4ThreeVector(%s)" % ", ".join(mm(x) for x in v)


def sizes(v: Sequence[float]) -> str:
    """Размеры для комментария: 20 × 40 × 70."""
    return " × ".join(num(x) for x in v)


def cpp_str(s: str) -> str:
    """Строковый литерал C++. id из контракта состоят из [A-Za-z0-9_-], но экранируем на всякий случай."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def comment(s: str) -> str:
    """Текст для однострочного комментария // (имена из FreeCAD могут быть любыми)."""
    return " ".join(str(s).split())


def mat3_init(m: Sequence[Sequence[float]], indent: int) -> str:
    """Литерал scene::Mat3 из трёх строк: {{{a, b, c},\\n<indent>{d, e, f},\\n<indent>{g, h, i}}}.

    Фигурные скобки печатает фильтр, а не шаблон: в тексте шаблона «{{» значило бы
    начало вставки Jinja2 (правило 4 решения 001).
    """
    rows = ["{%s}" % ", ".join(num(x) for x in row) for row in m]
    pad = " " * indent
    return "{{%s,\n%s%s,\n%s%s}}" % (rows[0], pad, rows[1], pad, rows[2])


def align_comments(block: str, marker: str = "  // ") -> str:
    """Выравнивает комментарии «  // …» в колонку внутри блока строк."""
    lines = block.split("\n")
    width = max((len(line.partition(marker)[0]) for line in lines if marker in line), default=0)
    out = []
    for line in lines:
        if marker in line:
            code, _, rest = line.partition(marker)
            line = (code.ljust(width) + marker + rest).rstrip()
        out.append(line)
    return "\n".join(out)


FILTERS = {
    "num": num,
    "mm": mm,
    "vec_mm": vec_mm,
    "sizes": sizes,
    "cpp_str": cpp_str,
    "comment": comment,
    "mat3_init": mat3_init,
    "align_comments": align_comments,
}
