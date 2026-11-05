"""Перепроверка validate.py стандартным jsonschema — только здесь, в тестах (шаг 2.8).

Во время работы mcscene проверяет сцену одним validate.py: он на чистом Python и работает
в Python FreeCAD без установки пакетов. Пакет jsonschema (внутри у него скомпилированная
часть rpds-py) нужен только тут: поймать пробел в SchemaChecker — мини-валидаторе схемы
внутри validate.py.

  1. На всех хороших сценах jsonschema не находит ошибок.
  2. Хорошие сцены портятся по одному месту за раз: удалить поле, подставить значение
     не того типа, отрицательное число, лишнее поле. Если jsonschema видит ошибку,
     SchemaChecker обязан тоже её увидеть. Одно и то же место (то же поле той же фигуры
     в другом теле или другой сцене) портится один раз: иначе тест шёл бы 10 с, а так
     доли секунды. Отдельный тест следит, чтобы при этом не потерялись фигуры и повороты.

Шара и тора нет ни в одном примере контракта и ни в одной сцене, поэтому для них здесь
своя маленькая сцена SPHERE_TORUS (она тоже проходит validate.py --strict).
"""
import copy
import json
import math

import pytest

jsonschema = pytest.importorskip("jsonschema")

from mcscene.io.contract import load_contract_validator, load_schema  # noqa: E402
from mcscene.paths import CONTRACT_V0_1, all_test_scenes, scene_id  # noqa: E402

SCHEMA = load_schema()
JSONSCHEMA = jsonschema.Draft202012Validator(SCHEMA)
VALIDATE = load_contract_validator()
CHECKER = VALIDATE.SchemaChecker(SCHEMA)
KINDS = ("delete", "wrong_type", "negative", "extra")

SPHERE_TORUS = {
    "format": "jinr-mc-scene", "format_version": "0.1",
    "units": {"length": "mm", "angle": "deg", "density": "g/cm3"},
    "world": {"material": "air", "margin_percent": 10},
    "materials": [{"id": "air", "nist": "G4_AIR"}, {"id": "lead", "nist": "G4_Pb"}],
    "bodies": [
        {"id": "shell", "parent": None, "material": "lead",
         "transform": {"translation": [0, 0, 0], "rotation": {"convention": "identity"}},
         "shape": {"type": "sphere", "radius": 50, "inner_radius": 30},
         "verification": {"cad_volume": 4 / 3 * math.pi * (50 ** 3 - 30 ** 3),
                          "bbox": [[-50, -50, -50], [50, 50, 50]]}},
        {"id": "ring", "parent": None, "material": "lead",
         "transform": {"translation": [300, 0, 0],
                       "rotation": {"convention": "euler_xyz_extrinsic_deg", "angles": [90, 0, 0]}},
         "shape": {"type": "torus", "major_radius": 100, "minor_radius": 20},
         "verification": {"cad_volume": 2 * math.pi ** 2 * 100 * 20 ** 2,
                          "bbox": [[180, -20, -120], [420, 20, 120]]}},
    ],
}


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


FILES = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()
GOOD = [(scene_id(p), read(p)) for p in FILES] + [("SPHERE_TORUS", SPHERE_TORUS)]
GOOD_IDS = [name for name, _ in GOOD]


def test_sphere_torus_scene_is_valid():
    rep = VALIDATE.Report(True)
    VALIDATE.validate_document(copy.deepcopy(SPHERE_TORUS), ".", rep, SCHEMA)
    assert [i for i in rep.items if i.level != "INFO"] == []


def places(node, path=(), sig=()):
    """Все места документа: (путь, подпись). В подписи номера в списках заменены на *,
    а к пути добавлены тип фигуры и соглашение поворота вокруг: так «радиус цилиндра
    в теле 3» и «радиус цилиндра в теле 7» — одно место, а «размер коробки» — другое."""
    if isinstance(node, dict):
        tag = node.get("type", node.get("convention"))
        if isinstance(tag, str):
            sig = sig + ("<%s>" % tag,)
        for k, v in node.items():
            yield path + (k,), sig + (k,)
            yield from places(v, path + (k,), sig + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield path + (i,), sig + ("*",)
            yield from places(v, path + (i,), sig + ("*",))


def spoil(doc, path, kind):
    """Копия документа, испорченная в одном месте; None — эта порча к месту не подходит."""
    doc = copy.deepcopy(doc)
    node = doc
    for k in path[:-1]:
        node = node[k]
    k = path[-1]
    v = node[k]
    if kind == "delete":
        if not isinstance(node, dict):
            return None
        del node[k]
    elif kind == "wrong_type":
        node[k] = 7 if isinstance(v, str) else "x"
    elif kind == "negative":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        node[k] = -abs(v) - 1
    elif kind == "extra":
        if not isinstance(v, dict):
            return None
        v["zz_unknown_field"] = 1
    return doc


def spoiled_documents():
    """(сцена, путь, порча, документ) — каждое место схемы ровно один раз."""
    seen = set()
    for name, doc in GOOD:
        for where, sig in list(places(doc)):
            if sig in seen:
                continue
            seen.add(sig)
            for kind in KINDS:
                bad = spoil(doc, where, kind)
                if bad is not None:
                    yield name, where, kind, bad, sig


@pytest.mark.parametrize("name, doc", GOOD, ids=GOOD_IDS)
def test_good_scenes_pass_jsonschema(name, doc):
    errors = [e.message for e in JSONSCHEMA.iter_errors(doc)]
    assert errors == []


def test_schema_checker_sees_everything_jsonschema_sees():
    missed, caught = [], 0
    for name, where, kind, bad, _ in spoiled_documents():
        if JSONSCHEMA.is_valid(bad):
            continue                                   # такая порча схеме не мешает
        caught += 1
        if not list(CHECKER.check(bad)):
            missed.append("%s %s: %s" % (name, "/".join(map(str, where)), kind))
    assert caught > 150                                # порча действительно ломает схему
    assert missed == [], "jsonschema видит ошибку, а validate.py — нет (поправить validate.py " \
                         "вместе с Никитой):\n" + "\n".join(missed)


def test_spoiling_covers_every_shape_and_rotation():
    tags = {part for *_, sig in spoiled_documents() for part in sig if part.startswith("<")}
    assert {"<box>", "<cylinder>", "<cone>", "<sphere>", "<torus>", "<boolean>", "<mesh>",
            "<identity>", "<matrix_active>", "<euler_xyz_extrinsic_deg>"} <= tags
