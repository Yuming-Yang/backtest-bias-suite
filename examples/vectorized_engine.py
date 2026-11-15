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

Limits: fills at the next open only; every asset needs a price every day;
no corporate actions, delistings or borrow fees.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def backtest(
    weights: pd.DataFrame,
    open_: pd.DataFrame,
    close: pd.DataFrame,
    cost_rate: float,
    initial_cash: float,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """Run a weight schedule.

    ``weights.loc[t]`` is the target decided at the close of ``t`` and filled
    at the open of the next day. Returns NAV at each close, the money traded in
    each asset at each open (buys > 0), and the weights held at each close.
    """
    if open_.isna().any().any() or close.isna().any().any():
        raise ValueError("the example engine needs a price for every asset on every day")
    o, c = open_.to_numpy(dtype=float), close.to_numpy(dtype=float)
    w = weights.reindex(index=close.index, columns=close.columns).fillna(0.0).to_numpy(dtype=float)
    n_days, n_assets = c.shape

    value = np.zeros(n_assets)  # money held in each asset
    cash = float(initial_cash)
    nav = np.empty(n_days)
    traded = np.zeros((n_days, n_assets))
    held = np.zeros((n_days, n_assets))
    for t in range(n_days):
        if t > 0:
            value = value * o[t] / c[t - 1]  # overnight drift
            target = w[t - 1] * (cash + value.sum())
            traded[t] = target - value
            cash -= traded[t].sum() + cost_rate * np.abs(traded[t]).sum()
            value = target
        value = value * c[t] / o[t]  # open to close
        nav[t] = cash + value.sum()
        held[t] = value / nav[t]

    def frame(x: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(x, index=close.index, columns=close.columns)

    return pd.Series(nav, index=close.index), frame(traded), frame(held)
