"""T5: the engine ignores the declared transaction cost model.

Scenario: three assets whose prices never move, a 10 bps proportional cost,
and a strategy that moves to a new random long-only allocation every day.
Without price moves, the only thing that can change NAV is trading cost, so
a correct engine loses exactly ``rate * traded notional`` at each fill and a
zero-cost engine keeps NAV flat.

Two checks:

1. NAV matches ``truth.flat_market_nav`` on every day.
2. Each reported trade's ``cost`` equals ``rate * |quantity * price|``. This
   catches an engine that deducts costs but reports them wrongly, or the
   other way round.
"""

from __future__ import annotations

import numpy as np

from btbias.generator import flat_prices, random_weights, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import CostModel, Scenario
from btbias.strategies import ScheduledWeights
from btbias.trap import NAV_RTOL, Trap, nav_mismatch
from btbias.truth import flat_market_nav

COST_RATE = 0.001
LEVELS = {"AAA": 10.0, "BBB": 25.0, "CCC": 40.0}
N_DAYS = 30
SEED = 5


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = flat_prices(calendar, LEVELS)
    scenario = simple_market("T5 costs", open_, close, cost_model=CostModel(rate=COST_RATE))
    schedule = random_weights(calendar, list(LEVELS), seed=SEED)
    return scenario, ScheduledWeights(schedule)


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, ScheduledWeights):
        raise TypeError(f"T5 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    expected = flat_market_nav(strategy.schedule, scenario.initial_cash, scenario.cost_model.rate)
    mismatch = nav_mismatch(result.nav, expected)
    if mismatch:
        problems.append(mismatch)

    tr = result.trades
    if not tr.empty:
        notional = (tr["quantity"].astype(float) * tr["price"].astype(float)).abs()
        expected_cost = scenario.cost_model.rate * notional
        reported = tr["cost"].astype(float)
        atol = NAV_RTOL * scenario.initial_cash * scenario.cost_model.rate
        bad = ~np.isclose(reported.to_numpy(), expected_cost.to_numpy(), rtol=NAV_RTOL, atol=atol)
        if bad.any():
            i = int(np.argmax(bad))
            row = tr.iloc[i]
            problems.append(
                f"{int(bad.sum())} trade(s) report the wrong cost, first {row['asset']} on "
                f"{row['date']:%Y-%m-%d}: {reported.iloc[i]:.6f}, expected "
                f"{expected_cost.iloc[i]:.6f}"
            )
    return problems


T5 = Trap(id="T5", title="Zero transaction costs", build=build, check=check)
