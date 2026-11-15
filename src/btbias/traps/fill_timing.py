"""T2: orders fill at the same close the signal was computed on.

Scenario: three assets on a random walk with overnight gaps, no costs, and a
strategy that follows a fixed random schedule and ignores prices. The
schedule cannot react to a leak, so the only way NAV can differ from the
ground truth is through when and at what price orders fill.

Two checks:

1. Every trade's price is the price the declared convention says: the open
   of the trade date under ``NEXT_OPEN``, the close under ``NEXT_CLOSE``.
2. NAV matches ``truth.no_cost_nav`` for the declared convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import random_walk, random_weights, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import ExecutionConvention, Scenario
from btbias.strategies import ScheduledWeights
from btbias.trap import NAV_RTOL, Trap, nav_mismatch
from btbias.truth import no_cost_nav

ASSETS = ["AAA", "BBB", "CCC"]
N_DAYS = 40
SEED = 202


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = random_walk(calendar, ASSETS, seed=SEED, gaps=True)
    schedule = random_weights(calendar, ASSETS, seed=SEED + 1)
    return simple_market("T2 fill timing", open_, close), ScheduledWeights(schedule)


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, ScheduledWeights):
        raise TypeError(f"T2 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    next_open = scenario.convention is ExecutionConvention.NEXT_OPEN
    fill_prices = scenario.open if next_open else scenario.close
    tr = result.trades
    if not tr.empty:
        dates = pd.to_datetime(tr["date"])
        rows = fill_prices.index.get_indexer(dates)
        cols = fill_prices.columns.get_indexer(tr["asset"])
        expected = fill_prices.to_numpy(dtype=float)[rows, cols]
        reported = tr["price"].to_numpy(dtype=float)
        bad = ~np.isclose(reported, expected, rtol=NAV_RTOL, atol=0.0)
        if bad.any():
            i = int(np.argmax(bad))
            where = "open" if next_open else "close"
            problems.append(
                f"{int(bad.sum())} fill(s) at the wrong price, first {tr['asset'].iloc[i]} on "
                f"{dates.iloc[i]:%Y-%m-%d} at {reported[i]:.6f}, expected the {where} "
                f"{expected[i]:.6f}"
            )
    truth = no_cost_nav(
        strategy.schedule, scenario.open, scenario.close, scenario.convention, scenario.initial_cash
    )
    mismatch = nav_mismatch(result.nav, truth)
    if mismatch:
        problems.append(mismatch)
    return problems


T2 = Trap(id="T2", title="Signal/execution misalignment", build=build, check=check)
