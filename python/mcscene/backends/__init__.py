"""Цели генерации и их реестр.

Реестр — как конфиг языков: имя цели -> где лежит её класс. Новая цель (OpenMC,
FLUKA, MCNP) — это папка backends/<цель>/ с классом-наследником Backend и
одна строка здесь. Общий код (Converter, проверка, запись) при этом не меняется.
Класс загружается только тогда, когда цель действительно нужна.
"""
from __future__ import annotations

from importlib import import_module

TARGETS: dict[str, object] = {
    "geant4": "mcscene.backends.geant4.backend:Geant4Backend",
}


class UnknownTarget(ValueError):
    """Такой цели нет в реестре."""


def targets() -> list[str]:
    """Имена всех целей, по алфавиту."""
    return sorted(TARGETS)


def get_backend(name: str):
    """Цель по имени: новый объект класса из реестра."""
    if name not in TARGETS:
        raise UnknownTarget("нет цели %r; есть: %s" % (name, ", ".join(targets())))
    entry = TARGETS[name]
    if isinstance(entry, str):                       # "модуль:Класс"
        module, _, cls = entry.partition(":")
        entry = getattr(import_module(module), cls)
    return entry()
