"""mcscene — генератор моделей Монте-Карло из сцены jinr-mc-scene.

Для программ (аддон FreeCAD, тесты):

    from mcscene import Converter
    result = Converter("geant4").generate("scene.json", "out/model")

Подробно — в mcscene/api.py. Командная строка (mcscene ...) — обёртка над тем же Converter.
"""

__version__ = "0.1.0"

_API = {"Converter", "Status", "targets", "validate"}


def __getattr__(name):
    # Converter и остальное загружаются при первом обращении: import mcscene остаётся лёгким.
    if name in _API:
        from . import api
        return getattr(api, name)
    raise AttributeError("module 'mcscene' has no attribute %r" % name)
