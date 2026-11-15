"""T6: holding through splits and dividends must leave an unchanged company unchanged."""

from dataclasses import replace

import pandas as pd

from btbias import ReferenceEngine, Scenario, Status
from btbias.trap import run_trap
from btbias.traps import T6


class IgnoresDividends(ReferenceEngine):
    """Applies splits but never pays dividends."""

    def corporate_actions(self, scenario: Scenario, t: pd.Timestamp, shares: pd.Series) -> float:
        ca = scenario.corporate_actions
        splits = ca[ca["kind"] == "split"]
        return super().corporate_actions(replace(scenario, corporate_actions=splits), t, shares)


def test_reference_engine_passes_t6() -> None:
    result = run_trap(ReferenceEngine(), T6)
    assert result.status is Status.PASS, result.detail


def test_t6_scenario_trades_on_every_ex_date() -> None:
    scenario, strategy = T6.build()
    trades = ReferenceEngine().run(scenario, strategy).trades
    ex_dates = set(pd.to_datetime(scenario.corporate_actions["ex_date"]))
    assert ex_dates <= set(pd.to_datetime(trades["date"]))


def test_ignoring_only_dividends_is_caught_on_the_first_dividend() -> None:
    result = run_trap(IgnoresDividends(), T6)
    assert result.status is Status.FAIL
    first_dividend = T6.build()[0].calendar[15]
    assert f"NAV on {first_dividend:%Y-%m-%d}" in result.detail
