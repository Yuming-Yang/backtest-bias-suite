"""T1: the probe names the day of a leak, the outcome check catches hidden ones."""

from dataclasses import replace

import pandas as pd

from btbias import ReferenceEngine, Scenario, Status, View
from btbias.strategies import Momentum, top_mover
from btbias.trap import run_trap
from btbias.traps import T1
from btbias.traps.lookahead import expected_schedule


class RelabelledFuture(ReferenceEngine):
    """Shows tomorrow's closes under today's dates: no row is dated after as_of."""

    name = "relabelled-future"

    def view(self, scenario: Scenario, t: pd.Timestamp, weights: pd.Series) -> View:
        v = super().view(scenario, t, weights)
        shifted = scenario.close.shift(-1).fillna(scenario.close).loc[:t]
        return replace(v, close=shifted)


def test_reference_engine_passes_t1() -> None:
    result = run_trap(ReferenceEngine(), T1)
    assert result.status is Status.PASS, result.detail


def test_t1_strategy_switches_assets_often() -> None:
    # If momentum always held one asset, a leak could not change its orders.
    scenario, _ = T1.build()
    picks = expected_schedule(scenario).idxmax(axis=1).iloc[1:]
    assert picks.nunique() == len(scenario.assets)
    assert (picks != picks.shift()).sum() > 20


def test_hidden_leak_is_caught_by_the_outcome_check_alone() -> None:
    result = run_trap(RelabelledFuture(), T1)
    assert result.status is Status.FAIL
    assert "from the future" not in result.detail
    assert "NAV on" in result.detail


def test_momentum_records_views_and_needs_two_rows() -> None:
    strategy = Momentum()
    one_row = pd.DataFrame({"A": [1.0], "B": [1.0]}, index=pd.to_datetime(["2024-01-01"]))
    view = View(as_of=one_row.index[0], open=one_row, close=one_row, universe=("A", "B"))
    assert strategy.target_weights(view).empty
    assert strategy.seen == [view]
    two_rows = pd.DataFrame({"A": [1.0, 1.1], "B": [1.0, 1.2]})
    assert top_mover(two_rows).to_dict() == {"B": 0.95}
