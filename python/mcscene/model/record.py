"""Основа Scene IR: неизменяемые записи, которые разбираются из JSON и выгружаются обратно.

Заменяет pydantic (шаг 2.8). У pydantic внутри скомпилированная часть (pydantic-core),
её нельзя просто положить папкой в аддон FreeCAD. Здесь — только то, что от pydantic было
нужно, на чистом Python:

  Box.from_dict(d)  — разобрать словарь JSON: обязательные поля, лишние поля, типы и
                      простые ограничения (> 0, шаблон id, допустимые значения).
                      Ошибка — ModelError с путём: /bodies/0/shape/size/1;
  box.to_dict()     — обратно в словарь JSON ровно с теми полями, что были в файле
                      (поэтому «разбор + выгрузка» даёт исходный документ).

Полностью сцену по контракту проверяет validate.py, и он работает раньше разбора.
Ограничения здесь повторяют то, что проверял pydantic: модель не должна молча принять
то, что схема запрещает (это код E902 — модель разошлась со схемой).

Запись описывается так:

    @dataclass(frozen=True, kw_only=True)
    class Box(ShapeBase):
        type: Literal["box"] = Lit("box").field()
        size: Vec3 = Vec(Num(gt=0)).field()
        transform: Optional[Transform] = Nullable(Obj(Transform)).field(default=None)

Поле без default — обязательное. Списки хранятся кортежами: запись неизменяемая.
"""
from __future__ import annotations

import math
import re
from dataclasses import MISSING, dataclass, field as _field, fields
from typing import Any, Callable, ClassVar, Mapping, Optional


class ModelError(ValueError):
    """Документ не разобрался в модели. where — путь в документе: /bodies/0/shape."""

    def __init__(self, where: str, message: str) -> None:
        self.where = where or "/"
        self.message = message
        super().__init__("%s: %s" % (self.where, message))


