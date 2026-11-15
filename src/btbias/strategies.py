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


def equal_weight(universe: tuple[str, ...]) -> pd.Series:
    """Split ``MAX_GROSS`` equally across ``universe``."""
    if not universe:
        return pd.Series(dtype=float)
    return pd.Series(MAX_GROSS / len(universe), index=list(universe))


@dataclass
class EqualWeightUniverse:
    """Holds every asset the engine offers, equally weighted.

    "Hold the index" in its simplest form. It reads only ``View.universe``,
    so its NAV shows what the engine let it hold, and the recorded views
    show what the engine offered on each day.
    """

    name: str = "equal-weight-universe"
    seen: list[View] = field(default_factory=list)

    def target_weights(self, view: View) -> pd.Series:
        self.seen.append(view)
        return equal_weight(view.universe)


def best_reported(fundamentals: pd.DataFrame) -> pd.Series:
    """Put ``MAX_GROSS`` in the asset whose latest known value is highest.

    "Latest known" is the row with the latest period end and, within it, the
    latest publish date, among the rows the view contains. A view that shows
    reports before they are published, or restated values before the
    restatement, changes which asset that is.
    """
    if fundamentals.empty:
        return pd.Series(dtype=float)
    latest = (
        fundamentals.assign(
            period_end=pd.to_datetime(fundamentals["period_end"]),
            publish_date=pd.to_datetime(fundamentals["publish_date"]),
        )
        .sort_values(["period_end", "publish_date"])
        .groupby("asset")["value"]
        .last()
    )
    return pd.Series({latest.astype(float).idxmax(): MAX_GROSS})


@dataclass
class FundamentalTilt:
    """Holds the asset with the best latest-known fundamental; records views."""

    name: str = "fundamental-tilt"
    seen: list[View] = field(default_factory=list)

    def target_weights(self, view: View) -> pd.Series:
        self.seen.append(view)
        return best_reported(view.fundamentals)
