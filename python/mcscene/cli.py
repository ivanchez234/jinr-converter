"""Командная строка mcscene — тонкая обёртка над Converter (api.py).

Здесь только разбор аргументов и печать. Вся работа — в Converter: тот же вход
использует аддон FreeCAD, поэтому терминал и кнопка в аддоне делают одно и то же.

Коды выхода: 0 — успех, 1 — ошибки в сцене, 2 — неверный вызов, файл не читается
или папка занята.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import __version__
from .api import CheckReport, Converter, Status, targets, validate
from .backends import get_backend
from .diagnostics import Diagnostic, print_diagnostics
from .templating import PackError, TemplateError

EXIT = {Status.OK: 0, Status.INVALID: 1, Status.UNSUPPORTED: 1,
        Status.UNREADABLE: 2, Status.WRITE_FAILED: 2}


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
    _target(c)
    c.add_argument("--plan", action="store_true",
                   help="напечатать план генерации (JSON): мир, материалы, тела, пробные точки")
    _common(c)

    g = sub.add_parser("generate", help="сгенерировать проект для цели (сейчас — Geant4)",
                       description="Проверить сцену и записать готовый проект цели. Для Geant4 — "
                                   "CMake-проект: геометрия, стенд проверки и копия g4scene. "
                                   "Компиляция — отдельный шаг (cmake).")
    g.add_argument("scene", metavar="scene.json")
    _target(g)
    g.add_argument("-o", "--out", required=True, metavar="ПАПКА", help="куда записать проект, например out/kub")
    g.add_argument("--force", action="store_true",
                   help="перезаписать уже сгенерированный проект (user/ и build/ не трогаются)")
    g.add_argument("--unsafe-skip-checks", action="store_true",
                   help="ОТЛАДКА: генерировать, даже если сцена нарушает геометрические правила "
                        "контракта (E220, E240, E250, E251) — чтобы убедиться, что стенд это поймает")
    _common(g)

    sub.add_parser("targets", help="какие цели есть", description="Показать цели генерации.")

    args = p.parse_args(argv)
    try:
        if args.cmd == "validate":
            return cmd_validate(args.scenes, strict=args.strict, verbose=args.verbose)
        if args.cmd == "check":
            return cmd_check(args.scene, args.target, strict=args.strict, verbose=args.verbose,
                             show_plan=args.plan)
        if args.cmd == "generate":
            return cmd_generate(args.scene, args.out, args.target, force=args.force, strict=args.strict,
                                verbose=args.verbose, unsafe=args.unsafe_skip_checks)
        if args.cmd == "targets":
            return cmd_targets()
    except (TemplateError, PackError) as e:
        # ошибка в пакете шаблонов, а не в сцене: показать шаблон и строку, без traceback
        print("ОШИБКА В ШАБЛОНАХ: %s" % e)
        return 2
    return 2


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strict", action="store_true",
                   help="предупреждения считаются ошибками (так проверять перед отправкой)")
    p.add_argument("--verbose", action="store_true", help="показывать и справочные сообщения INFO")


def _target(p: argparse.ArgumentParser) -> None:
    p.add_argument("-t", "--target", choices=targets(), default="geant4",
                   help="цель (по умолчанию geant4; список — mcscene targets)")


# --- команды -------------------------------------------------------------------
def cmd_validate(paths: list[str], strict: bool, verbose: bool) -> int:
    worst = 0
    for i, path in enumerate(paths):
        if i:
            print()
        print("== %s%s" % (path, " (strict)" if strict else ""))
        v = validate(path, strict=strict)
        print_diagnostics(v.diagnostics, verbose=verbose)
        if v.ok and verbose:
            print("Scene IR: тел %d, материалов %d" % (len(v.model.bodies), len(v.model.materials)))
        worst = max(worst, EXIT[v.status])
    return worst


def cmd_check(path: str, target: str, strict: bool, verbose: bool, show_plan: bool) -> int:
    report = Converter(target).check(path, strict=strict)
    if report.status in (Status.UNREADABLE, Status.INVALID):
        print("== %s: сцена не прошла проверку контракта" % path)
        print_diagnostics(report.diagnostics, verbose=verbose)
        return EXIT[report.status]

    print("== %s -> %s" % (path, target))
    _print_check(report, verbose)
    if show_plan and report.plan is not None:
        print()
        print(dump_json(asdict(report.plan)))
    return EXIT[report.status]


def cmd_generate(path: str, out: str, target: str, force: bool, strict: bool, verbose: bool,
                 unsafe: bool = False) -> int:
    r = Converter(target).generate(path, out, force=force, strict=strict, unsafe_skip_checks=unsafe)
    if r.status in (Status.UNREADABLE, Status.INVALID):
        print("== %s: сцена не прошла проверку контракта, файлы не записаны" % path)
        print_diagnostics(r.diagnostics, verbose=verbose)
        return EXIT[r.status]

    print("== %s -> %s -> %s" % (path, target, out))
    if unsafe:
        print("ВНИМАНИЕ: --unsafe-skip-checks — геометрические проверки контракта пропущены, "
              "проект только для отладки")
    if r.status is Status.UNSUPPORTED:
        _print_check(r, verbose)
        print("файлы не записаны")
        return EXIT[r.status]
    if r.status is Status.WRITE_FAILED:
        print("ОШИБКА: %s" % r.error)
        return EXIT[r.status]

    if _shown(r.diagnostics, verbose):
        print_diagnostics(r.diagnostics, verbose=verbose, summary=False)
    print("записано файлов: %d (тел: %d)" % (len(r.files), len(r.rows)))
    for rel in r.user_created:
        print("%s: создан" % rel)
    for rel in r.user_kept:
        print("%s: уже был, не тронут" % rel)
    if r.next_steps:
        print()
        print("Дальше:")
        for line in r.next_steps:
            print("  " + line)
    return 0


def cmd_targets() -> int:
    for name in targets():
        print("%-8s %s" % (name, get_backend(name).description))
    return 0


# --- печать ----------------------------------------------------------------------
def _shown(diags: list[Diagnostic], verbose: bool) -> bool:
    return any(verbose or d.level != "INFO" for d in diags)


def _print_check(report: CheckReport, verbose: bool) -> None:
    rows, diags = report.rows, report.diagnostics
    w_id = max([len("id")] + [len(r.body_id) for r in rows])
    w_type = max([len("тип")] + [len(r.shape_type) for r in rows])
    print("%-*s  %-*s  %-11s %s" % (w_id, "id", w_type, "тип", "действие", "примечание"))
    for r in rows:
        print(("%-*s  %-*s  %-11s %s" % (w_id, r.body_id, w_type, r.shape_type, r.action, r.note)).rstrip())

    if _shown(diags, verbose):
        print()
        print_diagnostics(diags, verbose=verbose, summary=False)

    ne = sum(1 for d in diags if d.level == "ERROR")
    nw = sum(1 for d in diags if d.level == "WARN")
    print()
    print("итог: %d %s, %d %s, %d %s -> %s" % (
        len(rows), plural(len(rows), "тело", "тела", "тел"),
        ne, plural(ne, "ошибка", "ошибки", "ошибок"),
        nw, plural(nw, "предупреждение", "предупреждения", "предупреждений"),
        "можно генерировать" if report.plan is not None else "генерировать нельзя"))


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
