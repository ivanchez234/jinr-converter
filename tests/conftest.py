"""Общие помощники для тестов: короткая сборка сцен прямо в коде теста."""
import copy

import pytest

from mcscene.model import Scene

_BASE = {
    "format": "jinr-mc-scene",
    "format_version": "0.1",
    "units": {"length": "mm", "angle": "deg", "density": "g/cm3"},
    "world": {"material": "air", "margin_percent": 10},
    "materials": [
        {"id": "air", "nist": "G4_AIR"},
        {"id": "iron", "nist": "G4_Fe"},
    ],
    "bodies": [],
}


def box_body(id, size, translation=(0, 0, 0), rotation=None, parent=None,
             material="iron", bbox=None):
    """Тело-коробка в виде словаря JSON. rotation — словарь rotation из контракта."""
    sx, sy, sz = size
    body = {
        "id": id,
        "parent": parent,
        "material": material,
        "transform": {"translation": list(translation),
                      "rotation": rotation or {"convention": "identity"}},
        "shape": {"type": "box", "size": list(size)},
        "verification": {"cad_volume": sx * sy * sz},
    }
    if bbox is not None:
        body["verification"]["bbox"] = [list(bbox[0]), list(bbox[1])]
    return body


def make_scene(*bodies, materials=None, margin=10, world_material="air"):
    doc = copy.deepcopy(_BASE)
    doc["bodies"] = list(bodies)
    doc["world"] = {"material": world_material, "margin_percent": margin}
    if materials is not None:
        doc["materials"] = materials
    return Scene.model_validate(doc)


@pytest.fixture
def scene():
    """scene(body, body, ..., materials=..., margin=...) -> Scene."""
    return make_scene


@pytest.fixture
def box():
    """box(id, size, translation, rotation=..., parent=..., material=..., bbox=...) -> dict."""
    return box_body
