"""Command line: ``btbias run TARGET`` and ``btbias matrix``.

``TARGET`` names an adapter as ``package.module:Name`` or
``path/to/file.py:Name``, where ``Name`` is an adapter class (called with no
arguments) or instance. The exit status is 0 only if every trap passes, so
the command can gate CI.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from pathlib import Path

from btbias.matrix import bug_effects, is_diagonal, mutation_matrix, to_markdown
from btbias.protocol import Adapter
from btbias.suite import run_suite
from btbias.traps import ALL_TRAPS


def load_adapter(target: str) -> Adapter:
    module_name, sep, attr = target.rpartition(":")
    if not sep or not module_name or not attr:
        raise SystemExit(f"btbias: expected module:Name or file.py:Name, got {target!r}")
    if module_name.endswith(".py"):
        path = Path(module_name).resolve()
        sys.path.insert(0, str(path.parent))  # so the file can import its neighbours
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"btbias: cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        sys.path.insert(0, str(Path.cwd()))
        module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    adapter = obj() if isinstance(obj, type) else obj
    if not isinstance(adapter, Adapter):
        raise SystemExit(f"btbias: {target} is not an adapter (needs .name and .run)")
    return adapter


def _run(target: str, only: list[str] | None) -> int:
    adapter = load_adapter(target)
    traps = [t for t in ALL_TRAPS if not only or t.id in only]
    unknown = set(only or []) - {t.id for t in ALL_TRAPS}
    if unknown:
        raise SystemExit(f"btbias: unknown trap(s) {sorted(unknown)}")
    report = run_suite(adapter, traps)
    print(f"btbias: {report.adapter}")
    for r in report.results:
        print(f"  {r.trap_id}  {r.status.value.upper():5}  {r.title}")
        if r.detail:
            print(f"        {r.detail}")
    failed = len(report.failed_ids)
    print(f"{len(report.results) - failed} passed, {failed} failed")
    return 0 if report.passed else 1


def _matrix() -> int:
    matrix = mutation_matrix()
    print("Mutation matrix (rows: engines, columns: traps)\n")
    print(to_markdown(matrix))
    print("\nFinal NAV on each trap's scenario, correct engine vs. the matching bug\n")
    columns = ["correct", "with bug", "bug moves NAV by"]
    print(to_markdown(bug_effects(), percent=columns))
    diagonal = is_diagonal(matrix)
    print(f"\nDiagonal: {'yes' if diagonal else 'NO'}")
    return 0 if diagonal else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btbias", description="Check a backtest engine for common biases."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the traps against an adapter")
    run.add_argument("adapter", help="module:Name or path/to/file.py:Name")
    run.add_argument("--trap", action="append", metavar="ID", help="only this trap (repeatable)")
    sub.add_parser("matrix", help="print the mutation matrix and the size of each bug")
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args.adapter, args.trap)
    return _matrix()