def _jtype(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true/false"
    if isinstance(v, (int, float)):
        return "число"
    if isinstance(v, str):
        return "строка"
    if isinstance(v, (list, tuple)):
        return "список"
    if isinstance(v, dict):
        return "объект"
    return type(v).__name__


# --- виды полей: как разобрать одно значение -------------------------------------------
class Kind:
    """Вид поля. parse(value, where) возвращает разобранное значение или бросает ModelError."""

    def parse(self, v: Any, where: str) -> Any:
        raise NotImplementedError

    def field(self, default: Any = MISSING) -> Any:
        """Поле dataclass этого вида; без default — обязательное."""
        return _field(default=default, metadata={"kind": self})


class Num(Kind):
    """Число; gt/ge/le — ограничения; integer — только целое."""

    def __init__(self, gt: float | None = None, ge: float | None = None,
                 le: float | None = None, integer: bool = False) -> None:
        self.gt, self.ge, self.le, self.integer = gt, ge, le, integer

    def parse(self, v: Any, where: str) -> float | int:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ModelError(where, "ожидалось число, получено: %s" % _jtype(v))
        if not math.isfinite(v):
            raise ModelError(where, "число должно быть конечным, получено %r" % v)
        if self.integer:
            if isinstance(v, float) and not v.is_integer():
                raise ModelError(where, "ожидалось целое число, получено %r" % v)
            v = int(v)
        else:
            v = float(v)
        if self.gt is not None and not v > self.gt:
            raise ModelError(where, "должно быть больше %s, получено %r" % (self.gt, v))
        if self.ge is not None and not v >= self.ge:
            raise ModelError(where, "должно быть не меньше %s, получено %r" % (self.ge, v))
        if self.le is not None and not v <= self.le:
            raise ModelError(where, "должно быть не больше %s, получено %r" % (self.le, v))
        return v


class Str(Kind):
    """Строка; pattern — регулярное выражение (как pattern в JSON Schema)."""

    def __init__(self, pattern: str | None = None, max_length: int | None = None) -> None:
        self.pattern = re.compile(pattern) if pattern else None
        self.max_length = max_length

    def parse(self, v: Any, where: str) -> str:
        if not isinstance(v, str):
            raise ModelError(where, "ожидалась строка, получено: %s" % _jtype(v))
        if self.pattern is not None and not self.pattern.search(v):
            raise ModelError(where, "строка %r не подходит под шаблон %s" % (v, self.pattern.pattern))
        if self.max_length is not None and len(v) > self.max_length:
            raise ModelError(where, "строка длиннее %d символов" % self.max_length)
        return v


class Lit(Kind):
    """Одно из перечисленных значений (Literal)."""

    def __init__(self, *values: str) -> None:
        self.values = values

    def parse(self, v: Any, where: str) -> str:
        if not isinstance(v, str) or v not in self.values:
            raise ModelError(where, "допустимо %s, получено %r" % (" / ".join(map(repr, self.values)), v))
        return v


class Vec(Kind):
    """Список ровно из n значений одного вида -> кортеж: точка, размеры, строка матрицы."""

    def __init__(self, item: Kind, n: int = 3) -> None:
        self.item, self.n = item, n

    def parse(self, v: Any, where: str) -> tuple:
        if not isinstance(v, (list, tuple)) or len(v) != self.n:
            raise ModelError(where, "ожидался список из %d значений, получено: %s%s"
                             % (self.n, _jtype(v), " из %d" % len(v) if isinstance(v, (list, tuple)) else ""))
        return tuple(self.item.parse(x, "%s/%d" % (where, i)) for i, x in enumerate(v))


class List(Kind):
    """Список любой длины (не меньше min_length) -> кортеж."""

    def __init__(self, item: Kind, min_length: int = 0) -> None:
        self.item, self.min_length = item, min_length

    def parse(self, v: Any, where: str) -> tuple:
        if not isinstance(v, (list, tuple)):
            raise ModelError(where, "ожидался список, получено: %s" % _jtype(v))
        if len(v) < self.min_length:
            raise ModelError(where, "в списке должно быть хотя бы %d" % self.min_length)
        return tuple(self.item.parse(x, "%s/%d" % (where, i)) for i, x in enumerate(v))


class Obj(Kind):
    """Вложенная запись."""

    def __init__(self, cls: type) -> None:
        self.cls = cls

    def parse(self, v: Any, where: str) -> Any:
        return self.cls.from_dict(v, where)


class OneOf(Kind):
    """Одна из записей; какая — по значению поля key («type», «convention»).

    choices — функция, которая возвращает {значение: класс}: так можно сослаться
    на классы, объявленные ниже (операнды булевой операции).
    """

    def __init__(self, key: str, choices: Callable[[], Mapping[str, type]]) -> None:
        self.key, self.choices = key, choices

    def parse(self, v: Any, where: str) -> Any:
        if not isinstance(v, dict):
            raise ModelError(where, "ожидался объект, получено: %s" % _jtype(v))
        choices = self.choices()
        tag = v.get(self.key)
        if not isinstance(tag, str) or tag not in choices:
            raise ModelError("%s/%s" % (where, self.key), "допустимо %s, получено %r"
                             % (" / ".join(map(repr, choices)), tag))
        return choices[tag].from_dict(v, where)


class Nullable(Kind):
    """Значение или null."""

    def __init__(self, item: Kind) -> None:
        self.item = item

    def parse(self, v: Any, where: str) -> Any:
        return None if v is None else self.item.parse(v, where)


class AnyDict(Kind):
    """Любой объект JSON как есть (extras, содержимое расширений)."""

    def parse(self, v: Any, where: str) -> dict:
        if not isinstance(v, dict):
            raise ModelError(where, "ожидался объект, получено: %s" % _jtype(v))
        return v


class Map(Kind):
    """Объект «имя -> значение», имена по шаблону (extensions)."""

    def __init__(self, key: Str, value: Kind) -> None:
        self.key, self.value = key, value

    def parse(self, v: Any, where: str) -> dict:
        if not isinstance(v, dict):
            raise ModelError(where, "ожидался объект, получено: %s" % _jtype(v))
        return {self.key.parse(k, "%s/%s" % (where, k)): self.value.parse(x, "%s/%s" % (where, k))
                for k, x in v.items()}


# --- запись ------------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class Record:
    """Неизменяемая запись Scene IR. Поля — dataclass, у каждого в metadata его вид (Kind)."""

    # какие поля были в исходном документе (для to_dict); None — запись создана в коде
    _given: Optional[tuple[str, ...]] = _field(default=None, init=False, repr=False, compare=False)
    _SPECS: ClassVar[dict] = {}

    @classmethod
    def from_dict(cls, d: Any, where: str = "") -> "Record":
        if not isinstance(d, dict):
            raise ModelError(where, "ожидался объект, получено: %s" % _jtype(d))
        specs = cls._specs()
        extra = [k for k in d if k not in specs]
        if extra:
            raise ModelError("%s/%s" % (where, extra[0]), "лишнее поле: в схеме его нет")
        values = {}
        for name, (k, required) in specs.items():
            if name in d:
                values[name] = k.parse(d[name], "%s/%s" % (where, name))
            elif required:
                raise ModelError("%s/%s" % (where, name), "нет обязательного поля")
        obj = cls(**values)
        object.__setattr__(obj, "_given", tuple(d))
        obj.check(where)
        return obj

    def check(self, where: str) -> None:
        """Правила сразу на несколько полей (как model_validator в pydantic). По умолчанию нет."""

    def to_dict(self) -> dict:
        """Словарь JSON. После from_dict — ровно те поля, что были в файле; у записи,
        созданной в коде, — все поля, кроме пустых (None)."""
        if self._given is not None:
            names = self._given
        else:
            names = tuple(f.name for f in fields(self)
                          if not f.name.startswith("_") and getattr(self, f.name) is not None)
        return {n: _dump(getattr(self, n)) for n in names}

    @classmethod
    def _specs(cls) -> dict:
        """имя поля -> (вид, обязательно ли). Считается один раз на класс."""
        if cls not in Record._SPECS:
            Record._SPECS[cls] = {
                f.name: (f.metadata["kind"], f.default is MISSING and f.default_factory is MISSING)
                for f in fields(cls) if not f.name.startswith("_")
            }
        return Record._SPECS[cls]


def _dump(v: Any) -> Any:
    if isinstance(v, Record):
        return v.to_dict()
    if isinstance(v, (list, tuple)):
        return [_dump(x) for x in v]
    if isinstance(v, dict):
        return {k: _dump(x) for k, x in v.items()}
    return v
