"""Проход над сценой — общий вход для всех проходов.

Проход читает Scene IR, пишет сообщения в общий сборщик Diagnostics и возвращает
свой результат (размер мира, список материалов, имена...). Цель собирает из проходов
свой конвейер: на этапе 7 к нему добавятся «уплощение» и «регионы» для OpenMC и FLUKA,
а остальное трогать не придётся.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..diagnostics import Diagnostics


class Pass(ABC):
    @abstractmethod
    def run(self, scene, diags: Diagnostics) -> Any:
        """Посчитать своё по сцене; ошибки и предупреждения — в diags."""
