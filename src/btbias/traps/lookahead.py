"""T1: the engine shows the strategy prices from after the decision time.

Scenario: four assets on a random walk without overnight gaps or costs, and
a momentum strategy that holds yesterday's best performer.

Two checks:

1. Probe. No view may contain an open or close dated after its ``as_of``.
   This names the exact day of a leak.
2. Outcome. NAV matches the momentum strategy run on point-in-time data
   (``truth.no_cost_nav``). This catches leaks the probe cannot see, such as
   tomorrow's prices written under today's date. A one-day leak turns the
   strategy into a perfect forecaster, so the NAV gap is large.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import random_walk, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import Scenario
from btbias.strategies import Momentum, top_mover
from btbias.trap import Trap, nav_mismatch
from btbias.truth import no_cost_nav

ASSETS = ["AAA", "BBB", "CCC", "DDD"]
N_DAYS = 60
SEED = 101


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = random_walk(calendar, ASSETS, seed=SEED)
    return simple_market("T1 lookahead", open_, close), Momentum()


def expected_schedule(scenario: Scenario) -> pd.DataFrame:
    """The momentum strategy's targets when it sees only data up to each day."""
    rows = [
        top_mover(scenario.close.loc[:t]).reindex(scenario.assets, fill_value=0.0).to_numpy()
        for t in scenario.calendar
    ]
    return pd.DataFrame(np.vstack(rows), index=scenario.calendar, columns=list(scenario.assets))


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, Momentum):
        raise TypeError(f"T1 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    leaks = [
        (v.as_of, max(v.open.index.max(), v.close.index.max()))
        for v in strategy.seen
        if max(v.open.index.max(), v.close.index.max()) > v.as_of
    ]
    if leaks:
        as_of, latest = leaks[0]
        problems.append(
            f"{len(leaks)} view(s) show prices from the future, first at the "
            f"{as_of:%Y-%m-%d} close: prices up to {latest:%Y-%m-%d}"
        )
    expected = no_cost_nav(
        expected_schedule(scenario),
        scenario.open,
        scenario.close,
        scenario.convention,
        scenario.initial_cash,
    )
    mismatch = nav_mismatch(result.nav, expected)
    if mismatch:
        problems.append(mismatch)
    return problems


T1 = Trap(id="T1", title="Price lookahead", build=build, check=check)
