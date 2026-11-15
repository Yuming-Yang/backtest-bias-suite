"""T3: fundamentals are visible before they were published.

Scenario: four assets on a random walk without gaps or costs, with reports
every 20 trading days that are published 5-15 days after the period ends,
and about 40% of them restated 10-25 days after that. The strategy holds
the asset with the highest latest-known value.

Two checks:

1. Probe. Every fundamental row a view shows must have a publish date on or
   before ``as_of``, and must be a row of the scenario exactly as published.
   The first catches reports used from their period end; the second catches
   restated values written over the original row.
2. Outcome. NAV matches the strategy run on the rows published by each day
   (``truth.no_cost_nav``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import random_fundamentals, random_walk, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import Scenario
from btbias.strategies import FundamentalTilt, best_reported
from btbias.trap import Trap, nav_mismatch
from btbias.truth import no_cost_nav

ASSETS = ["AAA", "BBB", "CCC", "DDD"]
N_DAYS = 120
SEED = 303


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = random_walk(calendar, ASSETS, seed=SEED)
    fundamentals = random_fundamentals(calendar, ASSETS, seed=SEED + 1)
    scenario = simple_market("T3 point-in-time", open_, close, fundamentals=fundamentals)
    return scenario, FundamentalTilt()


def published_by(fundamentals: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    return fundamentals[pd.to_datetime(fundamentals["publish_date"]) <= t]


def expected_schedule(scenario: Scenario) -> pd.DataFrame:
    """The strategy's targets when it sees only rows published by each day."""
    rows = [
        best_reported(published_by(scenario.fundamentals, t))
        .reindex(scenario.assets, fill_value=0.0)
        .to_numpy()
        for t in scenario.calendar
    ]
    return pd.DataFrame(np.vstack(rows), index=scenario.calendar, columns=list(scenario.assets))


def _as_published(fundamentals: pd.DataFrame) -> set[tuple]:
    return set(
        zip(
            fundamentals["asset"],
            fundamentals["field"],
            pd.to_datetime(fundamentals["period_end"]),
            pd.to_datetime(fundamentals["publish_date"]),
            fundamentals["value"].astype(float),
            strict=True,
        )
    )


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, FundamentalTilt):
        raise TypeError(f"T3 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    published = _as_published(scenario.fundamentals)
    early, altered = [], []
    for v in strategy.seen:
        fu = v.fundamentals
        if fu.empty:
            continue
        if (pd.to_datetime(fu["publish_date"]) > v.as_of).any():
            early.append(v.as_of)
        if not _as_published(fu) <= published:
            altered.append(v.as_of)
    if early:
        problems.append(
            f"{len(early)} view(s) show fundamentals before their publish date, "
            f"first at the {early[0]:%Y-%m-%d} close"
        )
    if altered:
        problems.append(
            f"{len(altered)} view(s) show fundamental rows that were never published as shown, "
            f"first at the {altered[0]:%Y-%m-%d} close"
        )
    expected = no_cost_nav(
        expected_schedule(scenario),
        scenario.open,
        scenario.close,
        scenario.convention,
        scenario.initial_cash,
    )
    mismatch = nav_mismatch(result.nav, expected)
    if mismatch:
        problems.append(mismatch)
    return problems


T3 = Trap(id="T3", title="Fundamentals not point-in-time", build=build, check=check)
