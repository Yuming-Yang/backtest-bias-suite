"""T7: today's index members are used for the whole history.

Scenario: six assets that all trade throughout, without gaps or costs, and
an index of four. BBB leaves after day 20 and EEE joins; CCC leaves after
day 40 and FFF joins. As in real index reconstitutions, the names that join
have been rising and the names that leave have been falling. The strategy
holds every index member equally.

Two checks:

1. Probe. Every asset a view offers was an index member on that day.
2. Outcome. NAV matches equal weights over the point-in-time members
   (``truth.no_cost_nav``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btbias.generator import random_walk, simple_market, trading_days
from btbias.protocol import BacktestResult, Strategy
from btbias.scenario import Scenario
from btbias.strategies import EqualWeightUniverse, equal_weight
from btbias.trap import Trap, nav_mismatch
from btbias.truth import no_cost_nav

ASSETS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
N_DAYS = 60
SEED = 707
TREND = 0.008


def build() -> tuple[Scenario, Strategy]:
    cal = trading_days(N_DAYS)
    drift = {"BBB": -TREND, "CCC": -TREND, "EEE": TREND, "FFF": TREND}
    open_, close = random_walk(cal, ASSETS, seed=SEED, drift=drift)
    membership = pd.DataFrame(
        {
            "asset": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
            "start": [cal[0], cal[0], cal[0], cal[0], cal[21], cal[41]],
            "end": [pd.NaT, cal[21], cal[41], pd.NaT, pd.NaT, pd.NaT],
        }
    )
    scenario = simple_market("T7 membership", open_, close, membership=membership)
    return scenario, EqualWeightUniverse()


def members_at(scenario: Scenario, t: pd.Timestamp) -> tuple[str, ...]:
    mb = scenario.membership
    start, end = pd.to_datetime(mb["start"]), pd.to_datetime(mb["end"])
    current = set(mb.loc[(start <= t) & (end.isna() | (t < end)), "asset"])
    return tuple(a for a in scenario.assets if a in current)


def expected_schedule(scenario: Scenario) -> pd.DataFrame:
    rows = [
        equal_weight(members_at(scenario, t)).reindex(scenario.assets, fill_value=0.0).to_numpy()
        for t in scenario.calendar
    ]
    return pd.DataFrame(np.vstack(rows), index=scenario.calendar, columns=list(scenario.assets))


def check(scenario: Scenario, strategy: Strategy, result: BacktestResult) -> list[str]:
    if not isinstance(strategy, EqualWeightUniverse):
        raise TypeError(f"T7 expects the strategy it built, got {type(strategy).__name__}")
    problems = []
    outsiders = [
        (v.as_of, sorted(set(v.universe) - set(members_at(scenario, v.as_of))))
        for v in strategy.seen
    ]
    outsiders = [(day, extra) for day, extra in outsiders if extra]
    if outsiders:
        day, extra = outsiders[0]
        problems.append(
            f"{len(outsiders)} view(s) offer assets that were not index members, "
            f"first {', '.join(extra)} on {day:%Y-%m-%d}"
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


T7 = Trap(id="T7", title="Universe membership lookahead", build=build, check=check)
