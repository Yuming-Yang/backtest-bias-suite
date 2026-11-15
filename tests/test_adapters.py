"""Adapter helpers agree with the reference engine."""

import pandas as pd
import pytest

from btbias import ReferenceEngine, Trap
from btbias.adapters import fills_from_money, view_at
from btbias.strategies import FundamentalTilt
from btbias.traps import ALL_TRAPS


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=[t.id for t in ALL_TRAPS])
def test_view_at_matches_the_reference_engine(trap: Trap) -> None:
    scenario, _ = trap.build()
    recorder = FundamentalTilt()  # any strategy that records views will do
    ReferenceEngine().run(scenario, recorder)
    for ref in recorder.seen:
        ours = view_at(scenario, ref.as_of)
        assert ours.universe == ref.universe
        pd.testing.assert_frame_equal(ours.close, ref.close)
        pd.testing.assert_frame_equal(ours.open, ref.open)
        pd.testing.assert_frame_equal(ours.fundamentals, ref.fundamentals)


def test_fills_from_money_prices_and_charges_each_fill() -> None:
    cal = pd.bdate_range("2024-01-01", periods=3)
    traded = pd.DataFrame({"A": [0.0, 500.0, -200.0], "B": [0.0, 0.0, 300.0]}, index=cal)
    prices = pd.DataFrame({"B": [5.0, 5.0, 6.0], "A": [10.0, 10.0, 8.0]}, index=cal)
    fills = fills_from_money(traded, prices, 0.01)
    assert fills["date"].tolist() == [cal[1], cal[2], cal[2]]
    assert fills["asset"].tolist() == ["A", "A", "B"]
    assert fills["quantity"].tolist() == [50.0, -25.0, 50.0]
    assert fills["price"].tolist() == [10.0, 8.0, 6.0]
    assert fills["cost"].tolist() == [5.0, 2.0, 3.0]
    assert fills_from_money(traded * 0, prices, 0.01).empty
