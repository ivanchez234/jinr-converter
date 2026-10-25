"""Общие проходы над Scene IR — для любой цели.

Проходы не знают про конкретную цель (Geant4, OpenMC, ...) и ничего не печатают:
каждый пишет сообщения в общий сборщик Diagnostics и возвращает свой результат.

  base      — Pass: общий вход run(scene, diags);
  world     — WorldPass: размер мира;
  materials — MaterialPass: какие материалы нужны и можно ли их построить.

Имена объёмов зависят от цели (у Geant4 одни правила, у FLUKA — имена до 8 символов),
поэтому они у цели: backends/geant4/naming.py. Повороты и габариты — объекты в geometry/.
"""
from .base import Pass
from .materials import MaterialPass, MaterialPlan
from .world import WorldPass, WorldPlan

__all__ = ["MaterialPass", "MaterialPlan", "Pass", "WorldPass", "WorldPlan"]
