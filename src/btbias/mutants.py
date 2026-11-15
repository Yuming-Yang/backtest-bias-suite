"""Deliberately broken engines, one bug each.

Every mutant is the reference engine with exactly one method overridden.
The mutation matrix (tests/test_mutation_matrix.py) checks that each one
fails its own trap and passes every other trap: the first shows the trap
catches the bug, the second shows it does not fire on unrelated ones.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from btbias.protocol import View
from btbias.reference import ReferenceEngine
from btbias.scenario import Scenario


class PeekingEngine(ReferenceEngine):
    """T1: slices price history one day too far, so each view ends tomorrow."""

    name = "mutant-T1-peeking"

    def view(self, scenario: Scenario, t: pd.Timestamp, weights: pd.Series) -> View:
        cal = scenario.calendar
        end = cal[min(cal.get_loc(t) + 1, len(cal) - 1)]  # off by one
        v = super().view(scenario, t, weights)
        return replace(v, open=scenario.open.loc[:end], close=scenario.close.loc[:end])


class SameCloseEngine(ReferenceEngine):
    """T2: fills orders at the close the signal was computed on."""

    name = "mutant-T2-same-close"

    def fill_prices(self, scenario: Scenario, t: pd.Timestamp) -> pd.Series:
        decision_day = scenario.calendar.get_loc(t) - 1
        return scenario.close.iloc[decision_day]


class ZeroCostEngine(ReferenceEngine):
    """T5: ignores the scenario's cost model and trades for free."""

    name = "mutant-T5-zero-cost"

    def transaction_cost(self, scenario: Scenario, notional: float) -> float:
        return 0.0


MUTANTS: dict[str, type[ReferenceEngine]] = {
    "T1": PeekingEngine,
    "T2": SameCloseEngine,
    "T5": ZeroCostEngine,
}
"""Trap id -> the mutant that trap must catch."""
