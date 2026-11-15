"""A small, readable event-loop engine that follows the reference semantics.

It exists to validate the suite, not to be used for research. Every rule it
follows is listed under "Reference semantics" in SPEC.md:

1. Orders decided at the close of t are sized with fill-day prices:
   ``shares = w * NAV_fill / p``.
2. Each fill pays ``rate * |traded notional|`` out of cash.
3. Shares are fractional.
4. An order for an asset with no price on the fill day is cancelled, and
   decisions made on the last day never fill.
5. ``View.universe`` is the index membership at ``as_of`` if the scenario has
   a membership table, otherwise the assets with a price at ``as_of``.
6. A position in an asset that delists is turned into cash at the close of
   its last trading day: ``shares * close * (1 + delisting_return)``.

Each rule lives in its own small method so a mutant (see ``btbias.mutants``)
can break exactly one of them by overriding one method.

Corporate actions and shorting are added together with their traps (T6,
T8). Until then the engine refuses scenarios and strategies
that need them, rather than silently getting them wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.protocol import TRADE_COLUMNS, BacktestResult, Strategy, View
from btbias.scenario import ExecutionConvention, Scenario

MIN_TRADE = 1e-12
"""Trades smaller than this fraction of NAV are skipped as floating-point noise."""


class ReferenceEngine:
    """The reference engine, usable directly as an ``Adapter``."""

    name = "reference"

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
        _require_supported(scenario)
        assets = list(scenario.assets)
        shares = pd.Series(0.0, index=assets)
        cash = float(scenario.initial_cash)
        last_close = pd.Series(np.nan, index=assets)
        pending: pd.Series | None = None
        navs: list[float] = []
        held: list[pd.Series] = []
        fills: list[dict[str, object]] = []
        delist_date = pd.to_datetime(scenario.listings["delist_date"])

        for t in scenario.calendar:
            if pending is not None:
                price = self.fill_prices(scenario, t)
                cash = self.fill(scenario, t, pending, price, last_close, shares, cash, fills)
                pending = None
            last_close = scenario.close.loc[t].combine_first(last_close)
            for asset in delist_date.index[delist_date == t]:
                cash += self.delisting_proceeds(scenario, asset, shares[asset], last_close[asset])
                shares[asset] = 0.0
            value = (shares * last_close).fillna(0.0)
            nav = cash + float(value.sum())
            weights = value / nav
            navs.append(nav)
            held.append(weights)
            view = self.view(scenario, t, weights)
            pending = _check_target(strategy.target_weights(view), assets)

        cal = scenario.calendar
        trades = pd.DataFrame(fills, columns=list(TRADE_COLUMNS))
        return BacktestResult(
            nav=pd.Series(navs, index=cal),
            trades=trades,
            weights=pd.DataFrame(held, index=cal, columns=assets),
        )

    # -- one method per rule ---------------------------------------------

    def view(self, scenario: Scenario, t: pd.Timestamp, weights: pd.Series) -> View:
        """What the strategy may see at the close of ``t``: nothing dated after it."""
        fu = scenario.fundamentals
        if not fu.empty:
            fu = fu[pd.to_datetime(fu["publish_date"]) <= t]
        return View(
            as_of=t,
            open=scenario.open.loc[:t],
            close=scenario.close.loc[:t],
            universe=self.universe(scenario, t),
            fundamentals=fu,
            weights=weights[weights != 0.0],
        )

    def universe(self, scenario: Scenario, t: pd.Timestamp) -> tuple[str, ...]:
        mb = scenario.membership
        if mb.empty:
            return tuple(scenario.close.loc[t].dropna().index)
        start = pd.to_datetime(mb["start"])
        end = pd.to_datetime(mb["end"])
        members = set(mb.loc[(start <= t) & (end.isna() | (t < end)), "asset"])
        return tuple(a for a in scenario.assets if a in members)

    def fill_prices(self, scenario: Scenario, t: pd.Timestamp) -> pd.Series:
        """Prices for orders decided on the previous trading day."""
        if scenario.convention is ExecutionConvention.NEXT_OPEN:
            return scenario.open.loc[t]
        return scenario.close.loc[t]

    def delisting_proceeds(
        self, scenario: Scenario, asset: str, shares: float, last_close: float
    ) -> float:
        """Cash received for ``shares`` of an asset that delists after this close."""
        return shares * last_close * (1 + float(scenario.listings.loc[asset, "delisting_return"]))

    def transaction_cost(self, scenario: Scenario, notional: float) -> float:
        return scenario.cost_model.rate * abs(notional)

    def fill(
        self,
        scenario: Scenario,
        t: pd.Timestamp,
        target: pd.Series,
        price: pd.Series,
        last_close: pd.Series,
        shares: pd.Series,
        cash: float,
        fills: list[dict[str, object]],
    ) -> float:
        """Trade ``shares`` (in place) towards ``target`` and return the new cash.

        All orders are sized from the same NAV, valued just before the first
        fill: tradable assets at the fill price, the rest at their last close.
        """
        mark = price.combine_first(last_close)
        nav = cash + float((shares * mark).fillna(0.0).sum())
        for asset in shares.index:
            if pd.isna(price[asset]):
                continue  # no price on the fill day: the order is cancelled
            delta = target.get(asset, 0.0) * nav / price[asset] - shares[asset]
            notional = delta * price[asset]
            if abs(notional) <= MIN_TRADE * abs(nav):
                continue
            cost = self.transaction_cost(scenario, notional)
            shares[asset] += delta
            cash -= notional + cost
            fills.append(
                {"date": t, "asset": asset, "quantity": delta, "price": price[asset], "cost": cost}
            )
        return cash


def _require_supported(scenario: Scenario) -> None:
    if not scenario.corporate_actions.empty:
        raise NotImplementedError("corporate actions are not supported yet (T6)")


def _check_target(target: pd.Series, assets: list[str]) -> pd.Series:
    unknown = set(target.index) - set(assets)
    if unknown:
        raise ValueError(f"strategy targets unknown assets {sorted(unknown)}")
    values = target.astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("target weights must be finite")
    if (values < 0).any():
        raise NotImplementedError("short positions are not supported yet (T8)")
    return values
