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


def listed_market_nav(
    schedule: pd.DataFrame,
    open_: pd.DataFrame,
    close: pd.DataFrame,
    listings: pd.DataFrame,
    initial_cash: float,
) -> pd.Series:
    """NAV of a weight schedule on a market where assets delist, with no costs.

    Orders fill at the next open, and every open equals the previous close,
    so a fill on day k is a rebalance at the close of k - 1. NAV then grows
    each day by ``1 + w . r``, where ``r`` is each asset's close-to-close
    return and ``w`` the weights decided the evening before.

    Two rules come from delistings. An asset with no open on the fill day
    cannot be bought, so its target weight stays in cash. On an asset's last
    trading day its return is compounded with its delisting return, which
    is paid at that close. Assets may not stop and restart trading.
    """
    for asset in close.columns:
        traded = close[asset].notna().to_numpy()
        first, last = traded.argmax(), len(traded) - traded[::-1].argmax()
        if not traded[first:last].all():
            raise ValueError(f"{asset} stops and restarts trading")
    both = open_.notna() & close.shift(1).notna()
    if not ((open_ == close.shift(1)) | ~both).all().all():
        raise ValueError("listed_market_nav needs every open to equal the previous close")

    held = schedule.reindex(columns=close.columns).fillna(0.0).shift(1).fillna(0.0)
    held = held.where(open_.notna(), 0.0)
    r = close / close.shift(1) - 1
    delist_date = pd.to_datetime(listings["delist_date"])
    for asset, day in delist_date.dropna().items():
        dlret = float(listings.loc[asset, "delisting_return"])
        r.loc[day, asset] = (1 + r.loc[day, asset]) * (1 + dlret) - 1
    return initial_cash * (1 + (held * r.fillna(0.0)).sum(axis=1)).cumprod()


def flat_market_borrow_nav(
    schedule: pd.DataFrame,
    initial_cash: float,
    daily_rate: float,
    hard_to_borrow: frozenset[str],
) -> pd.Series:
    """NAV of a long-short schedule on a market where no price moves, with no trading costs.

    As in ``flat_market_nav``, everything is in money. At each fill the money
    in each asset moves to ``weight * NAV``, except that a hard-to-borrow
    asset cannot go below zero (or below its current short, if it had one).
    At that day's close every short pays ``daily_rate`` on its size, and that
    fee is the only thing that moves NAV.
    """
    nav = float(initial_cash)
    held = pd.Series(0.0, index=schedule.columns)
    hard = schedule.columns.isin(sorted(hard_to_borrow))
    navs = [nav]
    for k in range(1, len(schedule)):
        target = schedule.iloc[k - 1].fillna(0.0) * nav
        floor = held.clip(upper=0.0)
        held = target.where(~hard, target.combine(floor, max))
        nav -= daily_rate * float(-held[held < 0].sum())
        navs.append(nav)
    return pd.Series(navs, index=schedule.index)
