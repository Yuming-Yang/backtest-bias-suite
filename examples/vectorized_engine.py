"""A small vectorized backtest engine, standing in for "your engine".

It works the way research code usually does: it takes the whole weight
matrix up front (one row per decision day) instead of calling a strategy
each day, and it tracks money per asset rather than shares.

Prices are handled with numpy across all assets at once. One loop over days
remains, because costs make it unavoidable: the money traded at each open is
the gap between the new target and the old holdings after they drifted
overnight, and the target depends on NAV, which depends on yesterday's costs.
The textbook shortcut, cost = rate * |w_t - w_{t-1}| * NAV, skips the drift
and lands a few parts per million away from the exact answer.

Fills happen at the next open. Missing prices mean the asset does not trade
that day; an asset whose prices stop before the last day has delisted, and
its delisting return is paid at its last close. Assets may not halt and
restart.
"""

from __future__ import annotations

from collections.abc import Collection

import numpy as np
import pandas as pd


def backtest(
    weights: pd.DataFrame,
    open_: pd.DataFrame,
    close: pd.DataFrame,
    cost_rate: float,
    initial_cash: float,
    *,
    splits: pd.DataFrame | None = None,
    dividends: pd.DataFrame | None = None,
    delisting_returns: pd.Series | None = None,
    borrow_rate: float = 0.0,
    no_short: Collection[str] = (),
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """Run a weight schedule.

    ``weights.loc[t]`` is the target decided at the close of ``t`` and filled
    at the open of the next day. ``splits`` (new shares per old share) and
    ``dividends`` (cash per share) are date-by-asset tables of ex-date
    events. Shorts pay ``borrow_rate`` a day on their value at the close, and
    assets in ``no_short`` are never sold below zero.

    Returns NAV at each close, the money traded in each asset at each open
    (buys > 0), and the weights held at each close.
    """
    idx, cols = close.index, close.columns

    def table(frame: pd.DataFrame | None, fill: float) -> np.ndarray:
        if frame is None:
            return np.full(close.shape, fill)
        return frame.reindex(index=idx, columns=cols).fillna(fill).to_numpy(dtype=float)

    o, c = open_.to_numpy(dtype=float), close.to_numpy(dtype=float)
    w, split, div = table(weights, 0.0), table(splits, 1.0), table(dividends, 0.0)
    dlret = np.zeros(len(cols))
    if delisting_returns is not None:
        dlret = delisting_returns.reindex(cols).fillna(0.0).to_numpy(dtype=float)
    traded_any = ~np.isnan(c)
    last_day = len(idx) - 1 - np.argmax(traded_any[::-1], axis=0)
    delists = traded_any.any(axis=0) & (last_day < len(idx) - 1)
    hard = cols.isin(list(no_short))

    value = np.zeros(len(cols))  # money held in each asset, at the last price
    cash = float(initial_cash)
    nav = np.empty(len(idx))
    traded = np.zeros(close.shape)
    held = np.zeros(close.shape)
    with np.errstate(invalid="ignore"):
        for t in range(len(idx)):
            if t > 0:
                live = (value != 0) & ~np.isnan(o[t])
                shares = np.where(live, value / c[t - 1], 0.0)
                cash += float(np.sum(shares * div[t]))  # dividends, on pre-split shares
                value = np.where(live, shares * split[t] * o[t], value)  # overnight drift
                target = w[t - 1] * (cash + value.sum())
                target = np.where(np.isnan(o[t]), value, target)  # no price: cancelled
                target = np.where(hard, np.maximum(target, np.minimum(value, 0.0)), target)
                traded[t] = target - value
                cash -= traded[t].sum() + cost_rate * np.abs(traded[t]).sum()
                value = target
            value = np.where(value != 0, value * c[t] / o[t], 0.0)  # open to close
            ending = delists & (last_day == t)
            cash += float(np.sum(np.where(ending, value * (1 + dlret), 0.0)))
            value = np.where(ending, 0.0, value)
            cash -= borrow_rate * float(-value[value < 0].sum())
            nav[t] = cash + value.sum()
            held[t] = value / nav[t]

    def frame(x: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(x, index=idx, columns=cols)

    return pd.Series(nav, index=idx), frame(traded), frame(held)
