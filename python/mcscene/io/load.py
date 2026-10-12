"""Чтение и проверка сцены: JSON -> диагностики -> Scene IR.

Порядок:
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
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ..diagnostics import Diagnostic, has_errors
from ..model.scene import Scene
from .contract import load_contract_validator, load_schema


def load_and_validate(path: str | os.PathLike, strict: bool = False
                      ) -> tuple[Scene | None, list[Diagnostic]]:
    """Возвращает (Scene или None, диагностики). Scene есть только при отсутствии ошибок."""
    v = load_contract_validator()
    rep = v.Report(strict)
    path = str(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        rep.error("E001", path, "не удалось открыть: %s" % e)
        return None, _diags(rep)
    except ValueError as e:
        rep.error("E001", path, "это не JSON: %s" % e)
        return None, _diags(rep)

    v.validate_document(doc, os.path.dirname(os.path.abspath(path)), rep, load_schema())
    diags = _diags(rep)
    if has_errors(diags):
        return None, diags

    clean = drop_fields(doc, [d.where for d in diags if d.code == "W100"])

    diags += crosscheck_schema(clean)
    if has_errors(diags):
        return None, diags

    try:
        scene = Scene.model_validate(clean)
    except ValidationError as e:
        for err in e.errors():
            where = "/" + "/".join(str(x) for x in err["loc"])
            diags.append(Diagnostic(
                "ERROR", "E902", where,
                "файл прошёл проверку контракта, но не разобрался в модели mcscene: %s "
                "(расхождение моделей со схемой — это ошибка mcscene)" % err["msg"]))
        return None, diags

    return scene, diags


def crosscheck_schema(doc: dict) -> list[Diagnostic]:
    """Стандартный jsonschema против уже проверенного validate.py документа."""
    validator = Draft202012Validator(load_schema())
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        where = "/" + "/".join(str(x) for x in err.absolute_path)
        out.append(Diagnostic(
            "ERROR", "E901", where,
            "jsonschema нашёл ошибку, которую пропустил validate.py: %s "
            "(сообщите Никите, нужно поправить контракт)" % err.message))
    return out


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
