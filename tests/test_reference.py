"""The reference engine on markets small enough to check by hand."""

import numpy as np
import pandas as pd
import pytest

from btbias import BorrowModel, CostModel, ExecutionConvention, Scenario
from btbias.generator import (
    flat_total_return_prices,
    listed_throughout,
    random_walk,
    simple_market,
    trading_days,
)
from btbias.reference import ReferenceEngine

from builders import Fixed, make_scenario

CAL = trading_days(3)
CAL4 = trading_days(4)


def _market(convention: ExecutionConvention = ExecutionConvention.NEXT_OPEN) -> Scenario:
    open_ = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [20.0, 20.0, 18.0]}, index=CAL)
    close = pd.DataFrame({"A": [10.0, 12.0, 12.0], "B": [20.0, 18.0, 18.0]}, index=CAL)
    return simple_market(
        "hand", open_, close, cost_model=CostModel(rate=0.01), convention=convention
    )


TARGETS = {0: {"A": 0.5}, 1: {"A": 0.25, "B": 0.25}, 2: {"B": 0.9}}


def test_next_open_fills_match_a_hand_calculation() -> None:
    result = ReferenceEngine().run(_market(), Fixed(TARGETS))
    result.check_against(_market())

    # Day 1, open: NAV_fill = 1,000,000. Buy A worth 500,000 at 11, pay 1% cost.
    a = 500_000 / 11
    cash = 1_000_000 - 500_000 - 5_000
    nav1 = cash + a * 12
    # Day 2, open: value A at its open (12), B has no position. Size both from NAV_fill.
    nav_fill = cash + a * 12
    a_new, b_new = 0.25 * nav_fill / 12, 0.25 * nav_fill / 18
    sell_a, buy_b = (a_new - a) * 12, b_new * 18
    cash += -sell_a - buy_b - 0.01 * (abs(sell_a) + abs(buy_b))
    nav2 = cash + a_new * 12 + b_new * 18

    np.testing.assert_allclose(result.nav, [1_000_000, nav1, nav2], rtol=1e-12)
    trades = result.trades
    assert list(trades["asset"]) == ["A", "A", "B"]
    assert list(trades["date"]) == [CAL[1], CAL[2], CAL[2]]
    np.testing.assert_allclose(trades["price"], [11.0, 12.0, 18.0])
    np.testing.assert_allclose(trades["quantity"], [a, a_new - a, b_new], rtol=1e-12)
    np.testing.assert_allclose(trades["cost"], 0.01 * (trades["quantity"] * trades["price"]).abs())
    # The day-2 decision (B: 0.9) is made on the last day and never fills.
    np.testing.assert_allclose(
        result.weights.iloc[2], [a_new * 12 / nav2, b_new * 18 / nav2], rtol=1e-12
    )


def test_next_close_fills_at_the_close_of_the_next_day() -> None:
    result = ReferenceEngine().run(_market(ExecutionConvention.NEXT_CLOSE), Fixed({0: {"A": 0.5}}))
    a = 500_000 / 12
    first = result.trades.iloc[0]
    assert (first["date"], first["price"]) == (CAL[1], 12.0)
    np.testing.assert_allclose(first["quantity"], a)
    np.testing.assert_allclose(result.nav.iloc[1], 1_000_000 - 5_000, rtol=1e-12)


def test_a_strategy_that_holds_cash_never_trades() -> None:
    result = ReferenceEngine().run(_market(), Fixed({}))
    assert result.trades.empty
    assert (result.nav == 1_000_000).all()
    assert (result.weights == 0.0).all().all()


def test_views_show_nothing_dated_after_the_decision() -> None:
    open_, close = random_walk(trading_days(20), ["X", "Y"], seed=0, gaps=True)
    scenario = simple_market("walk", open_, close)
    strategy = Fixed({k: {"X": 0.4, "Y": 0.4} for k in range(20)})
    ReferenceEngine().run(scenario, strategy)
    assert [v.as_of for v in strategy.seen] == list(scenario.calendar)
    for v in strategy.seen:
        assert v.open.index.max() == v.as_of == v.close.index.max()
    # From day 2 on, the view's weights are what the engine held at that close.
    assert strategy.seen[0].weights.empty
    assert set(strategy.seen[5].weights.index) == {"X", "Y"}


