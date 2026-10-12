"""Модели Scene IR: совпадают ли они со схемой контракта."""
import copy
import json

import pytest
from pydantic import ValidationError

from mcscene.io.load import drop_fields
from mcscene.model import Box, RotEuler, RotMatrix, Scene
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES

EXAMPLES = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + sorted(TEST_SCENES.glob("*.json"))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def box_doc():
    return load(TEST_SCENES / "box_in_world.json")


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_round_trip_keeps_every_field(path):
    """Разбор и обратная выгрузка дают исходный документ: модель не теряет поля."""
    doc = load(path)
    back = Scene.model_validate(doc).model_dump(mode="json", exclude_unset=True)
    assert back == doc


def test_discriminators(box_doc):
    scene = Scene.model_validate(box_doc)
    assert isinstance(scene.bodies[0].shape, Box)

    doc = copy.deepcopy(box_doc)
    doc["bodies"][0]["transform"]["rotation"] = {"convention": "euler_xyz_extrinsic_deg",
                                                 "angles": [0, 0, 90]}
    assert isinstance(Scene.model_validate(doc).bodies[0].transform.rotation, RotEuler)

    doc["bodies"][0]["transform"]["rotation"] = {"convention": "matrix_active",
                                                 "matrix": [[0, -1, 0], [1, 0, 0], [0, 0, 1]]}
    assert isinstance(Scene.model_validate(doc).bodies[0].transform.rotation, RotMatrix)


@pytest.mark.parametrize("mutate", [
    lambda d: d["bodies"][0]["shape"].update(type="prism"),               # неизвестная фигура
    lambda d: d["bodies"][0]["shape"].update(colour="red"),               # лишнее поле
    lambda d: d["bodies"][0]["shape"].update(size=[100, 0, 20]),          # размер не > 0
    lambda d: d["bodies"][0]["shape"].update(size=[100, 50]),             # не три числа
    lambda d: d["bodies"][0].pop("parent"),                               # parent обязателен
    lambda d: d["bodies"][0].update(id="1box"),                           # id не по шаблону
    lambda d: d["materials"][1].pop("nist"),                              # ни nist, ни состава
    lambda d: d["units"].update(length="cm"),                             # только мм
    lambda d: d.update(bodies=[]),                                        # хотя бы одно тело
], ids=["unknown-type", "extra-field", "zero-size", "two-sizes", "no-parent",
        "bad-id", "no-nist-no-composition", "cm", "no-bodies"])
def test_model_rejects_what_schema_rejects(box_doc, mutate):
    mutate(box_doc)
    with pytest.raises(ValidationError):
        Scene.model_validate(box_doc)


def test_custom_material_with_composition_is_accepted(box_doc):
    box_doc["materials"][1] = {
        "id": "iron", "density": 7.874,
        "composition": {"basis": "mass", "components": [{"element": "Fe", "fraction": 1.0}]},
    }
    assert Scene.model_validate(box_doc).materials[1].nist is None


def test_drop_fields_removes_only_given_paths(box_doc):
    box_doc["bodies"][0]["shape"]["colour"] = "red"
    box_doc["world"]["note"] = "x"
    clean = drop_fields(box_doc, ["/bodies/0/shape/colour", "/world/note"])
    assert "colour" not in clean["bodies"][0]["shape"]
    assert "note" not in clean["world"]
    assert box_doc["world"]["note"] == "x"          # исходный документ не тронут
