"""T4: assets that delist vanish from history, or their delisting return is lost.

Scenario: five assets on a random walk without gaps or costs. DDD is taken
over for cash after day 20 with a +25% delisting return. EEE drifts down
and is delisted for performance after day 40 with a -30% delisting return,
the order of magnitude Shumway (1997) imputes for missing
performance-related returns. The strategy holds every listed asset
equally.

Outcome check: NAV matches ``truth.listed_market_nav``, which keeps both
doomed assets in the portfolio while they trade and pays their delisting
returns. An engine that hides them (survivorship) or drops the delisting
return gets a different NAV.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import delist, listed_throughout, random_walk, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import Scenario
from btbias.strategies import EqualWeightUniverse, equal_weight
from btbias.trap import Trap, nav_mismatch
from btbias.truth import listed_market_nav

ASSETS = ["AAA", "BBB", "CCC", "DDD", "EEE"]
N_DAYS = 60
SEED = 404
TAKEOVER = ("DDD", 20, 0.25)
FAILURE = ("EEE", 40, -0.30)


def build() -> tuple[Scenario, Strategy]:
    calendar = trading_days(N_DAYS)
    open_, close = random_walk(calendar, ASSETS, seed=SEED, drift={"EEE": -0.01})
    listings = listed_throughout(calendar, ASSETS)
    for asset, day, dlret in (TAKEOVER, FAILURE):
        delist(open_, close, listings, asset, calendar[day], dlret)
    return simple_market("T4 survivorship", open_, close, listings=listings), EqualWeightUniverse()


def expected_schedule(scenario: Scenario) -> pd.DataFrame:
    """Equal weights over the assets that trade on each day."""
    rows = [
        equal_weight(tuple(scenario.close.loc[t].dropna().index))
        .reindex(scenario.assets, fill_value=0.0)
        .to_numpy()
        for t in scenario.calendar
    ]
    return pd.DataFrame(np.vstack(rows), index=scenario.calendar, columns=list(scenario.assets))


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    expected = listed_market_nav(
        expected_schedule(scenario),
        scenario.open,
        scenario.close,
        scenario.listings,
        scenario.initial_cash,
    )
    mismatch = nav_mismatch(result.nav, expected)
    return [mismatch] if mismatch else []


T4 = Trap(id="T4", title="Survivorship bias", build=build, check=check)