def test_fundamentals_are_visible_from_their_publish_date() -> None:
    d = make_scenario().calendar
    scenario = make_scenario(
        fundamentals=pd.DataFrame(
            {
                "asset": ["AAA", "AAA"],
                "field": ["eps", "eps"],
                "period_end": [d[0], d[0]],
                "publish_date": [d[1], d[3]],  # a restatement on day 3
                "value": [1.0, 0.8],
            }
        ),
        listings=listed_throughout(d, ["AAA", "BBB"]),
        close=make_scenario().close.ffill(),
        open=make_scenario().open.ffill(),
    )
    strategy = Fixed({})
    ReferenceEngine().run(scenario, strategy)
    visible = [v.fundamentals["value"].tolist() for v in strategy.seen]
    assert visible == [[], [1.0], [1.0], [1.0, 0.8], [1.0, 0.8]]


def test_universe_follows_membership_when_the_scenario_has_one() -> None:
    d = CAL
    scenario = _market()
    scenario = Scenario(
        **{f: getattr(scenario, f) for f in ("name", "calendar", "open", "close", "listings")},
        membership=pd.DataFrame(
            {"asset": ["A", "B"], "start": [d[0], d[1]], "end": [d[1], pd.NaT]}
        ),
    )
    strategy = Fixed({})
    ReferenceEngine().run(scenario, strategy)
    assert [v.universe for v in strategy.seen] == [("A",), ("B",), ("B",)]


def test_order_for_an_asset_without_a_price_on_the_fill_day_is_cancelled() -> None:
    open_ = pd.DataFrame({"A": [10.0, 10.0, 10.0], "C": [np.nan, np.nan, 5.0]}, index=CAL)
    listings = listed_throughout(CAL, ["A", "C"])
    listings.loc["C", "list_date"] = CAL[2]
    scenario = Scenario(
        name="late listing", calendar=CAL, open=open_, close=open_.copy(), listings=listings
    )
    result = ReferenceEngine().run(scenario, Fixed({0: {"A": 0.4, "C": 0.4}, 1: {"A": 0.4}}))
    # C has no price on day 1, so only A fills; the C order is not carried to day 2.
    assert result.trades["asset"].tolist() == ["A"]
    np.testing.assert_allclose(result.weights.iloc[2], [0.4, 0.0])


def test_engine_refuses_targets_it_cannot_trade() -> None:
    engine = ReferenceEngine()
    with pytest.raises(ValueError, match="unknown assets"):
        engine.run(_market(), Fixed({0: {"ZZZ": 0.5}}))


class IgnoresDelistingReturn(ReferenceEngine):
    def delisting_proceeds(
        self, scenario: Scenario, asset: str, shares: float, last_close: float
    ) -> float:
        return shares * last_close


def test_delisting_turns_the_position_into_cash_at_the_last_close() -> None:
    # BBB's last trading day is day 2 (close 18), with a -30% delisting return.
    scenario = make_scenario()
    hold_both = {k: {"AAA": 0.4, "BBB": 0.4} for k in range(5)}
    result = ReferenceEngine().run(scenario, Fixed(hold_both))
    no_dlret = IgnoresDelistingReturn().run(scenario, Fixed(hold_both))
    result.check_against(scenario)

    bbb = result.trades[result.trades["asset"] == "BBB"]
    shares_bbb = bbb["quantity"].sum()
    day2 = scenario.calendar[2]
    # Only the delisting return separates the two engines on the last day.
    np.testing.assert_allclose(result.nav[day2] - no_dlret.nav[day2], -0.3 * shares_bbb * 18.0)
    # From that close on BBB is cash: zero weight and no further fills.
    assert (result.weights["BBB"].iloc[2:] == 0.0).all()
    assert (pd.to_datetime(bbb["date"]) <= day2).all()


