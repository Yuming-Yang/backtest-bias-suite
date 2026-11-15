"""T5 end to end: the reference engine passes, broken engines are caught."""

from collections.abc import Callable

import numpy as np
import pandas as pd

from btbias import (
    BacktestResult,
    ReferenceEngine,
    Scenario,
    Status,
    Strategy,
    run_suite,
)
from btbias.trap import run_trap
from btbias.traps import T5


class Wrapped:
    """The reference engine with its result edited after the run."""

    def __init__(self, edit: Callable[[BacktestResult], BacktestResult]) -> None:
        self.name = "wrapped"
        self.edit = edit

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
        return self.edit(ReferenceEngine().run(scenario, strategy))


def test_reference_engine_passes_t5() -> None:
    result = run_trap(ReferenceEngine(), T5)
    assert result.status is Status.PASS, result.detail


def test_t5_scenario_trades_every_day_and_costs_add_up() -> None:
    scenario, strategy = T5.build()
    result = ReferenceEngine().run(scenario, strategy)
    fill_days = pd.to_datetime(result.trades["date"]).unique()
    assert len(fill_days) == len(scenario.calendar) - 1
    # On flat prices the NAV lost equals the costs charged, to the cent.
    lost = scenario.initial_cash - result.nav.iloc[-1]
    np.testing.assert_allclose(lost, result.trades["cost"].sum(), rtol=1e-9)
    # And the effect is large enough to dwarf the tolerance.
    assert lost / scenario.initial_cash > 1e-3


def test_costs_reported_but_not_deducted_fail_on_nav() -> None:
    def keep_nav_flat(r: BacktestResult) -> BacktestResult:
        return BacktestResult(nav=r.nav * 0 + r.nav.iloc[0], trades=r.trades, weights=r.weights)

    result = run_trap(Wrapped(keep_nav_flat), T5)
    assert result.status is Status.FAIL
    assert "NAV on 2024-01-02" in result.detail
    assert "wrong cost" not in result.detail


def test_costs_deducted_but_reported_as_zero_fail_on_trades() -> None:
    def zero_reported(r: BacktestResult) -> BacktestResult:
        return BacktestResult(nav=r.nav, trades=r.trades.assign(cost=0.0), weights=r.weights)

    result = run_trap(Wrapped(zero_reported), T5)
    assert result.status is Status.FAIL
    assert "report the wrong cost" in result.detail
    assert "NAV" not in result.detail


def test_engine_errors_and_malformed_results_are_reported_not_raised() -> None:
    def boom(r: BacktestResult) -> BacktestResult:
        raise RuntimeError("engine exploded")

    def short_nav(r: BacktestResult) -> BacktestResult:
        return BacktestResult(nav=r.nav.iloc[:-1], trades=r.trades, weights=r.weights)

    crashed = run_trap(Wrapped(boom), T5)
    assert crashed.status is Status.ERROR
    assert crashed.detail == "RuntimeError: engine exploded"
    assert run_trap(Wrapped(short_nav), T5).status is Status.ERROR


def test_run_suite_reports_every_trap() -> None:
    report = run_suite(ReferenceEngine())
    assert report.adapter == "reference"
    assert report.passed and report.failed_ids == ()
    assert [r.trap_id for r in report.results] == ["T5"]
