"""The mutation matrix, and how much each bug moves a backtest.

Rows are engines (the reference engine, then one mutant per trap), columns
are traps. The suite is sharp if each mutant fails its own trap, and
specific if it passes every other one, so a good matrix is "fail" on the
diagonal and "pass" everywhere else.

``bug_effects`` puts a size on each bug: the mutant's final NAV against the
reference engine's, on the scenario of the trap that catches it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from btbias.mutants import MUTANTS
from btbias.reference import ReferenceEngine
from btbias.trap import Trap, run_trap
from btbias.traps import ALL_TRAPS

REFERENCE_ROW = "reference"


def mutation_matrix(
    traps: Sequence[Trap] = ALL_TRAPS,
    mutants: Mapping[str, type[ReferenceEngine]] = MUTANTS,
) -> pd.DataFrame:
    """Status of every engine on every trap, as ``"pass"``, ``"fail"`` or ``"error"``."""
    engines = {REFERENCE_ROW: ReferenceEngine(), **{k: m() for k, m in mutants.items()}}
    return pd.DataFrame(
        {t.id: {row: run_trap(e, t).status.value for row, e in engines.items()} for t in traps}
    )


def is_diagonal(matrix: pd.DataFrame) -> bool:
    """True if the reference passes everything and each mutant fails only its own trap."""
    for row, statuses in matrix.iterrows():
        for trap_id, status in statuses.items():
            want = "fail" if row == trap_id else "pass"
            if status != want:
                return False
    return True


def bug_effects(
    traps: Sequence[Trap] = ALL_TRAPS,
    mutants: Mapping[str, type[ReferenceEngine]] = MUTANTS,
) -> pd.DataFrame:
    """Final NAV of each mutant and of the reference engine on its trap's scenario."""
    rows = {}
    for trap in traps:
        scenario, strategy = trap.build()
        correct = ReferenceEngine().run(scenario, strategy).nav.iloc[-1]
        scenario, strategy = trap.build()
        buggy = mutants[trap.id]().run(scenario, strategy).nav.iloc[-1]
        start = scenario.initial_cash
        rows[trap.id] = {
            "trap": trap.title,
            "correct": correct / start - 1,
            "with bug": buggy / start - 1,
            "bug moves NAV by": buggy / correct - 1,
        }
    return pd.DataFrame(rows).T


def to_markdown(frame: pd.DataFrame, percent: Sequence[str] = ()) -> str:
    """A GitHub-flavoured Markdown table, without needing ``tabulate``."""

    def cell(col: str, value: object) -> str:
        if col in percent:
            return f"{round(float(value), 6) + 0.0:+.1%}"  # + 0.0 turns -0.0 into 0.0
        return f"**{value}**" if value == "fail" else str(value)

    header = ["", *map(str, frame.columns)]
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    for index, row in frame.iterrows():
        cells = [str(index), *(cell(c, v) for c, v in row.items())]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
