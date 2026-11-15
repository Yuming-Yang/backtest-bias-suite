"""Hand-built scenarios shared by tests."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from btbias.protocol import View
from btbias.scenario import Scenario

CALENDAR = pd.bdate_range("2024-01-01", periods=5)


def make_scenario(**overrides: Any) -> Scenario:
    """A tiny valid scenario: AAA trades all 5 days, BBB delists on day 3."""
    close = pd.DataFrame(
        {"AAA": [10.0, 11.0, 12.0, 11.0, 13.0], "BBB": [20.0, 19.0, 18.0, np.nan, np.nan]},
        index=CALENDAR,
    )
    listings = pd.DataFrame(
        {
            "list_date": [CALENDAR[0], CALENDAR[0]],
            "delist_date": [pd.NaT, CALENDAR[2]],
            "delisting_return": [0.0, -0.3],
        },
        index=["AAA", "BBB"],
    )
    kwargs: dict[str, Any] = {
        "name": "tiny",
        "calendar": CALENDAR,
        "open": close * 0.99,
        "close": close,
        "listings": listings,
    }
    kwargs.update(overrides)
    return Scenario(**kwargs)


@dataclass
class Fixed:
    """Returns a preset target per day and records every view."""

    targets: dict[int, dict[str, float]]
    name: str = "fixed"
    seen: list[View] = field(default_factory=list)

    def target_weights(self, view: View) -> pd.Series:
        self.seen.append(view)
        day = len(self.seen) - 1
        return pd.Series(self.targets.get(day, {}), dtype=float)
