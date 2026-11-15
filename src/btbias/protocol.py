"""The contract between the suite, a strategy and the engine under test.

The flow for one backtest is:

1. The suite hands an adapter a ``Scenario`` and a ``Strategy``.
2. The adapter runs its engine. At the close of each trading day t the engine
   builds a ``View`` of what it believes is knowable at t and calls
   ``strategy.target_weights(view)``.
3. The engine fills the resulting orders under ``scenario.convention`` and the
   adapter returns a ``BacktestResult``.

``View`` is a plain container on purpose. The suite does not trust it: probe
strategies record what they were shown, and the trap tests check that record.
A view that contains the future is exactly the bug T1 looks for, so ``View``
must not validate itself away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from btbias.scenario import Scenario

TRADE_COLUMNS = ("date", "asset", "quantity", "price", "cost")


class ResultError(ValueError):
    """A backtest result does not have the shape the suite expects."""


@dataclass(frozen=True)
class View:
    """What a strategy is shown at the close of ``as_of``.

    Attributes:
        as_of: The decision date. The decision is made after its close.
        open, close: Price history the engine exposes, one column per asset.
            A correct engine shows only rows dated ``<= as_of``.
        universe: Assets the engine says the strategy may hold at ``as_of``.
        fundamentals: Fundamental rows the engine exposes, same columns as
            ``Scenario.fundamentals``. A correct engine shows only rows
            published on or before ``as_of``.
        weights: Current holdings as fractions of NAV at the ``as_of`` close,
            before any new trade. Missing assets mean zero.
    """

    as_of: pd.Timestamp
    open: pd.DataFrame
    close: pd.DataFrame
    universe: tuple[str, ...]
    fundamentals: pd.DataFrame = field(default_factory=pd.DataFrame)
    weights: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


@runtime_checkable
class Strategy(Protocol):
    """Maps a view to target portfolio weights.

    The returned series is indexed by asset and gives each target as a
    fraction of NAV. Missing assets are zero; whatever is left is cash.
    """

    name: str

    def target_weights(self, view: View) -> pd.Series: ...


@runtime_checkable
class Adapter(Protocol):
    """Wraps one backtest engine so the suite can drive it."""

    name: str

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult: ...


@dataclass(frozen=True)
class BacktestResult:
    """What an engine produced.

    Attributes:
        nav: Net asset value after each day's close (including cash, costs,
            dividends and delisting proceeds), indexed by the calendar.
        trades: One row per fill: ``date, asset, quantity, price, cost``.
            ``quantity`` is signed shares (buy > 0), ``price`` is the raw fill
            price, ``cost`` is the transaction cost charged, in cash.
        weights: Holdings as fractions of NAV after each day's close, indexed
            by the calendar, one column per asset held at some point.
    """

    nav: pd.Series
    trades: pd.DataFrame
    weights: pd.DataFrame

    def check_against(self, scenario: Scenario) -> None:
        """Raise ``ResultError`` if the result cannot be compared to ground truth.

        This checks shape, not correctness: a result can pass here and still
        fail every trap.
        """
        cal = scenario.calendar
        if not self.nav.index.equals(cal):
            raise ResultError("nav must be indexed by the scenario calendar")
        if not np.isfinite(self.nav.to_numpy(dtype=float)).all():
            raise ResultError("nav must be finite on every day")

        if not self.weights.index.equals(cal):
            raise ResultError("weights must be indexed by the scenario calendar")
        unknown = set(self.weights.columns) - set(scenario.assets)
        if unknown:
            raise ResultError(f"weights refer to unknown assets {sorted(unknown)}")
        if not np.isfinite(self.weights.to_numpy(dtype=float)).all():
            raise ResultError("weights must be finite on every day")

        tr = self.trades
        missing = [c for c in TRADE_COLUMNS if c not in tr.columns]
        if missing:
            raise ResultError(f"trades is missing columns {missing}")
        if tr.empty:
            return
        if not pd.to_datetime(tr["date"]).isin(cal).all():
            raise ResultError("every trade date must be a trading day")
        unknown = set(tr["asset"]) - set(scenario.assets)
        if unknown:
            raise ResultError(f"trades refer to unknown assets {sorted(unknown)}")
        if not np.isfinite(tr[["quantity", "price", "cost"]].to_numpy(dtype=float)).all():
            raise ResultError("trade quantity, price and cost must be finite")
        for day, asset in zip(pd.to_datetime(tr["date"]), tr["asset"], strict=True):
            if pd.isna(scenario.close.loc[day, asset]):
                raise ResultError(f"trade in {asset} on {day.date()}, a day it does not trade")
        if (tr["price"].astype(float) <= 0).any():
            raise ResultError("fill prices must be > 0")
        if (tr["cost"].astype(float) < 0).any():
            raise ResultError("transaction costs must be >= 0")
