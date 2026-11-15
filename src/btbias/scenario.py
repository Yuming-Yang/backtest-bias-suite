"""Scenario: the synthetic market an engine is tested on.

A scenario holds everything an engine needs to run a backtest, plus the
point-in-time metadata (publish dates, listing dates, index membership) that
the trap tests check against. All prices are raw, as traded on the day:
splits and dividends live in ``corporate_actions`` and are never pre-applied.

Validation runs on construction, so a malformed scenario fails loudly before
any engine sees it. The frames are not deep-frozen; treat a scenario as
read-only after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd


class ScenarioError(ValueError):
    """A scenario is internally inconsistent."""


class ExecutionConvention(StrEnum):
    """When an order decided at the close of day t is filled.

    Filling at the same close the signal was computed on is deliberately not
    offered: on daily bars it is the T2 bug, not a convention.
    """

    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"


@dataclass(frozen=True)
class CostModel:
    """Proportional transaction cost: ``rate`` times traded notional.

    ``rate`` is a fraction, so 10 bps is ``0.001``.
    """

    rate: float = 0.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.rate) or self.rate < 0:
            raise ScenarioError(f"cost rate must be finite and >= 0, got {self.rate}")


CORPORATE_ACTION_COLUMNS = ("asset", "ex_date", "kind", "value")
FUNDAMENTAL_COLUMNS = ("asset", "field", "period_end", "publish_date", "value")
LISTING_COLUMNS = ("list_date", "delist_date", "delisting_return")
MEMBERSHIP_COLUMNS = ("asset", "start", "end")
CORPORATE_ACTION_KINDS = frozenset({"split", "dividend"})


def empty_frame(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


@dataclass(frozen=True)
class Scenario:
    """A complete synthetic market plus the rules the backtest must follow.

    Attributes:
        name: Short identifier, used in reports.
        calendar: Trading days, sorted and unique, at midnight.
        open, close: Raw prices, indexed by ``calendar``, one column per
            asset. NaN means the asset did not trade that day.
        listings: One row per asset (index = asset) with ``list_date``,
            ``delist_date`` (NaT if still listed) and ``delisting_return``,
            the return from the close on ``delist_date`` to the cash received
            after delisting, as in CRSP's DLRET. 0 means liquidated at the
            last close; -1 means the shares became worthless.
        corporate_actions: Rows of ``asset, ex_date, kind, value``. For a
            split, ``value`` is new shares per old share (2.0 for 2:1). For
            a dividend, it is cash per share, paid on the ex-date.
        fundamentals: Rows of ``asset, field, period_end, publish_date,
            value``. A restatement is a second row for the same
            ``(asset, field, period_end)`` with a later ``publish_date``.
        membership: Index membership intervals ``asset, start, end``,
            half-open ``[start, end)``; ``end`` is NaT if still a member.
        cost_model: Transaction costs the engine must charge.
        convention: When orders are filled.
        initial_cash: Starting NAV.
    """

    name: str
    calendar: pd.DatetimeIndex
    open: pd.DataFrame
    close: pd.DataFrame
    listings: pd.DataFrame
    corporate_actions: pd.DataFrame = field(
        default_factory=lambda: empty_frame(CORPORATE_ACTION_COLUMNS)
    )
    fundamentals: pd.DataFrame = field(default_factory=lambda: empty_frame(FUNDAMENTAL_COLUMNS))
    membership: pd.DataFrame = field(default_factory=lambda: empty_frame(MEMBERSHIP_COLUMNS))
    cost_model: CostModel = field(default_factory=CostModel)
    convention: ExecutionConvention = ExecutionConvention.NEXT_OPEN
    initial_cash: float = 1_000_000.0

    def __post_init__(self) -> None:
        self._check_calendar()
        self._check_prices()
        self._check_listings()
        self._check_corporate_actions()
        self._check_fundamentals()
        self._check_membership()
        if not np.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ScenarioError(f"initial_cash must be finite and > 0, got {self.initial_cash}")
        if not isinstance(self.convention, ExecutionConvention):
            raise ScenarioError(f"unknown execution convention {self.convention!r}")

    @property
    def assets(self) -> tuple[str, ...]:
        return tuple(self.close.columns)

    # -- checks -----------------------------------------------------------

    def _check_calendar(self) -> None:
        cal = self.calendar
        if not isinstance(cal, pd.DatetimeIndex) or len(cal) == 0:
            raise ScenarioError("calendar must be a non-empty DatetimeIndex")
        if not cal.is_monotonic_increasing or not cal.is_unique:
            raise ScenarioError("calendar must be sorted and unique")
        if cal.tz is not None:
            raise ScenarioError("calendar must be timezone-naive")
        if not (cal == cal.normalize()).all():
            raise ScenarioError("calendar dates must be at midnight (daily bars)")

    def _check_prices(self) -> None:
        for label, frame in (("open", self.open), ("close", self.close)):
            if not frame.index.equals(self.calendar):
                raise ScenarioError(f"{label} prices must be indexed by the calendar")
            if not frame.columns.is_unique:
                raise ScenarioError(f"{label} prices have duplicate asset columns")
            values = frame.to_numpy(dtype=float)
            observed = values[~np.isnan(values)]
            if not np.isfinite(observed).all() or (observed <= 0).any():
                raise ScenarioError(f"{label} prices must be positive where present")
        if not self.open.columns.equals(self.close.columns):
            raise ScenarioError("open and close must have the same asset columns in the same order")
        if self.open.isna().ne(self.close.isna()).any().any():
            raise ScenarioError("open and close must be missing on exactly the same days")

    def _check_listings(self) -> None:
        lst = self.listings
        _require_columns("listings", lst, LISTING_COLUMNS)
        if set(lst.index) != set(self.assets) or not lst.index.is_unique:
            raise ScenarioError("listings must have exactly one row per price column")
        list_date = pd.to_datetime(lst["list_date"])
        delist_date = pd.to_datetime(lst["delist_date"])
        if list_date.isna().any():
            raise ScenarioError("every asset needs a list_date")
        if (delist_date.notna() & (delist_date < list_date)).any():
            raise ScenarioError("delist_date is before list_date")
        dlret = lst["delisting_return"].astype(float)
        if not np.isfinite(dlret).all() or (dlret < -1).any():
            raise ScenarioError("delisting_return must be finite and >= -1")
        if (delist_date.isna() & (dlret != 0)).any():
            raise ScenarioError("delisting_return must be 0 for an asset that never delists")
        # Prices may only exist while the asset is listed. The delist date is
        # the last trading day; the delisting return applies after its close.
        for asset in self.assets:
            traded = self.close.index[self.close[asset].notna()]
            last_day = delist_date[asset]
            if pd.notna(last_day) and last_day not in traded:
                raise ScenarioError(f"{asset} must trade on its delist_date, the last trading day")
            if len(traded) == 0:
                continue
            if traded[0] < list_date[asset]:
                raise ScenarioError(f"{asset} has prices before its list_date")
            if pd.notna(delist_date[asset]) and traded[-1] > delist_date[asset]:
                raise ScenarioError(f"{asset} has prices after its delist_date")

    def _check_corporate_actions(self) -> None:
        ca = self.corporate_actions
        _require_columns("corporate_actions", ca, CORPORATE_ACTION_COLUMNS)
        if ca.empty:
            return
        _require_known_assets("corporate_actions", ca["asset"], self.assets)
        unknown = set(ca["kind"]) - CORPORATE_ACTION_KINDS
        if unknown:
            raise ScenarioError(f"unknown corporate action kinds: {sorted(unknown)}")
        if not pd.to_datetime(ca["ex_date"]).isin(self.calendar).all():
            raise ScenarioError("every corporate action ex_date must be a trading day")
        value = ca["value"].astype(float)
        if not np.isfinite(value).all():
            raise ScenarioError("corporate action values must be finite")
        if ca.duplicated(subset=["asset", "ex_date", "kind"]).any():
            raise ScenarioError("two corporate actions share asset, ex_date and kind")
        for asset, day in zip(ca["asset"], pd.to_datetime(ca["ex_date"]), strict=True):
            if pd.isna(self.close.loc[day, asset]):
                raise ScenarioError(f"{asset} has a corporate action on a day it does not trade")
        if (value[ca["kind"] == "split"] <= 0).any():
            raise ScenarioError("split ratios must be > 0")
        if (value[ca["kind"] == "dividend"] < 0).any():
            raise ScenarioError("dividends must be >= 0")

    def _check_fundamentals(self) -> None:
        fu = self.fundamentals
        _require_columns("fundamentals", fu, FUNDAMENTAL_COLUMNS)
        if fu.empty:
            return
        _require_known_assets("fundamentals", fu["asset"], self.assets)
        period_end = pd.to_datetime(fu["period_end"])
        publish_date = pd.to_datetime(fu["publish_date"])
        if period_end.isna().any() or publish_date.isna().any():
            raise ScenarioError("every fundamental needs a period_end and a publish_date")
        if not np.isfinite(fu["value"].astype(float)).all():
            raise ScenarioError("fundamental values must be finite")
        if (publish_date < period_end).any():
            raise ScenarioError("a fundamental is published before its period ends")
        key = ["asset", "field", "period_end", "publish_date"]
        if fu.duplicated(subset=key).any():
            raise ScenarioError(
                "two fundamental rows share asset, field, period_end and publish_date"
            )

    def _check_membership(self) -> None:
        mb = self.membership
        _require_columns("membership", mb, MEMBERSHIP_COLUMNS)
        if mb.empty:
            return
        _require_known_assets("membership", mb["asset"], self.assets)
        start = pd.to_datetime(mb["start"])
        end = pd.to_datetime(mb["end"])
        if start.isna().any():
            raise ScenarioError("every membership interval needs a start")
        if (end.notna() & (end <= start)).any():
            raise ScenarioError("membership interval end must be after start")
        for asset, group in mb.assign(start=start, end=end).groupby("asset"):
            g = group.sort_values("start")
            prev_end = g["end"].shift().iloc[1:]
            later_start = g["start"].iloc[1:]
            # An open-ended interval (NaT end) overlaps anything after it.
            if (prev_end.isna() | (later_start < prev_end)).any():
                raise ScenarioError(f"{asset} has overlapping membership intervals")
            listed_from = pd.Timestamp(self.listings.loc[asset, "list_date"])
            listed_to = pd.to_datetime(self.listings.loc[asset, "delist_date"])
            for first, end_ in zip(g["start"], g["end"], strict=True):
                member = self.calendar >= first
                if pd.notna(end_):
                    member &= self.calendar < end_
                days = self.calendar[member]
                if (days < listed_from).any() or (pd.notna(listed_to) and (days > listed_to).any()):
                    raise ScenarioError(f"{asset} is an index member on a day it is not listed")


def _require_columns(label: str, frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ScenarioError(f"{label} is missing columns {missing}")


def _require_known_assets(label: str, assets: pd.Series, known: tuple[str, ...]) -> None:
    unknown = set(assets) - set(known)
    if unknown:
        raise ScenarioError(f"{label} refers to unknown assets {sorted(unknown)}")