def test_splits_and_dividends_leave_an_unchanged_company_unchanged() -> None:
    cal = trading_days(5)
    actions = pd.DataFrame(
        {
            "asset": ["A", "B"],
            "ex_date": [cal[2], cal[3]],
            "kind": ["split", "dividend"],
            "value": [2.0, 1.0],
        }
    )
    open_, close = flat_total_return_prices(cal, {"A": 100.0, "B": 50.0}, actions)
    assert close["A"].tolist() == [100.0, 100.0, 50.0, 50.0, 50.0]
    assert close["B"].tolist() == [50.0, 50.0, 50.0, 49.0, 49.0]
    scenario = simple_market("actions", open_, close, corporate_actions=actions)
    result = ReferenceEngine().run(scenario, Fixed({k: {"A": 0.4, "B": 0.4} for k in range(5)}))

    np.testing.assert_allclose(result.nav, 1_000_000.0, rtol=1e-12)
    # The split needs no trade. The dividend moves cash out of B (weight
    # 0.4 -> 0.392), so on its ex-date the engine buys B back up, and nothing else.
    trades = result.trades
    assert set(trades["date"]) == {cal[1], cal[3]}
    assert trades.loc[trades["date"] == cal[3], "asset"].tolist() == ["B"]
    np.testing.assert_allclose(result.weights.iloc[1:].to_numpy(), 0.4, rtol=1e-12)


def test_ignoring_a_split_looks_like_a_crash() -> None:
    class IgnoresActions(ReferenceEngine):
        def corporate_actions(
            self, scenario: Scenario, t: pd.Timestamp, shares: pd.Series
        ) -> float:
            return 0.0

    cal = trading_days(4)
    actions = pd.DataFrame({"asset": ["A"], "ex_date": [cal[2]], "kind": ["split"], "value": [2.0]})
    open_, close = flat_total_return_prices(cal, {"A": 100.0}, actions)
    scenario = simple_market("split", open_, close, corporate_actions=actions)
    nav = IgnoresActions().run(scenario, Fixed({0: {"A": 0.5}, 1: {"A": 0.5}})).nav
    # Half the money sat in A, which "fell" 50% on the ex-date.
    assert nav.iloc[2] == pytest.approx(750_000.0)


def _flat_two_assets(borrow: BorrowModel) -> Scenario:
    cal = trading_days(4)
    open_ = pd.DataFrame({"A": [10.0] * 4, "B": [20.0] * 4}, index=cal)
    return simple_market("flat", open_, open_.copy(), borrow=borrow)


def test_a_short_pays_the_borrow_fee_on_its_value_at_each_close() -> None:
    scenario = _flat_two_assets(BorrowModel(daily_rate=0.001))
    long_short = {k: {"A": 0.5, "B": -0.3} for k in range(4)}
    result = ReferenceEngine().run(scenario, Fixed(long_short))
    # Day 1: short 300,000 of B, pay 0.1% of it at the close.
    nav1 = 1_000_000 - 0.001 * 300_000
    # Day 2 and 3: the short is resized to 30% of the new NAV, then charged.
    nav2 = nav1 * (1 - 0.001 * 0.3)
    nav3 = nav2 * (1 - 0.001 * 0.3)
    np.testing.assert_allclose(result.nav, [1_000_000, nav1, nav2, nav3], rtol=1e-12)
    assert (result.weights["B"].iloc[1:] < 0).all()


def test_a_hard_to_borrow_asset_can_be_sold_to_zero_but_not_shorted() -> None:
    scenario = _flat_two_assets(BorrowModel(daily_rate=0.001, hard_to_borrow=frozenset({"B"})))
    targets = {0: {"A": 0.5, "B": 0.3}, 1: {"A": 0.5, "B": -0.3}, 2: {"A": 0.5, "B": -0.3}}
    result = ReferenceEngine().run(scenario, Fixed(targets))
    b = result.trades[result.trades["asset"] == "B"]
    # Bought on day 1, sold to exactly zero on day 2, nothing on day 3.
    assert b["date"].tolist() == [CAL4[1], CAL4[2]]
    np.testing.assert_allclose(b["quantity"].sum(), 0.0, atol=1e-9)
    assert (result.weights["B"] >= 0).all()
    # Never short, so never charged: NAV does not move on flat prices.
    np.testing.assert_allclose(result.nav, 1_000_000, rtol=1e-12)
