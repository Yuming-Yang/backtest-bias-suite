"""Ground truth for outcome checks, computed without the reference engine.

Each function here works on a market simple enough that the answer follows
from a few lines of arithmetic. None of them imports ``btbias.reference``
(a test enforces this), so a bug in the engine cannot leak into the answer
it is graded against.
"""

from __future__ import annotations

import pandas as pd

from btbias.scenario import ExecutionConvention


def flat_market_nav(schedule: pd.DataFrame, initial_cash: float, cost_rate: float) -> pd.Series:
    """NAV of a weight schedule on a market where no price ever moves.

    ``schedule.loc[t]`` holds the target weights decided at the close of
    ``t``; they fill on the next row's day, and the last row never fills.

    With constant prices, holdings change value only when traded, so the
    whole calculation can be done in money: no shares, no prices, and the
    execution convention does not matter. At each fill the target money in
    each asset is ``weight * NAV`` (NAV before this fill's costs), the cost
    is ``cost_rate`` times the money moved, and NAV falls by exactly that.
    """
    nav = float(initial_cash)
    held = pd.Series(0.0, index=schedule.columns)
    navs = [nav]
    for k in range(1, len(schedule)):
        target = schedule.iloc[k - 1].fillna(0.0) * nav
        nav -= cost_rate * float((target - held).abs().sum())
        held = target
        navs.append(nav)
    return pd.Series(navs, index=schedule.index)


def no_cost_nav(
    schedule: pd.DataFrame,
    open_: pd.DataFrame,
    close: pd.DataFrame,
    convention: ExecutionConvention,
    initial_cash: float,
) -> pd.Series:
    """NAV of a weight schedule on a moving market with no costs.

    ``schedule.loc[t]`` holds the target weights decided at the close of
    ``t``; they fill at the next day's open (or close, under
    ``NEXT_CLOSE``), and the last row never fills.

    Without costs, rebalancing to target weights at a fill makes the
    portfolio grow by ``1 + w . r`` until the next fill, where ``r`` is each
    asset's return between the two fill prices. So NAV at each fill is a
    cumulative product of those factors, and NAV at a close is the last
    fill's NAV grown from the fill price to that close. Every asset needs a
    price on every day.
    """
    if open_.isna().any().any() or close.isna().any().any():
        raise ValueError("no_cost_nav needs a price for every asset on every day")
    fill = open_ if convention is ExecutionConvention.NEXT_OPEN else close
    # held.loc[t]: weights held from the fill on t until the next fill.
    held = schedule.reindex(columns=close.columns).fillna(0.0).shift(1).fillna(0.0)
    between_fills = (held.shift(1).fillna(0.0) * (fill / fill.shift(1) - 1).fillna(0.0)).sum(axis=1)
    nav_at_fill = initial_cash * (1 + between_fills).cumprod()
    return nav_at_fill * (1 + (held * (close / fill - 1)).sum(axis=1))
