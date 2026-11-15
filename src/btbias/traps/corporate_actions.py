"""T6: splits and dividends are not applied.

Scenario: three companies whose value never changes, with raw prices that
drop on each ex-date: AAA splits 2:1, BBB splits 3:1 and pays a dividend,
CCC pays two dividends. No costs, no gaps in total-return terms, and a
strategy that moves to a new random allocation every day, so it trades on
every ex-date too.

Outcome check: a holder who receives the split shares and the dividend cash
is exactly as rich as before, so NAV must stay at the initial cash on every
day (``truth.flat_market_nav`` with no costs). An engine that ignores a
split books a crash; one that ignores a dividend loses the payout.
"""

from __future__ import annotations

import pandas as pd

from btbias.generator import flat_total_return_prices, random_weights, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import Scenario
from btbias.strategies import ScheduledWeights
from btbias.trap import Trap, nav_mismatch
from btbias.truth import flat_market_nav

LEVELS = {"AAA": 120.0, "BBB": 90.0, "CCC": 40.0}
N_DAYS = 40
SEED = 606


def corporate_actions(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset": ["AAA", "BBB", "BBB", "CCC", "CCC"],
            "ex_date": [calendar[10], calendar[20], calendar[30], calendar[15], calendar[35]],
            "kind": ["split", "split", "dividend", "dividend", "dividend"],
            "value": [2.0, 3.0, 0.75, 1.2, 1.2],
        }
    )


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    actions = corporate_actions(calendar)
    open_, close = flat_total_return_prices(calendar, LEVELS, actions)
    scenario = simple_market("T6 corporate actions", open_, close, corporate_actions=actions)
    return scenario, ScheduledWeights(random_weights(calendar, list(LEVELS), seed=SEED))


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, ScheduledWeights):
        raise TypeError(f"T6 expects the strategy it built, got {type(strategy).__name__}")
    # Flat in total-return terms and no costs: NAV never moves.
    expected = flat_market_nav(strategy.schedule, scenario.initial_cash, cost_rate=0.0)
    mismatch = nav_mismatch(result.nav, expected)
    return [mismatch] if mismatch else []


T6 = Trap(id="T6", title="Corporate actions unadjusted", build=build, check=check)
