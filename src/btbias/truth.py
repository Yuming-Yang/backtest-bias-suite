"""Ground truth for outcome checks, computed without the reference engine.

Each function here works on a market simple enough that the answer follows
from a few lines of arithmetic. None of them imports ``btbias.reference``
(a test enforces this), so a bug in the engine cannot leak into the answer
it is graded against.
"""

from __future__ import annotations

import pandas as pd


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
