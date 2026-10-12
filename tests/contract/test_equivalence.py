"""Главный тест этапа 0: mcscene validate выносит тот же вердикт, что validate.py.

Прогоняется на всех примерах контракта (хороших и плохих) и на всех сценах из
tests/scenes, в строгом и обычном режиме.
"""
import pytest

from mcscene.io.contract import load_contract_validator
from mcscene.io.load import load_and_validate
from mcscene.paths import CONTRACT_V0_1, TEST_SCENES

V = load_contract_validator()

GOOD = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + sorted(TEST_SCENES.glob("*.json"))
BAD = sorted((CONTRACT_V0_1 / "bad").glob("*.json"))


def test_fixture_sets_are_complete():
    # если примеры пропали или переехали, остальные тесты молча прошли бы на пустом списке
    assert len(list((CONTRACT_V0_1 / "examples").glob("*.json"))) == 5
    assert len(BAD) == 8
    assert len(list(TEST_SCENES.glob("*.json"))) >= 3


@pytest.mark.parametrize("strict", [True, False], ids=["strict", "normal"])
@pytest.mark.parametrize("path", GOOD + BAD, ids=lambda p: p.name)
def test_same_verdict_as_validate_py(path, strict):
    ref = V.validate_file(str(path), strict=strict)
    scene, ours = load_and_validate(path, strict=strict)

    ref_err = {i.code for i in ref if i.level == "ERROR"}
    our_err = {d.code for d in ours if d.level == "ERROR"}
    assert bool(ref_err) == bool(our_err), [d for d in ours if d.level == "ERROR"]
    assert ref_err <= our_err                      # все коды validate.py есть и у нас
    assert (scene is None) == bool(our_err)        # Scene IR есть ровно тогда, когда нет ошибок


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.name)
def test_good_scenes_parse_into_models(path):
    scene, diags = load_and_validate(path, strict=True)
    assert scene is not None, [d for d in diags if d.level == "ERROR"]


@pytest.mark.parametrize("path", BAD, ids=lambda p: p.name)
def test_bad_examples_are_rejected(path):
    scene, diags = load_and_validate(path, strict=True)
    assert scene is None
    assert any(d.level == "ERROR" for d in diags)


def test_b01_half_sizes_gives_E220():
    _, diags = load_and_validate(CONTRACT_V0_1 / "bad" / "b01_half_sizes.json", strict=False)
    assert "E220" in {d.code for d in diags if d.level == "ERROR"}
