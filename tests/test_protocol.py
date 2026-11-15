"""The adapter contract, exercised with a do-nothing engine."""

from dataclasses import dataclass, field

import pandas as pd
import pytest

from btbias import Adapter, BacktestResult, ResultError, Scenario, Strategy, View

from builders import make_scenario


@dataclass
class RecordingStrategy:
    """Stays in cash and keeps every view it is shown."""

    name: str = "recorder"
    seen: list[View] = field(default_factory=list)

    def target_weights(self, view: View) -> pd.Series:
        self.seen.append(view)
        return pd.Series(dtype=float)


class CashOnlyAdapter:
    """A minimal engine that builds correct views and never trades."""

    name = "cash-only"

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
        for t in scenario.calendar:
            listed = scenario.close.loc[t].dropna().index
            strategy.target_weights(
                View(
                    as_of=t,
                    open=scenario.open.loc[:t],
                    close=scenario.close.loc[:t],
                    universe=tuple(listed),
                )
            )
        cal = scenario.calendar
        return BacktestResult(
            nav=pd.Series(scenario.initial_cash, index=cal),
            trades=pd.DataFrame(columns=["date", "asset", "quantity", "price", "cost"]),
            weights=pd.DataFrame(0.0, index=cal, columns=list(scenario.assets)),
        )


def test_example_classes_satisfy_the_protocols() -> None:
    assert isinstance(RecordingStrategy(), Strategy)
    assert isinstance(CashOnlyAdapter(), Adapter)


def test_engine_calls_strategy_once_per_day_with_point_in_time_views() -> None:
    scenario = make_scenario()
    strategy = RecordingStrategy()
    result = CashOnlyAdapter().run(scenario, strategy)

    result.check_against(scenario)
    assert [v.as_of for v in strategy.seen] == list(scenario.calendar)
    for view in strategy.seen:
        assert view.close.index.max() == view.as_of
    # BBB delists on day 3, so it leaves the universe afterwards.
    assert strategy.seen[2].universe == ("AAA", "BBB")
    assert strategy.seen[3].universe == ("AAA",)


def _good_result(scenario: Scenario) -> BacktestResult:
    return CashOnlyAdapter().run(scenario, RecordingStrategy())


def _trade(**overrides: object) -> pd.DataFrame:
    row = {
        "date": pd.Timestamp("2024-01-02"),
        "asset": "AAA",
        "quantity": 10.0,
        "price": 11.0,
        "cost": 0.1,
    }
    row.update(overrides)
    return pd.DataFrame([row])


BAD_RESULTS = {
    "nav off calendar": (lambda r: {"nav": r.nav.iloc[:-1]}, "nav must be indexed"),
    "nav not finite": (lambda r: {"nav": r.nav.where(r.nav.index != r.nav.index[2])}, "finite"),
    "weights off calendar": (lambda r: {"weights": r.weights.iloc[1:]}, "weights must be"),
    "weights unknown asset": (lambda r: {"weights": r.weights.assign(ZZZ=0.0)}, "unknown assets"),
    "trades missing column": (lambda r: {"trades": _trade().drop(columns="cost")}, "missing"),
    "trade on holiday": (
        lambda r: {"trades": _trade(date=pd.Timestamp("2024-01-06"))},
        "trading day",
    ),
    "trade unknown asset": (lambda r: {"trades": _trade(asset="ZZZ")}, "unknown assets"),
    "non-positive fill price": (lambda r: {"trades": _trade(price=0.0)}, "fill prices"),
    "negative cost": (lambda r: {"trades": _trade(cost=-1.0)}, "costs"),
}


def test_a_well_formed_trade_passes() -> None:
    scenario = make_scenario()
    r = _good_result(scenario)
    BacktestResult(nav=r.nav, trades=_trade(), weights=r.weights).check_against(scenario)


@pytest.mark.parametrize("case", list(BAD_RESULTS), ids=list(BAD_RESULTS))
def test_malformed_results_are_rejected(case: str) -> None:
    scenario = make_scenario()
    good = _good_result(scenario)
    change, message = BAD_RESULTS[case]
    fields = {"nav": good.nav, "trades": good.trades, "weights": good.weights}
    fields.update(change(good))
    with pytest.raises(ResultError, match=message):
        BacktestResult(**fields).check_against(scenario)
