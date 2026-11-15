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
from btbias.generator import flat_total_return_prices, simple_market, trading_days
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


def test_same_close_mutant_restates_the_decision_close_after_a_split() -> None:
    # Where opens equal the economic previous close, the mutant must match
    # the reference engine, ex-dates included, or it would fail T6 too.
    cal = trading_days(6)
    actions = pd.DataFrame(
        {
            "asset": ["A", "A", "B"],
            "ex_date": [cal[2], cal[4], cal[3]],
            "kind": ["split", "dividend", "split"],
            "value": [2.0, 1.5, 3.0],
        }
    )
    open_, close = flat_total_return_prices(cal, {"A": 100.0, "B": 70.0}, actions)
    scenario = simple_market("actions", open_, close, corporate_actions=actions)
    targets = {k: {"A": 0.3 + 0.05 * k, "B": 0.5 - 0.05 * k} for k in range(6)}
    ref = ReferenceEngine().run(scenario, Fixed(targets))
    mutant = SameCloseEngine().run(scenario, Fixed(targets))
    pd.testing.assert_series_equal(mutant.nav, ref.nav, rtol=0, atol=0)
    pd.testing.assert_frame_equal(mutant.trades, ref.trades)
