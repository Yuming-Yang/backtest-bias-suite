"""T2: fills must happen at the price the declared convention names."""

from dataclasses import replace

import numpy as np
import pandas as pd

from btbias import (
    BacktestResult,
    ExecutionConvention,
    ReferenceEngine,
    Scenario,
    Status,
    Strategy,
)
from btbias.mutants import SameCloseEngine
from btbias.trap import run_trap
from btbias.traps import T2

from builders import Fixed, make_scenario


def test_reference_engine_passes_t2() -> None:
    result = run_trap(ReferenceEngine(), T2)
    assert result.status is Status.PASS, result.detail


def test_t2_scenario_gaps_overnight_and_trades_every_day() -> None:
    scenario, strategy = T2.build()
    gap = scenario.open.iloc[1:].to_numpy() / scenario.close.iloc[:-1].to_numpy() - 1
    assert (np.abs(gap) > 1e-6).all()
    trades = ReferenceEngine().run(scenario, strategy).trades
    assert trades["date"].nunique() == len(scenario.calendar) - 1


def test_t2_checks_the_declared_convention_not_a_fixed_one() -> None:
    # Under NEXT_CLOSE the reference engine fills at the close and passes,
    # and the same-close mutant still fails.
    def next_close() -> tuple[Scenario, Strategy]:
        scenario, strategy = T2.build()
        return replace(scenario, convention=ExecutionConvention.NEXT_CLOSE), strategy

    t2_close = replace(T2, build=next_close)
    assert run_trap(ReferenceEngine(), t2_close).status is Status.PASS
    assert run_trap(SameCloseEngine(), t2_close).status is Status.FAIL


def test_right_nav_with_wrong_reported_prices_still_fails() -> None:
    class MisreportedPrices(ReferenceEngine):
        def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
            r = super().run(scenario, strategy)
            return replace(r, trades=r.trades.assign(price=r.trades["price"] * 1.01))

    result = run_trap(MisreportedPrices(), T2)
    assert result.status is Status.FAIL
    assert "wrong price" in result.detail and "NAV" not in result.detail


def test_same_close_mutant_does_not_fill_assets_that_no_longer_trade() -> None:
    # BBB delists on day 2. An order decided that evening must be cancelled
    # by the mutant too, or it would carry a second bug into T4.
    scenario = make_scenario()
    targets = {k: {"AAA": 0.4, "BBB": 0.4} for k in range(5)}
    trades = SameCloseEngine().run(scenario, Fixed(targets)).trades
    bbb_days = pd.to_datetime(trades.loc[trades["asset"] == "BBB", "date"])
    assert (bbb_days <= scenario.calendar[2]).all()
