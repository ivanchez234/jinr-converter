"""Командная строка mcscene.

Коды выхода: 0 — успех, 1 — ошибки в сцене, 2 — неверный вызов или файл не читается.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import __version__
from .diagnostics import print_diagnostics

TARGETS = ["geant4"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mcscene",
                                description="Генератор моделей Монте-Карло из сцены jinr-mc-scene.")
    p.add_argument("--version", action="version", version="mcscene " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="команда")

    v = sub.add_parser("validate", help="проверить сцену",
                       description="Проверить scene.json по контракту v0.1 и разобрать в Scene IR.")
    v.add_argument("scenes", nargs="+", metavar="scene.json")
    _common(v)

    c = sub.add_parser("check", help="что генератор сделает с каждым телом",
                       description="Проверить сцену и показать по строке на тело: "
                                   "умеет ли цель его построить и почему нет.")
    c.add_argument("scene", metavar="scene.json")
    c.add_argument("-t", "--target", choices=TARGETS, default="geant4", help="цель (по умолчанию geant4)")
    c.add_argument("--plan", action="store_true",
                   help="напечатать план генерации (JSON): мир, материалы, тела, пробные точки")
    _common(c)

    args = p.parse_args(argv)
    if args.cmd == "validate":
        return cmd_validate(args.scenes, strict=args.strict, verbose=args.verbose)
    if args.cmd == "check":
        return cmd_check(args.scene, strict=args.strict, verbose=args.verbose, show_plan=args.plan)
    return 2


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strict", action="store_true",
                   help="предупреждения считаются ошибками (так проверять перед отправкой)")
    p.add_argument("--verbose", action="store_true", help="показывать и справочные сообщения INFO")


def cmd_validate(paths: list[str], strict: bool, verbose: bool) -> int:
    from .io.load import load_and_validate

    worst = 0
    for i, path in enumerate(paths):
        if i:
            print()
        print("== %s%s" % (path, " (strict)" if strict else ""))
        scene, diags = load_and_validate(path, strict=strict)
        print_diagnostics(diags, verbose=verbose)
        if scene is not None and verbose:
            print("Scene IR: тел %d, материалов %d" % (len(scene.bodies), len(scene.materials)))
        if any(d.code == "E001" for d in diags):
            worst = max(worst, 2)
        elif scene is None:
            worst = max(worst, 1)
    return worst


def cmd_check(path: str, strict: bool, verbose: bool, show_plan: bool) -> int:
    from .backends.geant4.plan import build_plan
    from .io.load import load_and_validate

    scene, diags = load_and_validate(path, strict=strict)
    if scene is None:
        print("== %s: сцена не прошла проверку контракта" % path)
        print_diagnostics(diags, verbose=verbose)
        return 2 if any(d.code == "E001" for d in diags) else 1

    result = build_plan(scene, path)
    diags = diags + result.diagnostics

    print("== %s -> geant4" % path)
    w_id = max([len("id")] + [len(r.body_id) for r in result.rows])
    w_type = max([len("тип")] + [len(r.shape_type) for r in result.rows])
    print("%-*s  %-*s  %-11s %s" % (w_id, "id", w_type, "тип", "действие", "примечание"))
    for r in result.rows:
        print(("%-*s  %-*s  %-11s %s" % (w_id, r.body_id, w_type, r.shape_type, r.action, r.note)).rstrip())

    shown = [d for d in diags if verbose or d.level != "INFO"]
    if shown:
        print()
        print_diagnostics(diags, verbose=verbose, summary=False)

    ne = sum(1 for d in diags if d.level == "ERROR")
    nw = sum(1 for d in diags if d.level == "WARN")
    print()
    print("итог: %d %s, %d %s, %d %s -> %s" % (
        len(result.rows), plural(len(result.rows), "тело", "тела", "тел"),
        ne, plural(ne, "ошибка", "ошибки", "ошибок"),
        nw, plural(nw, "предупреждение", "предупреждения", "предупреждений"),
        "можно генерировать" if result.plan is not None else "генерировать нельзя"))

    if show_plan and result.plan is not None:
        print()
        print(dump_json(asdict(result.plan)))
    return 0 if result.plan is not None else 1


def dump_json(obj, indent: int = 0) -> str:
    """JSON с отступами, но векторы и матрицы — в одну строку: [310, -130, 115]."""
    pad, inner = "  " * indent, "  " * (indent + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = ['%s%s: %s' % (inner, json.dumps(k, ensure_ascii=False), dump_json(v, indent + 1))
                 for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, (list, tuple)):
        if _is_numeric(obj):
            return json.dumps(obj)
        if not obj:
            return "[]"
        items = [inner + dump_json(v, indent + 1) for v in obj]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return json.dumps(obj, ensure_ascii=False)


def _is_numeric(seq) -> bool:
    return all(isinstance(x, (int, float)) or (isinstance(x, (list, tuple)) and _is_numeric(x))
               for x in seq)


def plural(n: int, one: str, few: str, many: str) -> str:
    """1 тело, 2 тела, 5 тел; 11 тел, 21 тело."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


if __name__ == "__main__":
    sys.exit(main())
