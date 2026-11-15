"""Strategies the suite runs inside engines.

Each trap's strategy reads only the data its trap is about (SPEC.md,
"Isolation between traps"). None of them reads ``View.weights``, so an
engine that cannot report current holdings during the run can still be
tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from btbias.generator import MAX_GROSS
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


def top_mover(close: pd.DataFrame) -> pd.Series:
    """Put ``MAX_GROSS`` in the asset with the best return over the last row.

    "The last row" is whatever the view ends with. On a correct view that is
    today's close; on a view that leaks one day ahead it is tomorrow's, and
    the strategy turns into a perfect forecaster.
    """
    if len(close) < 2:
        return pd.Series(dtype=float)
    last_return = close.iloc[-1] / close.iloc[-2] - 1
    return pd.Series({last_return.idxmax(): MAX_GROSS})


@dataclass
class Momentum:
    """Holds yesterday's best performer, and records every view it is shown.

    It is both an outcome strategy (its NAV depends on the prices it sees)
    and a probe (the recorded views show exactly what the engine exposed).
    """

    name: str = "momentum"
    seen: list[View] = field(default_factory=list)

    def target_weights(self, view: View) -> pd.Series:
        self.seen.append(view)
        return top_mover(view.close)
