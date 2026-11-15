"""T8: shorting is free and unlimited.

Scenario: four assets whose prices never move, no trading costs, a borrow
rate of 4 bps a day (about 10% a year, the cost of a crowded short), and
DDD on the hard-to-borrow list. The strategy runs a fixed long-short book:
long AAA and BBB, short CCC and DDD.

Two checks:

1. NAV matches ``truth.flat_market_borrow_nav``: on flat prices the only
   thing that moves NAV is the fee on the CCC short, and the DDD short is
   never opened.
2. No hard-to-borrow asset is ever held short at a close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import flat_prices, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import BorrowModel, Scenario
from btbias.strategies import ScheduledWeights
from btbias.trap import Trap, nav_mismatch
from btbias.truth import flat_market_borrow_nav

LEVELS = {"AAA": 30.0, "BBB": 55.0, "CCC": 80.0, "DDD": 25.0}
BOOK = {"AAA": 0.45, "BBB": 0.2, "CCC": -0.35, "DDD": -0.25}
DAILY_RATE = 0.0004
N_DAYS = 40


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = flat_prices(calendar, LEVELS)
    borrow = BorrowModel(daily_rate=DAILY_RATE, hard_to_borrow=frozenset({"DDD"}))
    scenario = simple_market("T8 shorting", open_, close, borrow=borrow)
    schedule = pd.DataFrame([BOOK] * N_DAYS, index=calendar)
    return scenario, ScheduledWeights(schedule)


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, ScheduledWeights):
        raise TypeError(f"T8 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    hard = sorted(scenario.borrow.hard_to_borrow)
    held = result.weights.reindex(columns=hard, fill_value=0.0)
    shorted = held < -1e-12
    if shorted.to_numpy().any():
        day = held.index[int(np.argmax(shorted.any(axis=1).to_numpy()))]
        names = ", ".join(held.columns[shorted.loc[day].to_numpy()])
        problems.append(f"hard-to-borrow {names} held short, first at the {day:%Y-%m-%d} close")
    expected = flat_market_borrow_nav(
        strategy.schedule,
        scenario.initial_cash,
        scenario.borrow.daily_rate,
        scenario.borrow.hard_to_borrow,
    )
    mismatch = nav_mismatch(result.nav, expected)
    if mismatch:
        problems.append(mismatch)
    return problems


T8 = Trap(id="T8", title="Free and unlimited shorting", build=build, check=check)
