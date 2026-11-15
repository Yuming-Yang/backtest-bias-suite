"""Deliberately broken engines, one bug each.

Every mutant is the reference engine with exactly one method overridden.
The mutation matrix (tests/test_mutation_matrix.py) checks that each one
fails its own trap and passes every other trap: the first shows the trap
catches the bug, the second shows it does not fire on unrelated ones.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from btbias.generator import ex_date_price
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
        price = scenario.close.iloc[decision_day].copy()
        # The decision close is quoted in shares from before any split or
        # dividend on the fill day; restate it in today's shares, as an
        # engine that really filled at that close would have been.
        ca = scenario.corporate_actions
        if not ca.empty:
            today = ca[pd.to_datetime(ca["ex_date"]) == t]
            for asset, g in today.groupby("asset"):
                v = dict(zip(g["kind"], g["value"].astype(float), strict=True))
                price[asset] = ex_date_price(
                    price[asset], v.get("dividend", 0.0), v.get("split", 1.0)
                )
        # Right fill day, wrong price: an asset that does not trade on the
        # fill day still cannot fill, so this stays one bug and not two.
        return price.where(scenario.open.loc[t].notna())


class PeriodEndEngine(ReferenceEngine):
    """T3: treats fundamentals as known from the end of their period.

    Reports show up before they are published, and restatements, which share
    the original's period end, show up at the same time as the original.
    """

    name = "mutant-T3-period-end"

    def view(self, scenario: Scenario, t: pd.Timestamp, weights: pd.Series) -> View:
        v = super().view(scenario, t, weights)
        fu = scenario.fundamentals
        if fu.empty:
            return v
        return replace(v, fundamentals=fu[pd.to_datetime(fu["period_end"]) <= t])


class SurvivorsOnlyEngine(ReferenceEngine):
    """T4: offers only assets still listed at the end of the data.

    This is what a backtest sees when its data comes from a snapshot of
    today's tickers: every company that later delisted is simply absent.
    """

    name = "mutant-T4-survivors-only"

    def universe(self, scenario: Scenario, t: pd.Timestamp) -> tuple[str, ...]:
        dead = set(scenario.listings.index[scenario.listings["delist_date"].notna()])
        return tuple(a for a in super().universe(scenario, t) if a not in dead)


class ZeroCostEngine(ReferenceEngine):
    """T5: ignores the scenario's cost model and trades for free."""

    name = "mutant-T5-zero-cost"

    def transaction_cost(self, scenario: Scenario, notional: float) -> float:
        return 0.0


class TodaysConstituentsEngine(ReferenceEngine):
    """T7: uses the index members on the last day for every day."""

    name = "mutant-T7-todays-constituents"

    def universe(self, scenario: Scenario, t: pd.Timestamp) -> tuple[str, ...]:
        if scenario.membership.empty:
            return super().universe(scenario, t)
        return super().universe(scenario, scenario.calendar[-1])


MUTANTS: dict[str, type[ReferenceEngine]] = {
    "T1": PeekingEngine,
    "T2": SameCloseEngine,
    "T3": PeriodEndEngine,
    "T4": SurvivorsOnlyEngine,
    "T5": ZeroCostEngine,
    "T7": TodaysConstituentsEngine,
}
"""Trap id -> the mutant that trap must catch."""
