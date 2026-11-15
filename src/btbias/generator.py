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

from btbias.scenario import FUNDAMENTAL_COLUMNS, LISTING_COLUMNS, Scenario

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
    drift: Mapping[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open and close prices from a geometric random walk.

    Each day's open-to-close log return is normal with standard deviation
    ``daily_vol``. With ``gaps=True`` the close-to-next-open log return is
    normal with ``overnight_vol``; otherwise it is zero and every open after
    the first equals the previous close. ``drift`` adds a fixed daily log
    return to the named assets, to stage trends such as a stock that falls
    before it delists.
    """
    rng = np.random.default_rng(seed)
    shape = (len(calendar), len(assets))
    intraday = rng.normal(0.0, daily_vol, shape)
    for asset, mu in (drift or {}).items():
        intraday[:, list(assets).index(asset)] += mu
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


def random_fundamentals(
    calendar: pd.DatetimeIndex,
    assets: Sequence[str],
    *,
    seed: int,
    field: str = "eps",
    period_days: int = 20,
    publish_lag: tuple[int, int] = (5, 15),
    restate_share: float = 0.4,
    restate_lag: tuple[int, int] = (10, 25),
) -> pd.DataFrame:
    """Periodic reports with a publication lag, some restated later.

    A period ends every ``period_days`` trading days. Each asset publishes
    its value for that period a random number of trading days later (within
    ``publish_lag``). A random ``restate_share`` of reports gets a second row
    with the same period end, a later publish date (within ``restate_lag``
    of the original) and a different value. Rows that would be published
    after the last calendar day are left out. Values are standard normal.
    """
    rng = np.random.default_rng(seed)
    rows = []
    n = len(calendar)
    for end in range(0, n, period_days):
        for asset in assets:
            pub = end + int(rng.integers(publish_lag[0], publish_lag[1] + 1))
            value = float(rng.normal())
            restate = rng.random() < restate_share
            re_pub = pub + int(rng.integers(restate_lag[0], restate_lag[1] + 1))
            re_value = value + float(rng.normal())
            if pub >= n:
                continue
            rows.append((asset, field, calendar[end], calendar[pub], value))
            if restate and re_pub < n:
                rows.append((asset, field, calendar[end], calendar[re_pub], re_value))
    return pd.DataFrame(rows, columns=list(FUNDAMENTAL_COLUMNS))


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


def delist(
    open_: pd.DataFrame,
    close: pd.DataFrame,
    listings: pd.DataFrame,
    asset: str,
    last_day: pd.Timestamp,
    delisting_return: float,
) -> None:
    """Delist ``asset`` after the close of ``last_day``, in place.

    Prices after ``last_day`` are removed, and the listings row gets the
    delist date and the return from that close to the cash received.
    """
    after = close.index > last_day
    open_.loc[after, asset] = np.nan
    close.loc[after, asset] = np.nan
    listings.loc[asset, "delist_date"] = last_day
    listings.loc[asset, "delisting_return"] = delisting_return


def simple_market(
    name: str,
    open_: pd.DataFrame,
    close: pd.DataFrame,
    listings: pd.DataFrame | None = None,
    **kwargs: object,
) -> Scenario:
    """A scenario with no corporate actions, fundamentals or membership table.

    Without ``listings``, every asset is listed throughout. Extra keyword
    arguments (``cost_model``, ``convention`` and so on) go to ``Scenario``.
    """
    if listings is None:
        listings = listed_throughout(close.index, list(close.columns))
    return Scenario(
        name=name,
        calendar=close.index,
        open=open_,
        close=close,
        listings=listings,
        **kwargs,  # type: ignore[arg-type]
    )
