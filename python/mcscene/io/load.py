"""Чтение и проверка сцены: JSON -> диагностики -> Scene IR (класс SceneLoader).

Порядок шагов:
  1. читаем JSON (ошибка чтения -> E001, как в validate.py);
  2. validate.py: формат, структура по схеме, ссылки, геометрия;
  3. если ошибок нет — вторая проверка структуры стандартным jsonschema
     (страховка от пробелов в мини-валидаторе validate.py, код E901);
  4. разбор в pydantic-модели Scene IR (код E902, если модель разошлась со схемой).

Неизвестные поля без --strict validate.py считает предупреждением (W100):
файл более новой версии, поле никто не читает. Поэтому перед шагами 3–4 такие
поля отбрасываются, как и обещает контракт.
"""
from __future__ import annotations

import copy
import json
import os

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ..diagnostics import Diagnostic, Diagnostics
from ..model.scene import Scene
from .contract import load_contract_validator, load_schema

# Геометрические ошибки контракта, которые можно обойти флагом --unsafe-skip-checks:
# объём (E220), bbox (E240), ребёнок торчит из родителя (E250), соседи пересекаются (E251).
# Ровно это должен ловить стенд check_geometry; флаг нужен, чтобы проверить, что он ловит.
# Битые ссылки, структура и меши не обходятся: с ними генератор не сможет работать вообще.
UNSAFE_SKIPPABLE = frozenset({"E220", "E240", "E250", "E251"})


class SceneLoader:
    """Читает scene.json и проверяет его по контракту.

    strict — предупреждения считаются ошибками (так проверять перед отправкой);
    unsafe_skip_checks — ОТЛАДКА: ошибки из UNSAFE_SKIPPABLE превращаются в
    предупреждения с пометкой, и сцена всё равно разбирается.
    """

    def __init__(self, strict: bool = False, unsafe_skip_checks: bool = False) -> None:
        self.strict = strict
        self.unsafe_skip_checks = unsafe_skip_checks

    def load(self, path: str | os.PathLike) -> tuple[Scene | None, list[Diagnostic]]:
        """(Scene или None, диагностики). Scene есть, только если ошибок нет."""
        v = load_contract_validator()
        rep = v.Report(self.strict)
        path = str(path)

        doc = self._read(path, rep)
        if doc is None:
            return None, _diags(rep)

        v.validate_document(doc, os.path.dirname(os.path.abspath(path)), rep, load_schema())
        diags = Diagnostics(_diags(rep))
        if self.unsafe_skip_checks:
            diags = Diagnostics(self._soften(d) for d in diags)
        if diags.has_errors:
            return None, list(diags)

        clean = drop_fields(doc, [d.where for d in diags if d.code == "W100"])
        diags += self.crosscheck_schema(clean)
        if diags.has_errors:
            return None, list(diags)
        return self._parse(clean, diags), list(diags)

    # --- шаги ------------------------------------------------------------------------
    @staticmethod
    def _read(path: str, rep):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except OSError as e:
            rep.error("E001", path, "не удалось открыть: %s" % e)
        except ValueError as e:
            rep.error("E001", path, "это не JSON: %s" % e)
        return None

    @staticmethod
    def _soften(d: Diagnostic) -> Diagnostic:
        if d.level == "ERROR" and d.code in UNSAFE_SKIPPABLE:
            return Diagnostic("WARN", d.code, d.where, "[пропущено --unsafe-skip-checks] " + d.message,
                              d.body_id, d.target)
        return d

    @staticmethod
    def crosscheck_schema(doc: dict) -> list[Diagnostic]:
        """Стандартный jsonschema против уже проверенного validate.py документа."""
        validator = Draft202012Validator(load_schema())
        out = Diagnostics()
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
            out.error("E901", "/" + "/".join(str(x) for x in err.absolute_path),
                      "jsonschema нашёл ошибку, которую пропустил validate.py: %s "
                      "(сообщите Никите, нужно поправить контракт)" % err.message)
        return list(out)

    @staticmethod
    def _parse(doc: dict, diags: Diagnostics) -> Scene | None:
        try:
            return Scene.model_validate(doc)
        except ValidationError as e:
            for err in e.errors():
                diags.error("E902", "/" + "/".join(str(x) for x in err["loc"]),
                            "файл прошёл проверку контракта, но не разобрался в модели mcscene: %s "
                            "(расхождение моделей со схемой — это ошибка mcscene)" % err["msg"])
            return None


def load_and_validate(path: str | os.PathLike, strict: bool = False,
                      unsafe_skip_checks: bool = False) -> tuple[Scene | None, list[Diagnostic]]:
    """Короткая запись SceneLoader(strict, unsafe_skip_checks).load(path)."""
    return SceneLoader(strict, unsafe_skip_checks).load(path)


def drop_fields(doc: dict, paths: list[str]) -> dict:
    """Копия документа без полей по путям вида /bodies/0/shape/colour."""
    if not paths:
        return doc
    doc = copy.deepcopy(doc)
    for p in paths:
        parts = [s for s in p.split("/") if s]
        node = doc
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node.get(part)
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return doc


def _diags(rep) -> list[Diagnostic]:
    return [Diagnostic.from_issue(i) for i in rep.items]
