import numpy as np
import pandas as pd
import pytest

from btbias.generator import (
    MAX_GROSS,
    delist,
    flat_prices,
    listed_throughout,
    random_walk,
    random_weights,
    simple_market,
    trading_days,
)

CAL = trading_days(40)
ASSETS = ["AAA", "BBB", "CCC"]


def test_trading_days_are_consecutive_business_days() -> None:
    cal = trading_days(10, start="2024-01-05")  # a Friday
    assert len(cal) == 10
    assert cal[0] == pd.Timestamp("2024-01-05")
    assert (cal.day_of_week < 5).all()
    with pytest.raises(ValueError, match="n_days"):
        trading_days(0)


def test_flat_prices_never_move() -> None:
    open_, close = flat_prices(CAL, {"AAA": 10.0, "BBB": 25.0})
    assert (close["AAA"] == 10.0).all() and (close["BBB"] == 25.0).all()
    assert open_.equals(close)
    assert open_ is not close


def test_random_walk_is_deterministic_per_seed() -> None:
    a = random_walk(CAL, ASSETS, seed=7)
    b = random_walk(CAL, ASSETS, seed=7)
    c = random_walk(CAL, ASSETS, seed=8)
    assert a[0].equals(b[0]) and a[1].equals(b[1])
    assert not a[1].equals(c[1])


def test_random_walk_without_gaps_opens_at_the_previous_close() -> None:
    open_, close = random_walk(CAL, ASSETS, seed=1)
    # Exactly equal, not just close: the isolation rule relies on it.
    assert (open_.iloc[1:].to_numpy() == close.iloc[:-1].to_numpy()).all()
    assert (open_.iloc[0] == 100.0).all()
    assert (close.to_numpy() > 0).all()


def test_random_walk_with_gaps_opens_away_from_the_previous_close() -> None:
    open_, close = random_walk(CAL, ASSETS, seed=1, gaps=True)
    gap = open_.iloc[1:].to_numpy() / close.iloc[:-1].to_numpy() - 1
    assert (np.abs(gap) > 1e-6).all()
    assert (open_.iloc[0] == 100.0).all()


def test_random_weights_are_long_only_with_fixed_gross_and_change_daily() -> None:
    w = random_weights(CAL, ASSETS, seed=3)
    assert (w.to_numpy() >= 0).all()
    np.testing.assert_allclose(w.sum(axis=1), MAX_GROSS, rtol=1e-12)
    assert (w.diff().abs().sum(axis=1).iloc[1:] > 0).all()
    with pytest.raises(ValueError, match="gross"):
        random_weights(CAL, ASSETS, seed=3, gross=1.0)


def test_generated_pieces_make_a_valid_scenario() -> None:
    open_, close = random_walk(CAL, ASSETS, seed=2, gaps=True)
    s = simple_market("walk", open_, close)
    assert s.assets == tuple(ASSETS)
    assert s.listings["delist_date"].isna().all()


def test_drift_moves_only_the_named_asset() -> None:
    base = random_walk(CAL, ASSETS, seed=4)[1]
    tilted = random_walk(CAL, ASSETS, seed=4, drift={"BBB": -0.01})[1]
    assert tilted["AAA"].equals(base["AAA"]) and tilted["CCC"].equals(base["CCC"])
    np.testing.assert_allclose(
        np.log(tilted["BBB"] / base["BBB"]), -0.01 * np.arange(1, len(CAL) + 1), atol=1e-12
    )


def test_delist_removes_later_prices_and_records_the_return() -> None:
    open_, close = random_walk(CAL, ASSETS, seed=5)
    listings = listed_throughout(CAL, ASSETS)
    delist(open_, close, listings, "CCC", CAL[9], -0.3)
    s = simple_market("delisting", open_, close, listings=listings)
    assert close["CCC"].iloc[10:].isna().all() and close["CCC"].iloc[:10].notna().all()
    assert s.listings.loc["CCC", "delist_date"] == CAL[9]
    assert s.listings.loc["CCC", "delisting_return"] == -0.3
