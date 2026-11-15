"""Helpers for adapters around engines that work on weight and money tables.

``view_at`` builds a point-in-time view. ``fills_from_money`` turns a table
of money traded per asset and day into the one-row-per-fill trades table
the suite expects.

An engine that reads its own data (an event loop with a data handler) should
build views from that data, so the probe checks test the engine. A
vectorized engine only takes a weight matrix: the adapter has to ask the
strategy for each day's weights, and needs a view to do it. ``view_at``
builds a correct one, so the adapter does not have to rewrite the
point-in-time rules.

The cost of using it: for that adapter, T1, T3 and T7's probes test this
function rather than the engine. Their outcome checks, and every other trap,
still test the engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.protocol import TRADE_COLUMNS, View
from btbias.scenario import Scenario


def view_at(scenario: Scenario, t: pd.Timestamp) -> View:
    """What may be known at the close of ``t``, under the reference semantics.

    Prices up to ``t``; fundamentals published on or before ``t``; the
    universe is the index members at ``t`` if the scenario has a membership
    table, otherwise the assets with a price at ``t``.
    """
    fu = scenario.fundamentals
    if not fu.empty:
        fu = fu[pd.to_datetime(fu["publish_date"]) <= t]
    mb = scenario.membership
    if mb.empty:
        universe = tuple(scenario.close.columns[scenario.close.loc[t].notna()])
    else:
        start, end = pd.to_datetime(mb["start"]), pd.to_datetime(mb["end"])
        current = set(mb.loc[(start <= t) & (end.isna() | (t < end)), "asset"])
        universe = tuple(a for a in scenario.assets if a in current)
    return View(
        as_of=t,
        open=scenario.open.loc[:t],
        close=scenario.close.loc[:t],
        universe=universe,
        fundamentals=fu,
    )


def fills_from_money(traded: pd.DataFrame, prices: pd.DataFrame, cost_rate: float) -> pd.DataFrame:
    """One trade row per non-zero cell of ``traded`` (money bought, sells < 0).

    Each fill is priced from ``prices`` on the same day (the open, for an
    engine that fills at the next open) and pays ``cost_rate`` on its size.
    """
    day, asset = np.nonzero(traded.to_numpy())
    money = traded.to_numpy(dtype=float)[day, asset]
    price = prices.reindex_like(traded).to_numpy(dtype=float)[day, asset]
    return pd.DataFrame(
        {
            "date": traded.index[day],
            "asset": traded.columns[asset],
            "quantity": money / price,
            "price": price,
            "cost": cost_rate * np.abs(money),
        },
        columns=list(TRADE_COLUMNS),
    )
