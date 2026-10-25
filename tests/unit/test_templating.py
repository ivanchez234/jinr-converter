"""Шаблоны (этап 2, шаги 2.1–2.4): рендерер Jinja2, пакет шаблонов, запись проекта.

То, что сгенерированный C++ не изменился при переходе на шаблоны, проверяют
golden-тесты (tests/golden) — здесь проверяются сами механизмы.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from mcscene.backends.geant4.backend import TEMPLATES, Geant4Backend
from mcscene.backends.writer import GenerateError, ProjectWriter
from mcscene.paths import REPO
from mcscene.templating import PackError, TemplateError, TemplatePack, TemplateRenderer


def write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


# --- рендерер -------------------------------------------------------------------
def test_typo_in_template_is_an_error_with_place(tmp_path):
    write(tmp_path, {"a.txt.j2": "строка 1\n{{ scene_nmae }}\n"})
    with pytest.raises(TemplateError, match=r"a\.txt\.j2, строка 2: 'scene_nmae' is undefined"):
        TemplateRenderer([tmp_path]).render("a.txt.j2", {"scene_name": "kub"})


def test_typo_in_attribute_is_an_error(tmp_path):
    write(tmp_path, {"a.txt.j2": "{{ plan.scene_nmae }}\n"})
    with pytest.raises(TemplateError, match="scene_nmae"):
        TemplateRenderer([tmp_path]).render("a.txt.j2", {"plan": {"scene_name": "kub"}})


def test_block_lines_leave_no_trace(tmp_path):
    # строки с {% for %} / {% if %} не дают пустых строк, а пустая строка в шаблоне — даёт
    write(tmp_path, {"a.txt.j2": "{% for x in xs %}\n  {{ x }}\n{% endfor %}\n\n{% if flag %}\nда\n{% endif %}\nконец\n"})
    out = TemplateRenderer([tmp_path]).render("a.txt.j2", {"xs": [1, 2], "flag": True})
    assert out == "  1\n  2\n\nда\nконец\n"


def test_nothing_is_escaped(tmp_path):
    write(tmp_path, {"a.txt.j2": "{{ s }}\n"})
    assert TemplateRenderer([tmp_path]).render("a.txt.j2", {"s": '<"a" & b>'}) == '<"a" & b>\n'


def test_filters_are_used(tmp_path):
    write(tmp_path, {"a.txt.j2": "{{ x|twice }}\n"})
    assert TemplateRenderer([tmp_path], {"twice": lambda v: v * 2}).render("a.txt.j2", {"x": 21}) == "42\n"


def test_syntax_error_names_template_and_line(tmp_path):
    write(tmp_path, {"a.txt.j2": "строка 1\n{% for x in xs %}\n{{ x }}\n"})
    with pytest.raises(TemplateError, match=r"a\.txt\.j2, строка \d"):
        TemplateRenderer([tmp_path]).render("a.txt.j2", {"xs": []})


def test_missing_template(tmp_path):
    with pytest.raises(TemplateError, match="нет шаблона b.txt.j2"):
        TemplateRenderer([tmp_path]).render("b.txt.j2", {})


def test_first_folder_in_search_path_wins(tmp_path):
    mine = write(tmp_path / "mine", {"a.txt.j2": "мой\n"})
    builtin = write(tmp_path / "builtin", {"a.txt.j2": "встроенный\n", "b.txt.j2": "только встроенный\n"})
    r = TemplateRenderer([mine, builtin])
    assert r.render("a.txt.j2", {}) == "мой\n"
    assert r.render("b.txt.j2", {}) == "только встроенный\n"


# --- пакет шаблонов ---------------------------------------------------------------
def make_pack(tmp_path, manifest: dict, files=("CMake.txt.j2", "gen/a.cc.j2", "user/u.hh.j2", "_macros.j2")):
    write(tmp_path, {f: "" for f in files})
    (tmp_path / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return TemplatePack(tmp_path)


GOOD = {"target": "demo", "generated": ["CMake.txt.j2", "gen/a.cc.j2"], "user": ["user/u.hh.j2"],
        "copy": [{"from": "lib", "to": "lib", "dirs": ["src"]}]}


def test_pack_reads_manifest(tmp_path):
    p = make_pack(tmp_path, GOOD)
    assert [(f.template, f.output) for f in p.files] == [
        ("CMake.txt.j2", "CMake.txt"), ("gen/a.cc.j2", "gen/a.cc"), ("user/u.hh.j2", "user/u.hh")]
    assert p.owned_dirs == ("gen", "lib")
    assert p.top_files == ("CMake.txt",)
    assert p.user_dirs == ("user",)


@pytest.mark.parametrize("change, message", [
    (lambda m: m["generated"].append("gen/nope.cc.j2"), "нет шаблона gen/nope.cc.j2"),
    (lambda m: m["generated"].append("_macros.j2"), "общий кусок"),
    (lambda m: m["generated"].append("gen/a.cc"), r"\*\.j2"),
    (lambda m: m["generated"].append("../evil.j2"), "внутри пакета"),
    (lambda m: m["generated"].append("gen/a.cc.j2"), "дважды"),
    (lambda m: m.update(user=["gen/u.hh.j2"]), "принадлежит пользователю"),
    (lambda m: m.update(user=["u.hh.j2"]), "в своей папке"),
    (lambda m: m.update(extra=1), "неизвестные поля extra"),
    (lambda m: m["copy"].append({"from": "x"}), "from и to"),
], ids=["missing", "partial", "not-j2", "outside", "twice", "user-clash", "user-top", "unknown-key", "copy"])
def test_bad_pack_is_rejected_before_writing(tmp_path, change, message):
    manifest = json.loads(json.dumps(GOOD))
    change(manifest)
    with pytest.raises(PackError, match=message):
        make_pack(tmp_path, manifest, files=("CMake.txt.j2", "gen/a.cc.j2", "user/u.hh.j2", "_macros.j2",
                                             "gen/u.hh.j2", "u.hh.j2"))


def test_geant4_pack():
    p = Geant4Backend().pack
    assert p.target == "geant4"
    assert p.owned_dirs == ("generated", "harness", "app", "g4scene")
    assert p.top_files == ("CMakeLists.txt",)
    assert [f.output for f in p.user] == ["user/DetectorConstruction.hh"]


def test_geant4_pack_has_no_forgotten_templates():
    # каждый шаблон либо выводится в проект (есть в pack.json), либо общий кусок «_…»
    listed = {f.template for f in Geant4Backend().pack.files}
    on_disk = {p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.j2")}
    assert {t for t in on_disk if not Path(t).name.startswith("_")} == listed


# --- C++ только в пакете шаблонов -------------------------------------------------
CPP = re.compile(r"\bnew G4|\bG4[A-Z]\w*\(|scene::|\*mm\b|#include")
ALLOWED = {"python/mcscene/backends/geant4/filters.py"}       # как значения пишутся в C++


def string_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.lineno, node.value


def test_no_cpp_in_python():
    found = []
    for path in sorted((REPO / "python" / "mcscene").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWED:
            continue
        found += ["%s:%d: %r" % (rel, line, s) for line, s in string_literals(path) if CPP.search(s)]
    assert found == [], "синтаксис C++ должен жить в templates/ (и filters.py):\n" + "\n".join(found)


def test_no_cpp_check_catches_cpp():
    # проверка самой проверки: строка с C++ в коде была бы найдена
    assert CPP.search('"new G4Box(%s, %s)" % (a, b)') and CPP.search('"scene::Nist(%s)"')
    assert not CPP.search("коробка 20 × 40 × 70 мм")


# --- запись проекта по пакету (общая для всех целей) -------------------------------
def demo_writer(tmp_path):
    p = make_pack(tmp_path / "pack", GOOD)
    lib = write(tmp_path / "lib", {"src/x.cc": "x", "tests/t.cc": "не копируется"})
    return ProjectWriter(p, {"lib": lib})


def test_writer_follows_pack(tmp_path):
    w = demo_writer(tmp_path)
    out = tmp_path / "out"
    res = w.write(out, {"CMake.txt": "c\n", "gen/a.cc": "a\n", "report.json": "{}\n"}, {"user/u.hh": "u\n"})
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert files == [".mcscene", "CMake.txt", "gen/a.cc", "lib/src/x.cc", "report.json", "user/u.hh"]
    assert res.user_created == ["user/u.hh"] and res.user_kept == []
    assert (out / ".mcscene").read_text("utf-8") == (
        "Эту папку создал mcscene. При mcscene generate --force перезаписываются\n"
        "gen/, lib/, CMake.txt и report.json;\n"
        "user/ и build/ не трогаются никогда.\n")

    (out / "user/u.hh").write_text("моя правка\n", encoding="utf-8")
    (out / "gen/old.cc").write_text("старый\n", encoding="utf-8")
    with pytest.raises(GenerateError, match="--force"):
        w.write(out, {"gen/a.cc": "a2\n"}, {"user/u.hh": "u2\n"})
    res = w.write(out, {"gen/a.cc": "a2\n"}, {"user/u.hh": "u2\n"}, force=True)
    assert (out / "user/u.hh").read_text("utf-8") == "моя правка\n"   # user/ не тронут
    assert not (out / "gen/old.cc").exists()                          # gen/ пересоздан
    assert res.user_kept == ["user/u.hh"]


def test_writer_needs_every_copy_source(tmp_path):
    p = make_pack(tmp_path / "pack", GOOD)
    with pytest.raises(GenerateError, match="lib"):
        ProjectWriter(p, {})
