"""Командная строка mcscene.

Коды выхода: 0 — успех, 1 — ошибки в сцене, 2 — неверный вызов или файл не читается.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .diagnostics import print_diagnostics


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mcscene",
                                description="Генератор моделей Монте-Карло из сцены jinr-mc-scene.")
    p.add_argument("--version", action="version", version="mcscene " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="команда")

    v = sub.add_parser("validate", help="проверить сцену",
                       description="Проверить scene.json по контракту v0.1 и разобрать в Scene IR.")
    v.add_argument("scenes", nargs="+", metavar="scene.json")
    v.add_argument("--strict", action="store_true",
                   help="предупреждения считаются ошибками (так проверять перед отправкой)")
    v.add_argument("--verbose", action="store_true", help="показывать и справочные сообщения INFO")

    args = p.parse_args(argv)
    if args.cmd == "validate":
        return cmd_validate(args.scenes, strict=args.strict, verbose=args.verbose)
    return 2


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


if __name__ == "__main__":
    sys.exit(main())
