"""Ground-truth helpers, checked against numbers worked out by hand."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import btbias
from btbias.generator import trading_days
from btbias.scenario import ExecutionConvention
from btbias.truth import (
    flat_market_borrow_nav,
    flat_market_nav,
    listed_market_nav,
    no_cost_nav,
)


def test_flat_market_nav_matches_a_hand_calculation() -> None:
    cal = trading_days(4)
    schedule = pd.DataFrame({"A": [0.5, 0.0, 0.0, 0.9], "B": [0.0, 0.5, 0.5, 0.0]}, index=cal)
    nav = flat_market_nav(schedule, initial_cash=100.0, cost_rate=0.01)
    # Day 1: buy A worth 50, cost 0.5. Day 2: sell A (50), buy B worth
    # 0.5 * 99.5, cost 1% of both legs. Day 3: B is topped up from 49.75 to
    # half of the new NAV. The day-3 decision never fills.
    nav2 = 99.5 - 0.01 * (50 + 49.75)
    nav3 = nav2 - 0.01 * abs(0.5 * nav2 - 49.75)
    np.testing.assert_allclose(nav, [100.0, 99.5, nav2, nav3], rtol=1e-15)


def test_flat_market_nav_without_costs_stays_at_initial_cash() -> None:
    cal = trading_days(5)
    schedule = pd.DataFrame({"A": [0.3, 0.9, 0.1, 0.5, 0.2]}, index=cal)
    assert (flat_market_nav(schedule, 1_000.0, 0.0) == 1_000.0).all()


def _three_day_market() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cal = trading_days(3)
    open_ = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [20.0, 19.0, 22.0]}, index=cal)
    close = pd.DataFrame({"A": [10.0, 12.0, 15.0], "B": [20.0, 20.0, 21.0]}, index=cal)
    schedule = pd.DataFrame({"A": [0.5, 0.2, 0.9], "B": [0.0, 0.6, 0.0]}, index=cal)
    return schedule, open_, close


def test_no_cost_nav_next_open_matches_a_hand_calculation() -> None:
    schedule, open_, close = _three_day_market()
    nav = no_cost_nav(schedule, open_, close, ExecutionConvention.NEXT_OPEN, 100.0)
    # Day 1: buy 50 of A at the open (11); A closes at 12.
    nav1 = 50 + 50 * 12 / 11
    # Day 2: A moved 11 -> 12 between opens, so NAV at the open is
    # 50 + 50 * 12/11. Rebalance to 20% A and 60% B, then mark to the close.
    fill2 = 50 + 50 * 12 / 11
    nav2 = fill2 * (0.2 + 0.2 * 15 / 12 + 0.6 * 21 / 22)  # cash + A + B at the close
    np.testing.assert_allclose(nav, [100.0, nav1, nav2], rtol=1e-14)


def test_no_cost_nav_next_close_matches_a_hand_calculation() -> None:
    schedule, open_, close = _three_day_market()
    nav = no_cost_nav(schedule, open_, close, ExecutionConvention.NEXT_CLOSE, 100.0)
    # Day 1: buy 50 of A at the close (12), so NAV is still 100.
    # Day 2: A goes 12 -> 15 with 50% held, then rebalance at that close.
    np.testing.assert_allclose(nav, [100.0, 100.0, 100 * (1 + 0.5 * (15 / 12 - 1))], rtol=1e-14)


def _btbias_imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return {n for n in names if n.startswith("btbias")}


def test_ground_truth_and_traps_do_not_import_the_reference_engine() -> None:
    package = Path(btbias.__file__).parent
    graded = [package / "truth.py", *sorted((package / "traps").glob("*.py"))]
    for path in graded:
        forbidden = _btbias_imports(path) & {"btbias.reference", "btbias.mutants", "btbias"}
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"


def test_listed_market_nav_pays_the_delisting_return_and_holds_cash_after() -> None:
    cal = trading_days(3)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.1], "B": [20.0, 16.0, np.nan]}, index=cal)
    open_ = close.shift(1).where(close.notna())
    open_.iloc[0] = close.iloc[0]
    listings = pd.DataFrame(
        {"list_date": [cal[0]] * 2, "delist_date": [pd.NaT, cal[1]], "delisting_return": [0, -0.5]},
        index=["A", "B"],
    )
    schedule = pd.DataFrame({"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5]}, index=cal)
    nav = listed_market_nav(schedule, open_, close, listings, 100.0)
    # Day 1: A +10%, B -20% and then -50% on delisting.
    nav1 = 100 * (1 + 0.5 * 0.1 + 0.5 * (0.8 * 0.5 - 1))
    # Day 2: the B order cannot fill, so only half is invested; A +10%.
    nav2 = nav1 * (1 + 0.5 * 0.1)
    np.testing.assert_allclose(nav, [100.0, nav1, nav2], rtol=1e-14)


def test_listed_market_nav_refuses_markets_it_cannot_price() -> None:
    cal = trading_days(3)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=cal)
    listings = pd.DataFrame(
        {"list_date": [cal[0]], "delist_date": [pd.NaT], "delisting_return": [0.0]}, index=["A"]
    )
    schedule = pd.DataFrame({"A": [0.5, 0.5, 0.5]}, index=cal)
    with pytest.raises(ValueError, match="previous close"):
        listed_market_nav(schedule, close * 1.01, close, listings, 100.0)
    halted = close.copy()
    halted.iloc[1] = np.nan
    with pytest.raises(ValueError, match="restarts"):
        listed_market_nav(schedule, halted.shift(1), halted, listings, 100.0)


def test_flat_market_borrow_nav_charges_shorts_and_blocks_hard_to_borrow() -> None:
    cal = trading_days(3)
    schedule = pd.DataFrame({"A": [0.5] * 3, "B": [-0.2] * 3, "C": [-0.3] * 3}, index=cal)
    nav = flat_market_borrow_nav(schedule, 100.0, 0.01, frozenset({"C"}))
    # Only B is shorted (C is hard to borrow); 1% of the B short each day.
    nav1 = 100.0 - 0.01 * 20.0
    nav2 = nav1 - 0.01 * 0.2 * nav1
    np.testing.assert_allclose(nav, [100.0, nav1, nav2], rtol=1e-14)
