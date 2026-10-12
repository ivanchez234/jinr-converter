"""Доступ к validate.py из контракта.

validate.py не переписываем и не копируем: загружаем тот самый файл из
contracts/scene/v0.1. Тогда правила существуют в одном экземпляре.
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from types import ModuleType

from ..paths import SCHEMA_V0_1, VALIDATE_V0_1


@lru_cache(maxsize=None)
def load_contract_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("jinr_contract_v0_1", VALIDATE_V0_1)
    if spec is None or spec.loader is None:
        raise ImportError("не удалось загрузить %s" % VALIDATE_V0_1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=None)
def load_schema() -> dict:
    """Схема v0.1 (нормативная, рукописная). Читается один раз."""
    return load_contract_validator().load_schema(str(SCHEMA_V0_1))
