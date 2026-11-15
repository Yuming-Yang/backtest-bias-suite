"""Strategies the suite runs inside engines.

Each trap's strategy reads only the data its trap is about (SPEC.md,
"Isolation between traps"). None of them reads ``View.weights``, so an
engine that cannot report current holdings during the run can still be
tested.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from btbias.protocol import View


@dataclass(frozen=True)
class ScheduledWeights:
    """Returns a precomputed row of weights for each decision date.

    It ignores prices entirely, so a view that leaks future prices cannot
    change its orders.
    """

    schedule: pd.DataFrame
    name: str = "scheduled-weights"

    def target_weights(self, view: View) -> pd.Series:
        return self.schedule.loc[view.as_of].copy()
