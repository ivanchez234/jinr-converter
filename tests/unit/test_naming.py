"""Имена объёмов и C++ функций (правила цели geant4: Geant4Naming)."""
import json
import re

import pytest

from mcscene.backends.geant4.naming import Geant4Naming
from mcscene.diagnostics import Diagnostics
from mcscene.model import Scene
from mcscene.paths import CONTRACT_V0_1, all_test_scenes, scene_id


def run(p, scene):
    """Проход над сценой -> (результат, сообщения)."""
    diags = Diagnostics()
    return p.run(scene, diags), diags


CPP_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def test_plain_ids_are_kept(scene, box):
    names, diags = run(Geant4Naming(), scene(box("Body", (1, 1, 1)), box("pipe_bore", (1, 1, 1), (5, 0, 0))))
    assert diags == []
    assert names["Body"].volume == "Body" and names["Body"].func == "BuildBody_Body"
    assert names["pipe_bore"].func == "BuildBody_pipe_bore"


def test_dash_becomes_underscore_in_function_only(scene, box):
    names, diags = run(Geant4Naming(), scene(box("beam-pipe", (1, 1, 1))))
    assert diags == []
    assert names["beam-pipe"].volume == "beam-pipe"
    assert names["beam-pipe"].func == "BuildBody_beam_pipe"


def test_collision_after_replacement_gets_suffix(scene, box):
    names, diags = run(Geant4Naming(), scene(box("a-b", (1, 1, 1)), box("a_b", (1, 1, 1), (5, 0, 0))))
    assert names["a-b"].func == "BuildBody_a_b"                  # первый в файле — без суффикса
    assert names["a_b"].func == "BuildBody_a_b_2"
    assert [(d.code, d.body_id) for d in diags] == [("I401", "a_b")]


def test_world_is_reserved(scene, box):
    names, diags = run(Geant4Naming(), scene(box("world", (1, 1, 1))))
    assert names["world"].volume == "world_body"
    assert names["world"].func == "BuildBody_world_body"
    assert [d.code for d in diags] == ["I401"]


def test_world_body_already_taken(scene, box):
    names, _ = run(Geant4Naming(), scene(box("world", (1, 1, 1)), box("world_body", (1, 1, 1), (5, 0, 0))))
    assert names["world_body"].volume == "world_body"
    assert names["world"].volume == "world_body_2"


def test_deterministic(scene, box):
    s = scene(box("a-b", (1, 1, 1)), box("a_b", (1, 1, 1), (5, 0, 0)), box("world", (1, 1, 1), (9, 0, 0)))
    assert run(Geant4Naming(), s) == run(Geant4Naming(), s)


GOOD = sorted((CONTRACT_V0_1 / "examples").glob("*.json")) + all_test_scenes()


@pytest.mark.parametrize("path", GOOD, ids=scene_id)
def test_names_unique_and_valid_in_all_scenes(path):
    with open(path, encoding="utf-8") as f:
        names, _ = run(Geant4Naming(), Scene.model_validate(json.load(f)))
    volumes = [n.volume for n in names.values()]
    funcs = [n.func for n in names.values()]
    assert len(set(volumes)) == len(volumes) and "world" not in volumes
    assert len(set(funcs)) == len(funcs)
    assert all(CPP_IDENT.match(f) for f in funcs)
