"""Диагностики: один тип сообщений на весь генератор.

Коды:
  E0xx, E1xx, E2xx, W0xx, W1xx, W2xx, I0xx, I2xx — из validate.py, без изменений;
  E3xx        — цель не умеет (фигура, материал) или не хватает данных:
      E310 — материал задан своим составом без nist (свои составы — этап 3);
      E330 — у тела-меша нет verification.bbox, размер мира не оценить;
  W4xx, I4xx  — смена представления и имён:
      I401 — имя объёма или C++ функции изменено (занято или совпало после замены '-');
      I402 — материал никем не используется, в код не попадает;
      I410 — у материала и nist, и composition: для Geant4 берётся nist;
  W5xx        — проверка не сошлась;
  E6xx        — сборка или стенд упали;
  E9xx        — mcscene разошёлся с контрактом (ошибка в mcscene или в контракте,
                а не во входном файле):
      E901 — jsonschema нашёл ошибку, которую пропустил validate.py;
      E902 — файл прошёл проверку, но не разобрался в модели Scene IR.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Literal, TextIO

Level = Literal["ERROR", "WARN", "INFO"]


@dataclass(frozen=True)
class Diagnostic:
    level: Level
    code: str             # E202, W241, E301 ...
    where: str            # /bodies/0/material
    message: str
    body_id: str | None = None
    target: str | None = None

    @classmethod
    def from_issue(cls, issue) -> "Diagnostic":
        """Сообщение validate.py (Issue: level, code, where, msg) -> Diagnostic."""
        return cls(issue.level, issue.code, issue.where, issue.msg)


def has_errors(diags: Iterable[Diagnostic]) -> bool:
    return any(d.level == "ERROR" for d in diags)


_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


def print_diagnostics(diags: list[Diagnostic], stream: TextIO | None = None,
                      verbose: bool = False) -> None:
    """Печать в том же виде, что у validate.py: ошибки, предупреждения, итог."""
    stream = stream or sys.stdout
    for d in sorted(diags, key=lambda x: _ORDER[x.level]):
        if d.level == "INFO" and not verbose:
            continue
        stream.write("%-5s %s  %s: %s\n" % (d.level, d.code, d.where, d.message))
    ne = sum(1 for d in diags if d.level == "ERROR")
    nw = sum(1 for d in diags if d.level == "WARN")
    stream.write("Итог: ошибок %d, предупреждений %d -> %s\n"
                 % (ne, nw, "НЕ ПРОШЁЛ" if ne else "OK"))
