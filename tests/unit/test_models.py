"""Модели Scene IR (dataclass на model/record.py): совпадают ли они со схемой контракта."""
import copy
import json

import pytest
from mcscene.io.load import drop_fields
from mcscene.model import Box, ModelError, RotEuler, RotMatrix, Scene
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES, all_test_scenes, scene_id

EXAMPLES = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def box_doc():
    return load(TEST_SCENES / "box_in_world.json")


@pytest.mark.parametrize("path", EXAMPLES, ids=scene_id)
def test_round_trip_keeps_every_field(path):
    """Разбор и обратная выгрузка дают исходный документ: модель не теряет поля."""
    doc = load(path)
    back = Scene.from_dict(doc).to_dict()
    assert back == doc


def test_discriminators(box_doc):
    scene = Scene.from_dict(box_doc)
    assert isinstance(scene.bodies[0].shape, Box)

    doc = copy.deepcopy(box_doc)
    doc["bodies"][0]["transform"]["rotation"] = {"convention": "euler_xyz_extrinsic_deg",
                                                 "angles": [0, 0, 90]}
    assert isinstance(Scene.from_dict(doc).bodies[0].transform.rotation, RotEuler)

    doc["bodies"][0]["transform"]["rotation"] = {"convention": "matrix_active",
                                                 "matrix": [[0, -1, 0], [1, 0, 0], [0, 0, 1]]}
    assert isinstance(Scene.from_dict(doc).bodies[0].transform.rotation, RotMatrix)


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
    with pytest.raises(ModelError):
        Scene.from_dict(box_doc)


def test_custom_material_with_composition_is_accepted(box_doc):
    box_doc["materials"][1] = {
        "id": "iron", "density": 7.874,
        "composition": {"basis": "mass", "components": [{"element": "Fe", "fraction": 1.0}]},
    }
    assert Scene.from_dict(box_doc).materials[1].nist is None


def test_drop_fields_removes_only_given_paths(box_doc):
    box_doc["bodies"][0]["shape"]["colour"] = "red"
    box_doc["world"]["note"] = "x"
    clean = drop_fields(box_doc, ["/bodies/0/shape/colour", "/world/note"])
    assert "colour" not in clean["bodies"][0]["shape"]
    assert "note" not in clean["world"]
    assert box_doc["world"]["note"] == "x"          # исходный документ не тронут


# --- свои классы вместо pydantic (шаг 2.8) ---
@pytest.mark.parametrize("mutate, where", [
    (lambda d: d["bodies"][0]["shape"].update(size=[100, 0, 20]), "/bodies/0/shape/size/1"),
    (lambda d: d["bodies"][0]["shape"].update(colour="red"), "/bodies/0/shape/colour"),
    (lambda d: d["bodies"][0]["shape"].update(type="prism"), "/bodies/0/shape/type"),
    (lambda d: d["bodies"][0].pop("parent"), "/bodies/0/parent"),
    (lambda d: d["materials"][1].pop("nist"), "/materials/1"),
], ids=["zero-size", "extra-field", "unknown-type", "no-parent", "no-nist"])
def test_error_says_where(box_doc, mutate, where):
    # путь в ошибке попадает в E902 — по нему видно, какое место документа не разобралось
    mutate(box_doc)
    with pytest.raises(ModelError) as e:
        Scene.from_dict(box_doc)
    assert e.value.where == where


def test_records_are_frozen_and_lists_are_tuples(box_doc):
    import dataclasses
    scene = Scene.from_dict(box_doc)
    with pytest.raises(dataclasses.FrozenInstanceError):
        scene.bodies[0].id = "other"                 # type: ignore[misc]
    assert isinstance(scene.bodies, tuple) and isinstance(scene.materials, tuple)


def test_numbers_are_floats_like_before(box_doc):
    # pydantic превращал целые в float; план и шаблоны на это рассчитывают
    shape = Scene.from_dict(box_doc).bodies[0].shape
    assert shape.size == (100.0, 50.0, 20.0) and all(type(x) is float for x in shape.size)


def test_record_made_in_code_dumps_its_fields():
    assert Box(type="box", size=(20, 40, 70)).to_dict() == {"type": "box", "size": [20, 40, 70]}
