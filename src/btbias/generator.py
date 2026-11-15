"""Seeded building blocks for synthetic scenarios.

Each trap builds its scenario from these pieces. Everything that draws random
numbers takes an explicit ``seed``, so the same call always returns the same
market. Ground truth is always recomputed from the generated data, never
hard-coded, so tests do not depend on numpy's random stream staying the same
across versions.

Price paths come in two kinds:

- ``gaps=False`` (the default): the open of every day after the first equals
  the previous close. Filling at the decision close and filling at the next
  open then give the same result, which keeps fill-timing bugs out of every
  scenario except T2's (see "Isolation between traps" in SPEC.md).
- ``gaps=True``: opens move away from the previous close, for T2.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from btbias.scenario import LISTING_COLUMNS, Scenario

MAX_GROSS = 0.95
"""Suite strategies never invest more than this, so cash stays positive after costs."""


def trading_days(n_days: int, start: str = "2024-01-01") -> pd.DatetimeIndex:
    """``n_days`` consecutive business days starting on or after ``start``."""
    if n_days < 1:
        raise ValueError(f"n_days must be >= 1, got {n_days}")
    return pd.bdate_range(start, periods=n_days)


def flat_prices(
    calendar: pd.DatetimeIndex, levels: Mapping[str, float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open and close prices that never move: each asset trades at its level every day."""
    close = pd.DataFrame(
        {asset: np.full(len(calendar), float(level)) for asset, level in levels.items()},
        index=calendar,
    )
    return close.copy(), close


def random_walk(
    calendar: pd.DatetimeIndex,
    assets: Sequence[str],
    *,
    seed: int,
    start_price: float = 100.0,
    daily_vol: float = 0.02,
    gaps: bool = False,
    overnight_vol: float = 0.01,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open and close prices from a geometric random walk.

    Each day's open-to-close log return is normal with standard deviation
    ``daily_vol``. With ``gaps=True`` the close-to-next-open log return is
    normal with ``overnight_vol``; otherwise it is zero and every open after
    the first equals the previous close.
    """
    rng = np.random.default_rng(seed)
    shape = (len(calendar), len(assets))
    intraday = rng.normal(0.0, daily_vol, shape)
    overnight = rng.normal(0.0, overnight_vol, shape) if gaps else np.zeros(shape)
    overnight[0] = 0.0  # the first open is the start price
    close = start_price * np.cumprod(np.exp(overnight + intraday), axis=0)
    open_ = np.empty(shape)
    open_[0] = start_price
    # Multiplying by exp(0.0) == 1.0 leaves the previous close bit-for-bit.
    open_[1:] = close[:-1] * np.exp(overnight[1:])

    def frame(values: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(values, index=calendar, columns=list(assets))

    return frame(open_), frame(close)


def random_weights(
    calendar: pd.DatetimeIndex,
    assets: Sequence[str],
    *,
    seed: int,
    gross: float = MAX_GROSS,
) -> pd.DataFrame:
    """A long-only weight schedule that changes every day.

    Each row is a random split of ``gross`` across the assets, so every row
    sums to exactly ``gross`` and consecutive rows differ, which makes the
    strategy trade every day.
    """
    if not 0 < gross <= MAX_GROSS:
        raise ValueError(f"gross must be in (0, {MAX_GROSS}], got {gross}")
    rng = np.random.default_rng(seed)
    split = rng.dirichlet(np.ones(len(assets)), size=len(calendar))
    return pd.DataFrame(split * gross, index=calendar, columns=list(assets))


def listed_throughout(calendar: pd.DatetimeIndex, assets: Sequence[str]) -> pd.DataFrame:
    """A listings table where every asset trades for the whole calendar."""
    return pd.DataFrame(
        {
            "list_date": [calendar[0]] * len(assets),
            "delist_date": [pd.NaT] * len(assets),
            "delisting_return": [0.0] * len(assets),
        },
        index=list(assets),
    )[list(LISTING_COLUMNS)]


def simple_market(
    name: str, open_: pd.DataFrame, close: pd.DataFrame, **kwargs: object
) -> Scenario:
    """A scenario where every asset is listed throughout and nothing else happens.

    Extra keyword arguments (``cost_model``, ``convention`` and so on) are
    passed to ``Scenario``.
    """
    return Scenario(
        name=name,
        calendar=close.index,
        open=open_,
        close=close,
        listings=listed_throughout(close.index, list(close.columns)),
        **kwargs,  # type: ignore[arg-type]
    )
